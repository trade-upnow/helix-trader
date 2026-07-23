from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.models import ApiCredential, BotPositionLedger, BotSession, TradeRecord
from app.services.account_sync import account_sync_service, extract_account_equity
from app.services.encryption import EncryptionService
from app.services.exchange.factory import build_exchange_adapter
from app.services.market_catalog import market_catalog_service
from app.services.strategies.base import StrategyContext, StrategyPosition
from app.services.strategies.registry import get_strategy

logger = logging.getLogger(__name__)
BOT_TAG = "helixbot"
POSITION_CAP_SKIP_RATIO = 0.98
BATCH_RETRY_TIMES = 2
BATCH_RETRY_DELAY_SECONDS = 1.5
MARKET_RULE_STALE_MINUTES = 45
TASK_CANCEL_GRACE_SECONDS = 3.0
POSITION_RECONCILE_EPSILON = 1e-9


class BotManager:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._wake_events: dict[str, asyncio.Event] = {}
        self._stop_tasks: dict[str, asyncio.Task] = {}
        self._encryption = EncryptionService()

    def _register_task(self, user_id: str, task: asyncio.Task) -> None:
        self._tasks[user_id] = task
        task.add_done_callback(
            lambda finished_task: self._clear_task_refs(user_id, finished_task)
        )

    def _clear_task_refs(self, user_id: str, task: asyncio.Task | None = None) -> None:
        tracked_task = self._tasks.get(user_id)
        if task is None or tracked_task is task:
            self._tasks.pop(user_id, None)
            self._wake_events.pop(user_id, None)

    def is_running(self, user_id: str) -> bool:
        task = self._tasks.get(user_id)
        if task is None:
            return False
        if task.done():
            self._clear_task_refs(user_id, task)
            return False
        return True

    def is_stopping(self, user_id: str) -> bool:
        task = self._stop_tasks.get(user_id)
        if task is None:
            return False
        if task.done():
            self._stop_tasks.pop(user_id, None)
            return False
        return True

    async def _cancel_task(
        self,
        user_id: str,
        *,
        raise_on_timeout: bool,
    ) -> bool:
        task = self._tasks.get(user_id)
        wake_event = self._wake_events.get(user_id)
        if wake_event:
            wake_event.set()
        if task is None:
            self._clear_task_refs(user_id)
            return True

        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=TASK_CANCEL_GRACE_SECONDS)
        except asyncio.CancelledError:
            self._clear_task_refs(user_id, task)
            return True
        except asyncio.TimeoutError as exc:
            logger.warning(
                "Bot task cancellation timed out",
                extra={"user_id": user_id},
            )
            if raise_on_timeout:
                raise RuntimeError(
                    "Previous bot instance is still shutting down; retry in a few seconds"
                ) from exc
            return False

        self._clear_task_refs(user_id, task)
        return True

    def _collect_remote_position_sizes(
        self, positions: list[dict], symbol: str
    ) -> dict[str, float]:
        sizes = {"long": 0.0, "short": 0.0}
        for position in positions:
            position_symbol = position.get("symbol")
            if position_symbol and position_symbol != symbol:
                continue

            raw_contracts = position.get("contracts")
            if raw_contracts is None:
                raw_contracts = position.get("contractsSize")
            try:
                signed_contracts = float(raw_contracts or 0)
            except (TypeError, ValueError):
                continue
            if abs(signed_contracts) <= POSITION_RECONCILE_EPSILON:
                continue

            raw_side = str(position.get("side") or "").lower()
            if raw_side in {"long", "buy"}:
                side = "long"
            elif raw_side in {"short", "sell"}:
                side = "short"
            elif signed_contracts > 0:
                side = "long"
            else:
                side = "short"
            sizes[side] += abs(signed_contracts)
        return sizes

    async def _reconcile_ledgers_with_exchange(
        self,
        session: AsyncSession,
        bot_session: BotSession,
        adapter,
        ledgers: list[BotPositionLedger],
    ) -> list[BotPositionLedger]:
        if not ledgers:
            return ledgers

        symbol = bot_session.config["symbol"]
        try:
            remote_positions = await adapter.fetch_positions([symbol]) or []
        except Exception:
            logger.warning(
                "Failed to reconcile bot ledgers with remote positions",
                extra={
                    "user_id": bot_session.user_id,
                    "session_id": bot_session.id,
                    "exchange": bot_session.exchange,
                    "symbol": symbol,
                },
                exc_info=True,
            )
            return ledgers

        remote_sizes = self._collect_remote_position_sizes(remote_positions, symbol)
        reconciled: list[BotPositionLedger] = []
        changed = False
        for ledger in ledgers:
            remote_qty = remote_sizes.get(ledger.side, 0.0)
            if remote_qty <= POSITION_RECONCILE_EPSILON:
                logger.info(
                    "Dropping stale bot ledger with no remote position",
                    extra={
                        "user_id": bot_session.user_id,
                        "session_id": bot_session.id,
                        "exchange": bot_session.exchange,
                        "symbol": ledger.symbol,
                        "side": ledger.side,
                        "ledger_qty": ledger.quantity,
                    },
                )
                await session.delete(ledger)
                changed = True
                continue

            if remote_qty + POSITION_RECONCILE_EPSILON < ledger.quantity:
                logger.info(
                    "Shrinking bot ledger to remote position size",
                    extra={
                        "user_id": bot_session.user_id,
                        "session_id": bot_session.id,
                        "exchange": bot_session.exchange,
                        "symbol": ledger.symbol,
                        "side": ledger.side,
                        "ledger_qty": ledger.quantity,
                        "remote_qty": remote_qty,
                    },
                )
                ledger.quantity = remote_qty
                changed = True
            reconciled.append(ledger)

        if changed:
            await session.flush()
        return reconciled

    async def restore_running_bots(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        async with session_factory() as session:
            result = await session.execute(
                select(BotSession).where(BotSession.status == "running")
            )
            sessions = result.scalars().all()

        for bot_session in sessions:
            if bot_session.user_id not in self._tasks:
                self._wake_events[bot_session.user_id] = asyncio.Event()
                self._register_task(
                    bot_session.user_id,
                    asyncio.create_task(
                        self._run_loop(session_factory, bot_session.user_id, bot_session.id)
                    ),
                )

    def request_immediate_cycle(self, user_id: str) -> None:
        event = self._wake_events.get(user_id)
        if event:
            event.set()

    async def _cancel_running_task_only(self, user_id: str) -> None:
        await self._cancel_task(user_id, raise_on_timeout=True)

    async def start_bot(
        self, session_factory: async_sessionmaker[AsyncSession], user_id: str, session_id: str
    ) -> None:
        if self.is_running(user_id):
            raise RuntimeError("Bot is already running")
        if self.is_stopping(user_id):
            raise RuntimeError("Bot is stopping; wait until close-out completes")
        async with session_factory() as session:
            bot_session = await session.get(BotSession, session_id)
            if not bot_session or bot_session.status != "running":
                raise RuntimeError("Bot session is not ready to start")

            try:
                await self._prepare_runtime(session, bot_session)
                bot_session.last_heartbeat = datetime.now(timezone.utc)
                bot_session.status_message = "Healthy"
                await session.commit()
            except Exception as exc:
                bot_session.status = "stopped"
                bot_session.stopped_at = datetime.now(timezone.utc)
                bot_session.status_message = f"Startup failed: {exc}"
                logger.exception(
                    "Bot startup failed",
                    extra={
                        "user_id": bot_session.user_id,
                        "session_id": bot_session.id,
                        "exchange": bot_session.exchange,
                        "use_testnet": bot_session.use_testnet,
                    },
                )
                await session.commit()
                raise RuntimeError(str(exc)) from exc

        self._wake_events[user_id] = asyncio.Event()
        self._register_task(
            user_id,
            asyncio.create_task(
                self._run_loop(session_factory, user_id, session_id)
            ),
        )
        account_sync_service.request_refresh()

    async def stop_bot(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        user_id: str,
        close_all: bool,
    ) -> str:
        if self.is_stopping(user_id):
            return "Bot is stopping"

        running_before_stop = self.is_running(user_id)
        await self._cancel_task(user_id, raise_on_timeout=False)

        stopped_session = False
        async with session_factory() as session:
            result = await session.execute(
                select(BotSession)
                .where(BotSession.user_id == user_id)
                .where(BotSession.status == "running")
                .order_by(BotSession.started_at.desc())
            )
            bot_session = result.scalars().first()
            if not bot_session:
                return "Bot is already stopped"
            stopped_session = True

            close_session_id = bot_session.id if close_all else None
            await self._sync_stop(session, bot_session, close_all=False)
            if close_all and close_session_id:
                bot_session.status_message = "Stopping; closing bot positions in background"
            await session.commit()

        if close_all and close_session_id:
            self._stop_tasks[user_id] = asyncio.create_task(
                self._close_positions_after_stop(session_factory, user_id, close_session_id)
            )
            return "Bot is stopping"

        account_sync_service.request_refresh()
        if running_before_stop or stopped_session:
            return "Bot stopped"
        return "Bot is already stopped"

    async def _close_positions_after_stop(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        user_id: str,
        session_id: str,
    ) -> None:
        try:
            async with session_factory() as session:
                bot_session = await session.get(BotSession, session_id)
                if not bot_session:
                    return
                adapter = None
                try:
                    _, adapter = await self._load_runtime_dependencies(session, bot_session)
                    await adapter.initialize()
                    ledgers = await self._load_ledgers(session, bot_session)
                    ledgers = await self._reconcile_ledgers_with_exchange(
                        session,
                        bot_session,
                        adapter,
                        ledgers,
                    )
                    logger.info(
                        "Starting background stop close-out",
                        extra={
                            "user_id": bot_session.user_id,
                            "session_id": bot_session.id,
                            "exchange": bot_session.exchange,
                            "symbol": bot_session.config.get("symbol"),
                            "ledger_count": len(ledgers),
                        },
                    )
                    if ledgers:
                        await self._close_ledgers(
                            session,
                            bot_session,
                            adapter,
                            ledgers,
                            0,
                            "Stopped by user",
                        )
                    else:
                        bot_session.status_message = (
                            "Stopped by user; no bot-managed positions to close "
                            "(pre-existing exchange positions were left untouched)"
                        )
                    if not bot_session.status_message or "Stopping;" in bot_session.status_message:
                        bot_session.status_message = "Stopped by user"
                    logger.info(
                        "Background stop close-out finished",
                        extra={
                            "user_id": bot_session.user_id,
                            "session_id": bot_session.id,
                            "exchange": bot_session.exchange,
                            "symbol": bot_session.config.get("symbol"),
                        },
                    )
                    await session.commit()
                except Exception:
                    bot_session.status_message = "Stopped locally; remote close-all may require review"
                    logger.exception("Bot stop close-out failed")
                    await session.commit()
                finally:
                    if adapter is not None:
                        await adapter.close()
        finally:
            self._stop_tasks.pop(user_id, None)
            account_sync_service.request_refresh()

    async def _sync_stop(
        self, session: AsyncSession, bot_session: BotSession, close_all: bool
    ) -> None:
        bot_session.status = "stopped"
        bot_session.stopped_at = datetime.now(timezone.utc)
        bot_session.status_message = "Stopped by user"

        if close_all:
            adapter = None
            try:
                _, adapter = await self._load_runtime_dependencies(session, bot_session)
                await adapter.initialize()
                ledgers = await self._load_ledgers(session, bot_session)
                ledgers = await self._reconcile_ledgers_with_exchange(
                    session,
                    bot_session,
                    adapter,
                    ledgers,
                )
                if ledgers:
                    await self._close_ledgers(
                        session,
                        bot_session,
                        adapter,
                        ledgers,
                        0,
                        "Stopped by user",
                    )
            except Exception:
                bot_session.status_message = "Stopped locally; remote close-all may require review"
                logger.exception("Bot stop close-out failed")
            finally:
                if adapter is not None:
                    await adapter.close()

    async def _run_loop(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        user_id: str,
        session_id: str,
    ) -> None:
        settings = get_settings()
        adapter = None
        try:
            async with session_factory() as session:
                bot_session = await session.get(BotSession, session_id)
                if not bot_session or bot_session.status != "running":
                    return
                _, adapter = await self._load_runtime_dependencies(session, bot_session)
                await adapter.initialize()

            while True:
                async with session_factory() as session:
                    bot_session = await session.get(BotSession, session_id)
                    if not bot_session or bot_session.status != "running":
                        return

                    try:
                        await self._execute_cycle(session, bot_session, adapter)
                        if bot_session.status == "running" and not bot_session.status_message:
                            bot_session.status_message = "Healthy"
                        bot_session.last_heartbeat = datetime.now(timezone.utc)
                        await session.commit()
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        bot_session.status_message = f"Cycle error: {exc}"
                        logger.exception(
                            "Bot cycle failed",
                            extra={
                                "user_id": bot_session.user_id,
                                "session_id": bot_session.id,
                                "exchange": bot_session.exchange,
                                "use_testnet": bot_session.use_testnet,
                            },
                        )
                        await session.commit()

                event = self._wake_events.setdefault(user_id, asyncio.Event())
                try:
                    await asyncio.wait_for(event.wait(), timeout=settings.bot_poll_seconds)
                except asyncio.TimeoutError:
                    pass
                finally:
                    event.clear()
        finally:
            if adapter is not None:
                await adapter.close()

    async def _execute_cycle(self, session: AsyncSession, bot_session: BotSession, adapter) -> None:
        strategy = get_strategy(bot_session.strategy_id)
        config = bot_session.config
        symbol = config["symbol"]
        timeframe = config["timeframe"]
        leverage = float(config["leverage"])
        position_size_pct = float(config["position_size_pct"])
        stop_loss_pct = float(config["stop_loss_pct"])
        take_profit_pct = float(config["take_profit_pct"])
        max_drawdown_pct = float(config["max_drawdown_pct"])
        max_order_notional = float(config.get("max_order_notional_usdt") or 1000)
        max_position_notional = float(config.get("max_position_notional_usdt") or 3000)

        try:
            await adapter.set_leverage(symbol, leverage)

            balance_payload = await adapter.fetch_balance()
            total_equity = extract_account_equity(balance_payload)
            bot_session.peak_balance = max(bot_session.peak_balance or 0, total_equity)

            candles = await adapter.fetch_ohlcv(symbol, timeframe, strategy.candle_limit)
            if self._is_candle_stale(candles, timeframe):
                bot_session.status_message = "Market data is stale; skipped opening"
                return

            symbol_rules = await self._resolve_runtime_rules(
                session,
                bot_session.exchange,
                symbol,
                adapter,
                allow_stale_on_failure=False,
            )
            if symbol_rules is None:
                bot_session.status_message = "Current symbol is temporarily unavailable; skipped opening"
                return

            ticker = await adapter.fetch_ticker(symbol)
            last_price = float(ticker.get("last") or ticker.get("close") or candles[-1][4])

            ledgers = await self._load_ledgers(session, bot_session)
            ledgers = await self._reconcile_ledgers_with_exchange(
                session,
                bot_session,
                adapter,
                ledgers,
            )
            if await self._apply_runtime_risk_controls(
                session,
                bot_session,
                adapter,
                ledgers,
                last_price,
                total_equity,
                stop_loss_pct,
                take_profit_pct,
                max_drawdown_pct,
            ):
                account_sync_service.request_refresh()
                return

            if await self._reconcile_open_orders(bot_session, adapter, symbol):
                return

            strategy_state = config.get("strategy_state") if isinstance(config.get("strategy_state"), dict) else {}
            signal = strategy.calculate_signal(
                StrategyContext(
                    candles=candles,
                    positions=self._build_strategy_positions(ledgers),
                    config=dict(config),
                    state=dict(strategy_state or {}),
                )
            )
            bot_session.config = {
                **bot_session.config,
                "strategy_state": dict(signal.state or {}),
            }

            current_bot_side = self._get_current_bot_side(ledgers)
            if current_bot_side == "hedged":
                bot_session.status_message = "Bot-managed position is not one-way; manual review required"
                return

            if signal.intent == "open":
                if signal.side is None:
                    bot_session.status_message = "Strategy signal is missing a direction"
                    return
                if current_bot_side and current_bot_side != signal.side:
                    bot_session.status_message = (
                        "Existing bot position is on the opposite side; close it before opening a new direction"
                    )
                    return

                current_side_notional = self._calculate_side_notional(
                    ledgers,
                    signal.side,
                    last_price,
                    symbol_rules,
                )
                if current_side_notional >= max_position_notional * POSITION_CAP_SKIP_RATIO:
                    bot_session.status_message = "Position cap reached; skipped opening"
                    return

                target_notional = self._calculate_target_notional(
                    total_equity,
                    leverage,
                    signal.target_exposure_pct or position_size_pct,
                )
                remaining_notional = max(max_position_notional - current_side_notional, 0)
                desired_notional = min(max(target_notional - current_side_notional, 0), remaining_notional)
                if desired_notional <= 0:
                    bot_session.status_message = "Signal target already satisfied; skipped opening"
                    return

                await self._execute_batched_entry(
                    session,
                    bot_session,
                    adapter,
                    symbol=symbol,
                    order_side="buy" if signal.side == "long" else "sell",
                    ledger_side=signal.side,
                    last_price=last_price,
                    symbol_rules=symbol_rules,
                    target_notional=desired_notional,
                    max_order_notional=max_order_notional,
                )
            elif signal.intent == "reduce":
                if signal.side is None or current_bot_side != signal.side:
                    bot_session.status_message = "Reduce signal ignored because no same-side bot position exists"
                    return
                current_side_notional = self._calculate_side_notional(
                    ledgers,
                    signal.side,
                    last_price,
                    symbol_rules,
                )
                target_notional = self._calculate_target_notional(
                    total_equity,
                    leverage,
                    signal.target_exposure_pct,
                )
                close_notional = max(current_side_notional - target_notional, 0)
                if close_notional <= 0:
                    bot_session.status_message = "Reduce target already satisfied"
                    return
                contract_size = self._get_contract_size(symbol_rules)
                close_quantity = close_notional / max(last_price * contract_size, 1e-9)
                target_ledgers = [ledger for ledger in ledgers if ledger.side == signal.side]
                await self._close_ledgers(
                    session,
                    bot_session,
                    adapter,
                    target_ledgers,
                    last_price,
                    signal.reason,
                    close_quantities=self._build_partial_close_quantities(
                        target_ledgers,
                        close_quantity,
                    ),
                )
            elif signal.intent == "close":
                target_ledgers = [
                    ledger for ledger in ledgers if signal.side is None or ledger.side == signal.side
                ]
                if target_ledgers:
                    await self._close_ledgers(
                        session,
                        bot_session,
                        adapter,
                        target_ledgers,
                        last_price,
                        signal.reason,
                    )

            ledgers = await self._load_ledgers(session, bot_session)
            exposure, unrealized = self._calculate_ledger_metrics(
                ledgers,
                last_price,
                symbol_rules,
            )
            bot_session.balance = total_equity
            bot_session.unrealized_pnl = unrealized
            bot_session.exposure = exposure
            if bot_session.status_message == "Healthy":
                bot_session.status_message = None
        finally:
            account_sync_service.request_refresh()

    async def _prepare_runtime(self, session: AsyncSession, bot_session: BotSession) -> None:
        _, adapter = await self._load_runtime_dependencies(session, bot_session)
        symbol = bot_session.config["symbol"]
        leverage = float(bot_session.config["leverage"])

        try:
            await adapter.initialize()
            rules = await self._resolve_runtime_rules(
                session,
                bot_session.exchange,
                symbol,
                adapter,
                allow_stale_on_failure=False,
            )
            if rules is None:
                raise RuntimeError("Selected symbol is temporarily unavailable")
            await adapter.set_hedge_mode()
            await adapter.set_leverage(symbol, leverage)
        finally:
            await adapter.close()

    async def _apply_runtime_risk_controls(
        self,
        session: AsyncSession,
        bot_session: BotSession,
        adapter,
        ledgers: list[BotPositionLedger],
        last_price: float,
        total_balance: float,
        stop_loss_pct: float,
        take_profit_pct: float,
        max_drawdown_pct: float,
    ) -> bool:
        if not ledgers:
            return False

        if max_drawdown_pct > 0 and bot_session.peak_balance > 0:
            drawdown_limit = bot_session.peak_balance * (1 - max_drawdown_pct / 100)
            if total_balance <= drawdown_limit:
                await self._close_ledgers(
                    session,
                    bot_session,
                    adapter,
                    ledgers,
                    last_price,
                    "Max drawdown threshold reached",
                )
                bot_session.status = "stopped"
                bot_session.stopped_at = datetime.now(timezone.utc)
                bot_session.status_message = "Max drawdown threshold reached"
                return True

        triggered: list[BotPositionLedger] = []
        for ledger in ledgers:
            if ledger.side == "long":
                stop_price = ledger.entry_price * (1 - stop_loss_pct / 100)
                target_price = ledger.entry_price * (1 + take_profit_pct / 100)
                if last_price <= stop_price or last_price >= target_price:
                    triggered.append(ledger)
            elif ledger.side == "short":
                stop_price = ledger.entry_price * (1 + stop_loss_pct / 100)
                target_price = ledger.entry_price * (1 - take_profit_pct / 100)
                if last_price >= stop_price or last_price <= target_price:
                    triggered.append(ledger)

        if triggered:
            await self._close_ledgers(
                session,
                bot_session,
                adapter,
                triggered,
                last_price,
                "Risk controls closed bot-managed positions",
            )
            return True

        return False

    async def _execute_batched_entry(
        self,
        session: AsyncSession,
        bot_session: BotSession,
        adapter,
        *,
        symbol: str,
        order_side: str,
        ledger_side: str,
        last_price: float,
        symbol_rules: dict,
        target_notional: float,
        max_order_notional: float,
    ) -> None:
        if target_notional <= 0:
            bot_session.status_message = "Target order notional is zero; skipped opening"
            return

        contract_size = self._get_contract_size(symbol_rules)
        entry_notional = min(target_notional, max_order_notional)
        desired_amount = entry_notional / max(last_price * contract_size, 1e-9)
        normalized = adapter.normalize_order_amount(
            symbol,
            desired_amount,
            price=last_price,
            rules=symbol_rules,
        )
        if not normalized["ok"]:
            bot_session.status_message = normalized["reason"]
            return

        client_order_id = self._build_client_order_id()
        order = await self._create_order_with_retry(
            adapter,
            symbol=symbol,
            side=order_side,
            amount=float(normalized["amount"]),
            pos_side=ledger_side,
            client_order_id=client_order_id,
        )
        fill_amount = self._extract_order_quantity(order, float(normalized["amount"]))
        fill_price = self._extract_order_price(order, last_price)
        await self._record_trade(
            session,
            bot_session,
            symbol=symbol,
            side=order_side,
            quantity=fill_amount,
            price=fill_price,
            realized_pnl=None,
            raw_payload=order,
            client_order_id=client_order_id,
        )
        await self._upsert_ledger(
            session,
            bot_session,
            symbol=symbol,
            side=ledger_side,
            quantity=fill_amount,
            price=fill_price,
        )

    async def _close_ledgers(
        self,
        session: AsyncSession,
        bot_session: BotSession,
        adapter,
        ledgers: list[BotPositionLedger],
        last_price: float,
        reason: str,
        close_quantities: dict[str, float] | None = None,
    ) -> None:
        max_order_notional = float(bot_session.config.get("max_order_notional_usdt") or 1000)
        symbol_rules = await self._resolve_runtime_rules(
            session,
            bot_session.exchange,
            bot_session.config["symbol"],
            adapter,
            allow_stale_on_failure=True,
        )
        if symbol_rules is None:
            bot_session.status_message = "Unable to close bot-managed positions right now"
            logger.warning(
                "Missing runtime rules during ledger close",
                extra={
                    "user_id": bot_session.user_id,
                    "session_id": bot_session.id,
                    "exchange": bot_session.exchange,
                    "symbol": bot_session.config.get("symbol"),
                },
            )
            return

        for ledger in list(ledgers):
            reference_price = await self._resolve_close_price(adapter, ledger.symbol, last_price, ledger.entry_price)
            contract_size = self._get_contract_size(symbol_rules)
            target_close_qty = (
                min(abs(ledger.quantity), abs(close_quantities.get(ledger.id, 0.0)))
                if close_quantities is not None
                else abs(ledger.quantity)
            )
            remaining_qty = target_close_qty
            if remaining_qty <= POSITION_RECONCILE_EPSILON:
                continue
            while remaining_qty > 0:
                if reference_price > 0:
                    batch_notional = min(
                        remaining_qty * reference_price * contract_size,
                        max_order_notional,
                    )
                    desired_amount = batch_notional / max(reference_price * contract_size, 1e-9)
                else:
                    desired_amount = remaining_qty
                normalized = adapter.normalize_order_amount(
                    ledger.symbol,
                    min(desired_amount, remaining_qty),
                    price=reference_price,
                    rules=symbol_rules,
                )
                if not normalized["ok"]:
                    remote_sizes = self._collect_remote_position_sizes(
                        await adapter.fetch_positions([ledger.symbol]) or [],
                        ledger.symbol,
                    )
                    remote_qty = remote_sizes.get(ledger.side, 0.0)
                    if remote_qty <= POSITION_RECONCILE_EPSILON:
                        logger.info(
                            "Clearing stale residual ledger after confirmed flat remote position",
                            extra={
                                "user_id": bot_session.user_id,
                                "session_id": bot_session.id,
                                "exchange": bot_session.exchange,
                                "symbol": ledger.symbol,
                                "side": ledger.side,
                                "ledger_qty": ledger.quantity,
                            },
                        )
                        await session.delete(ledger)
                        remaining_qty = 0
                        break
                    if remote_qty + POSITION_RECONCILE_EPSILON < remaining_qty:
                        ledger.quantity = remote_qty
                        remaining_qty = remote_qty
                        continue
                    residual_message = (
                        "Stopped with residual bot position below exchange minimum order size; "
                        "manual review may be required"
                    )
                    if bot_session.status_message != residual_message:
                        logger.info(
                            "Skipped ledger close during stop due to order normalization",
                            extra={
                                "user_id": bot_session.user_id,
                                "session_id": bot_session.id,
                                "exchange": bot_session.exchange,
                                "symbol": ledger.symbol,
                                "side": ledger.side,
                                "remaining_qty": remaining_qty,
                                "reason": normalized["reason"],
                                "reference_price": reference_price,
                            },
                        )
                    bot_session.status_message = residual_message
                    break

                close_side = "sell" if ledger.side == "long" else "buy"
                client_order_id = self._build_client_order_id()
                order = await self._create_order_with_retry(
                    adapter,
                    symbol=ledger.symbol,
                    side=close_side,
                    amount=float(normalized["amount"]),
                    reduce_only=True,
                    pos_side=ledger.side,
                    client_order_id=client_order_id,
                )
                fill_amount = abs(self._extract_order_quantity(order, float(normalized["amount"])))
                fill_price = self._extract_order_price(order, reference_price or ledger.entry_price)
                realized_pnl = self._calculate_realized_pnl(ledger, fill_amount, fill_price, symbol_rules)
                await self._record_trade(
                    session,
                    bot_session,
                    symbol=ledger.symbol,
                    side="close",
                    quantity=fill_amount,
                    price=fill_price,
                    realized_pnl=realized_pnl,
                    raw_payload={**order, "reason": reason},
                    client_order_id=client_order_id,
                )
                remaining_qty = max(remaining_qty - fill_amount, 0)
                residual_ledger_qty = max(abs(ledger.quantity) - fill_amount, 0)
                if residual_ledger_qty <= 0:
                    await session.delete(ledger)
                else:
                    ledger.quantity = residual_ledger_qty

    async def _resolve_close_price(
        self,
        adapter,
        symbol: str,
        last_price: float,
        fallback_price: float,
    ) -> float:
        if last_price and last_price > 0:
            return float(last_price)
        try:
            ticker = await adapter.fetch_ticker(symbol)
            ticker_price = float(ticker.get("last") or ticker.get("close") or 0)
            if ticker_price > 0:
                return ticker_price
        except Exception:
            logger.warning("Failed to fetch ticker for stop close-out", exc_info=True)
        return float(fallback_price or 0)

    async def _create_order_with_retry(
        self,
        adapter,
        *,
        symbol: str,
        side: str,
        amount: float,
        reduce_only: bool = False,
        pos_side: str | None = None,
        client_order_id: str,
    ) -> dict:
        last_error: Exception | None = None
        for attempt in range(BATCH_RETRY_TIMES + 1):
            try:
                return await adapter.create_market_order(
                    symbol,
                    side,
                    amount,
                    reduce_only=reduce_only,
                    pos_side=pos_side,
                    client_order_id=client_order_id,
                )
            except Exception as exc:  # noqa: PERF203
                last_error = exc
                if attempt >= BATCH_RETRY_TIMES:
                    break
                await asyncio.sleep(BATCH_RETRY_DELAY_SECONDS)
        raise RuntimeError(f"Order failed after retries: {last_error}") from last_error

    async def _reconcile_open_orders(
        self,
        bot_session: BotSession,
        adapter,
        symbol: str,
    ) -> bool:
        try:
            open_orders = await adapter.fetch_open_orders(symbol)
        except Exception:
            return False

        relevant = [
            order
            for order in open_orders
            if str(order.get("clientOrderId") or order.get("clOrdId") or "").startswith("helix")
        ]
        if not relevant:
            return False

        for order in relevant:
            order_id = order.get("id")
            if order_id:
                try:
                    await adapter.cancel_order(order_id, symbol)
                except Exception:
                    logger.exception("Failed to cancel stale open order during reconcile")
        bot_session.status_message = "Pending orders reconciled; skipped this cycle"
        return True

    async def _record_trade(
        self,
        session: AsyncSession,
        bot_session: BotSession,
        *,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        realized_pnl: float | None,
        raw_payload: dict,
        client_order_id: str,
    ) -> None:
        session.add(
            TradeRecord(
                user_id=bot_session.user_id,
                session_id=bot_session.id,
                strategy_id=bot_session.strategy_id,
                exchange=bot_session.exchange,
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                realized_pnl=realized_pnl,
                raw_payload=raw_payload,
                client_order_id=client_order_id,
                bot_tag=BOT_TAG,
            )
        )

    async def _upsert_ledger(
        self,
        session: AsyncSession,
        bot_session: BotSession,
        *,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
    ) -> None:
        result = await session.execute(
            select(BotPositionLedger).where(
                BotPositionLedger.user_id == bot_session.user_id,
                BotPositionLedger.exchange == bot_session.exchange,
                BotPositionLedger.symbol == symbol,
                BotPositionLedger.side == side,
            )
        )
        ledger = result.scalar_one_or_none()
        if ledger is None:
            ledger = BotPositionLedger(
                user_id=bot_session.user_id,
                session_id=bot_session.id,
                exchange=bot_session.exchange,
                symbol=symbol,
                side=side,
                quantity=quantity,
                entry_price=price,
                bot_tag=BOT_TAG,
            )
            session.add(ledger)
            return

        total_quantity = ledger.quantity + quantity
        if total_quantity <= 0:
            await session.delete(ledger)
            return

        ledger.entry_price = (
            (ledger.entry_price * ledger.quantity) + (price * quantity)
        ) / total_quantity
        ledger.quantity = total_quantity
        ledger.session_id = bot_session.id

    async def _load_ledgers(
        self, session: AsyncSession, bot_session: BotSession
    ) -> list[BotPositionLedger]:
        result = await session.execute(
            select(BotPositionLedger)
            .where(
                BotPositionLedger.user_id == bot_session.user_id,
                BotPositionLedger.exchange == bot_session.exchange,
                BotPositionLedger.symbol == bot_session.config["symbol"],
                BotPositionLedger.quantity > 0,
            )
            .order_by(BotPositionLedger.updated_at.desc())
        )
        return result.scalars().all()

    def _build_strategy_positions(
        self,
        ledgers: list[BotPositionLedger],
    ) -> list[StrategyPosition]:
        return [
            StrategyPosition(
                symbol=ledger.symbol,
                side=ledger.side,
                quantity=ledger.quantity,
                entry_price=ledger.entry_price,
            )
            for ledger in ledgers
        ]

    def _get_current_bot_side(
        self,
        ledgers: list[BotPositionLedger],
    ) -> str | None:
        sides = {ledger.side for ledger in ledgers if ledger.quantity > POSITION_RECONCILE_EPSILON}
        if len(sides) > 1:
            return "hedged"
        return next(iter(sides), None)

    def _calculate_target_notional(
        self,
        total_equity: float,
        leverage: float,
        target_exposure_pct: float | None,
    ) -> float:
        if not target_exposure_pct or target_exposure_pct <= 0:
            return 0.0
        return total_equity * (target_exposure_pct / 100) * leverage

    def _build_partial_close_quantities(
        self,
        ledgers: list[BotPositionLedger],
        close_quantity: float,
    ) -> dict[str, float]:
        remaining = max(close_quantity, 0.0)
        close_quantities: dict[str, float] = {}
        for ledger in ledgers:
            if remaining <= POSITION_RECONCILE_EPSILON:
                break
            ledger_close_qty = min(abs(ledger.quantity), remaining)
            if ledger_close_qty <= POSITION_RECONCILE_EPSILON:
                continue
            close_quantities[ledger.id] = ledger_close_qty
            remaining -= ledger_close_qty
        return close_quantities

    def _calculate_ledger_metrics(
        self,
        ledgers: list[BotPositionLedger],
        last_price: float,
        symbol_rules: dict,
    ) -> tuple[float, float]:
        exposure = 0.0
        unrealized = 0.0
        for ledger in ledgers:
            contract_size = self._get_contract_size(symbol_rules)
            exposure += abs(ledger.quantity) * last_price * contract_size
            if ledger.side == "long":
                unrealized += (
                    (last_price - ledger.entry_price) * ledger.quantity * contract_size
                )
            else:
                unrealized += (
                    (ledger.entry_price - last_price) * ledger.quantity * contract_size
                )
        return exposure, unrealized

    def _calculate_side_notional(
        self,
        ledgers: list[BotPositionLedger],
        side: str,
        last_price: float,
        symbol_rules: dict,
    ) -> float:
        return sum(
            abs(ledger.quantity) * last_price * self._get_contract_size(symbol_rules)
            for ledger in ledgers
            if ledger.side == side
        )

    def _calculate_realized_pnl(
        self,
        ledger: BotPositionLedger,
        quantity: float,
        close_price: float,
        symbol_rules: dict,
    ) -> float:
        contract_size = self._get_contract_size(symbol_rules)
        if ledger.side == "long":
            return (close_price - ledger.entry_price) * quantity * contract_size
        return (ledger.entry_price - close_price) * quantity * contract_size

    def _get_contract_size(self, symbol_rules: dict) -> float:
        contract_size = float(symbol_rules.get("contract_size") or 0)
        if contract_size <= 0:
            return 1.0
        return contract_size

    async def _resolve_runtime_rules(
        self,
        session: AsyncSession,
        exchange: str,
        symbol: str,
        adapter,
        *,
        allow_stale_on_failure: bool,
    ) -> dict | None:
        rules = await market_catalog_service.get_runtime_rules(session, exchange, symbol)
        if market_catalog_service.is_runtime_rules_fresh(
            rules,
            max_age=timedelta(minutes=MARKET_RULE_STALE_MINUTES),
        ):
            return rules

        try:
            fallback_rules = await adapter.fetch_market_rules(symbol, reload=rules is not None)
            fallback_rules["synced_at"] = datetime.now(timezone.utc)
            stored_rules = await market_catalog_service.upsert_runtime_rules(
                session,
                exchange,
                fallback_rules,
            )
            return stored_rules
        except Exception:
            logger.exception(
                "Failed to refresh runtime market rules",
                extra={"exchange": exchange, "symbol": symbol},
            )
            if allow_stale_on_failure and rules is not None:
                return rules
            return None

    def _extract_order_quantity(self, order: dict, fallback_amount: float) -> float:
        for key in ("filled", "amount"):
            value = order.get(key)
            try:
                if value is not None and float(value) > 0:
                    return float(value)
            except (TypeError, ValueError):
                continue
        return float(fallback_amount)

    def _extract_order_price(self, order: dict, fallback_price: float) -> float:
        for key in ("average", "price"):
            value = order.get(key)
            try:
                if value is not None and float(value) > 0:
                    return float(value)
            except (TypeError, ValueError):
                continue
        return float(fallback_price)

    def _is_candle_stale(self, candles: list[list[float]], timeframe: str) -> bool:
        if not candles:
            return True
        last_candle_ms = int(candles[-1][0])
        last_candle_time = datetime.fromtimestamp(last_candle_ms / 1000, tz=timezone.utc)
        return last_candle_time < datetime.now(timezone.utc) - timedelta(
            seconds=self._timeframe_to_seconds(timeframe) * 3
        )

    def _timeframe_to_seconds(self, timeframe: str) -> int:
        value = int(timeframe[:-1])
        unit = timeframe[-1]
        if unit == "m":
            return value * 60
        if unit == "h":
            return value * 3600
        if unit == "d":
            return value * 86400
        return 900

    def _build_client_order_id(self) -> str:
        return f"helix{uuid4().hex[:20]}"

    async def _load_runtime_dependencies(
        self, session: AsyncSession, bot_session: BotSession
    ) -> tuple[ApiCredential, object]:
        credential_result = await session.execute(
            select(ApiCredential).where(
                ApiCredential.user_id == bot_session.user_id,
                ApiCredential.exchange == bot_session.exchange,
            )
        )
        credential = credential_result.scalar_one_or_none()
        if credential is None:
            raise RuntimeError("No API credentials available for this exchange")

        adapter = build_exchange_adapter(
            exchange=credential.exchange,
            api_key=self._encryption.decrypt(credential.api_key_encrypted),
            api_secret=self._encryption.decrypt(credential.api_secret_encrypted),
            passphrase=(
                self._encryption.decrypt(credential.passphrase_encrypted)
                if credential.passphrase_encrypted
                else None
            ),
            use_testnet=bot_session.use_testnet,
            market_type=bot_session.market_type,
        )
        return credential, adapter


bot_manager = BotManager()
