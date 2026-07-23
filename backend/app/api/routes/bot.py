from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import OperationalError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import SessionLocal, get_db
from app.models import (
    AccountSnapshot,
    ApiCredential,
    BotPositionLedger,
    BotSession,
    StrategyDefinition,
    TradeRecord,
    User,
)
from app.schemas.bot import (
    BotStatusResponse,
    MarketSymbolResponse,
    PositionResponse,
    SaveCredentialRequest,
    SaveCredentialResponse,
    StartBotRequest,
    StopBotRequest,
    TradeResponse,
    UpdateBotConfigRequest,
    UpdateBotConfigResponse,
)
from app.services.account_sync import account_sync_service
from app.services.bot_manager import bot_manager
from app.services.encryption import EncryptionService, mask_api_key
from app.services.market_catalog import market_catalog_service


router = APIRouter(prefix="/api/bot", tags=["bot"])
encryption_service = EncryptionService()
DEFAULT_SYMBOL = "BTC/USDT:USDT"
ACTIVE_TOUCH_INTERVAL = timedelta(seconds=30)


async def _resolve_runtime_position_side(
    db: AsyncSession,
    current_user_id: str,
    session_ref: BotSession | None,
) -> str | None:
    if session_ref is None:
        return None
    symbol = str((session_ref.config or {}).get("symbol") or session_ref.runtime_symbol or DEFAULT_SYMBOL)
    result = await db.execute(
        select(BotPositionLedger).where(
            BotPositionLedger.user_id == current_user_id,
            BotPositionLedger.exchange == session_ref.exchange,
            BotPositionLedger.symbol == symbol,
            BotPositionLedger.quantity > 0,
        )
    )
    ledgers = result.scalars().all()
    sides = {ledger.side for ledger in ledgers if ledger.quantity > 0}
    if len(sides) > 1:
        return "hedged"
    return next(iter(sides), None)


@router.post("/credentials", response_model=SaveCredentialResponse)
async def save_credentials(
    payload: SaveCredentialRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SaveCredentialResponse:
    result = await db.execute(
        select(ApiCredential).where(ApiCredential.user_id == current_user.id)
    )
    credentials = result.scalars().all()
    credential = next(
        (item for item in credentials if item.exchange == payload.exchange),
        None,
    )
    masked = mask_api_key(payload.api_key)

    for existing in credentials:
        if existing.exchange != payload.exchange:
            await db.delete(existing)

    if credential is None:
        credential = ApiCredential(
            user_id=current_user.id,
            exchange=payload.exchange,
            api_key_encrypted="",
            api_secret_encrypted="",
            masked_api_key=masked,
        )
        db.add(credential)

    credential.api_key_encrypted = encryption_service.encrypt(payload.api_key)
    credential.api_secret_encrypted = encryption_service.encrypt(payload.api_secret)
    credential.passphrase_encrypted = (
        encryption_service.encrypt(payload.passphrase) if payload.passphrase else None
    )
    credential.masked_api_key = masked
    credential.use_testnet = payload.use_testnet
    credential.sync_status = "active"
    credential.sync_error = None
    credential.last_error_at = None
    credential.last_seen_at = datetime.now(timezone.utc)
    await db.commit()
    await account_sync_service.sync_user(SessionLocal, current_user.id, payload.exchange)

    return SaveCredentialResponse(masked_api_key=masked)


@router.post("/start")
async def start_bot(
    payload: StartBotRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if bot_manager.is_stopping(current_user.id):
        raise HTTPException(status_code=409, detail="Bot is stopping; wait until close-out completes")

    strategy_result = await db.execute(
        select(StrategyDefinition).where(StrategyDefinition.id == payload.strategy_id)
    )
    strategy = strategy_result.scalar_one_or_none()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    credential_result = await db.execute(
        select(ApiCredential)
        .where(ApiCredential.user_id == current_user.id)
        .order_by(ApiCredential.updated_at.desc())
    )
    credential = credential_result.scalars().first()
    if credential is None:
        raise HTTPException(status_code=400, detail="Save exchange credentials first")
    if credential.sync_status in {"decrypt_failed", "auth_failed"}:
        raise HTTPException(
            status_code=400,
            detail=credential.sync_error or "Please re-save or verify this credential",
        )
    market = await market_catalog_service.get_symbol(db, credential.exchange, payload.symbol)
    if market is None:
        raise HTTPException(status_code=400, detail="Selected symbol is unavailable")

    merged_config = {
        **strategy.default_params,
        "symbol": payload.symbol,
        "leverage": payload.leverage,
        "position_size_pct": payload.position_size_pct,
        "stop_loss_pct": payload.stop_loss_pct,
        "take_profit_pct": payload.take_profit_pct,
        "max_drawdown_pct": payload.max_drawdown_pct,
        "max_order_notional_usdt": payload.max_order_notional_usdt,
        "max_position_notional_usdt": payload.max_position_notional_usdt,
    }

    latest_result = await db.execute(
        select(BotSession)
        .where(BotSession.user_id == current_user.id)
        .where(BotSession.status == "running")
        .order_by(BotSession.started_at.desc())
    )
    latest_session = latest_result.scalars().first()
    if latest_session is not None or bot_manager.is_running(current_user.id):
        raise HTTPException(status_code=409, detail="Bot is already running")

    bot_session = BotSession(
        user_id=current_user.id,
        strategy_id=strategy.id,
        exchange=credential.exchange,
        market_type=payload.market_type,
        status="running",
        config=merged_config,
        runtime_symbol=payload.symbol,
        close_all_on_stop=payload.close_all_on_stop,
        use_testnet=credential.use_testnet,
        status_message="Launching",
    )
    db.add(bot_session)
    await db.commit()
    await db.refresh(bot_session)

    try:
        await bot_manager.start_bot(SessionLocal, current_user.id, bot_session.id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"detail": "Bot started", "session_id": bot_session.id}


@router.get("/markets", response_model=list[MarketSymbolResponse])
async def get_markets(
    exchange: str,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MarketSymbolResponse]:
    symbols = await market_catalog_service.list_symbols(db, exchange)
    return [
        MarketSymbolResponse(
            symbol=item.symbol,
            base=item.base,
            quote=item.quote,
            min_qty=item.min_qty,
            min_notional=item.min_notional,
            qty_precision=item.qty_precision,
            price_precision=item.price_precision,
        )
        for item in symbols
    ]


@router.patch("/config", response_model=UpdateBotConfigResponse)
async def update_bot_config(
    payload: UpdateBotConfigRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UpdateBotConfigResponse:
    result = await db.execute(
        select(BotSession)
        .where(
            BotSession.user_id == current_user.id,
            BotSession.status == "running",
        )
        .order_by(BotSession.started_at.desc())
    )
    bot_session = result.scalars().first()
    if bot_session is None:
        raise HTTPException(status_code=400, detail="No running bot session")

    bot_session.config = {
        **bot_session.config,
        "leverage": payload.leverage,
        "position_size_pct": payload.position_size_pct,
        "stop_loss_pct": payload.stop_loss_pct,
        "take_profit_pct": payload.take_profit_pct,
        "max_drawdown_pct": payload.max_drawdown_pct,
        "max_order_notional_usdt": payload.max_order_notional_usdt,
        "max_position_notional_usdt": payload.max_position_notional_usdt,
    }
    if payload.close_all_on_stop is not None:
        bot_session.close_all_on_stop = payload.close_all_on_stop
    bot_session.status_message = "Config updated; applying on next cycle"
    await db.commit()

    bot_manager.request_immediate_cycle(current_user.id)
    return UpdateBotConfigResponse(detail="Config applied", config=bot_session.config)


@router.post("/stop")
async def stop_bot(
    payload: StopBotRequest,
    current_user: User = Depends(get_current_user),
    _: AsyncSession = Depends(get_db),
) -> dict:
    detail = await bot_manager.stop_bot(SessionLocal, current_user.id, payload.close_all)
    return {"detail": detail}


@router.get("/status", response_model=BotStatusResponse)
async def get_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BotStatusResponse:
    is_stopping = bot_manager.is_stopping(current_user.id)
    session_result = await db.execute(
        select(BotSession)
        .where(
            BotSession.user_id == current_user.id,
            BotSession.status == "running",
        )
        .order_by(BotSession.started_at.desc())
    )
    bot_session = session_result.scalars().first()
    latest_session_result = await db.execute(
        select(BotSession)
        .where(BotSession.user_id == current_user.id)
        .order_by(BotSession.started_at.desc())
    )
    latest_session = latest_session_result.scalars().first()

    credential_result = await db.execute(
        select(ApiCredential)
        .where(ApiCredential.user_id == current_user.id)
        .order_by(ApiCredential.updated_at.desc())
    )
    credential = credential_result.scalars().first()
    if credential is not None:
        last_seen_at = credential.last_seen_at
        if last_seen_at is None or (
            (last_seen_at.replace(tzinfo=timezone.utc) if last_seen_at.tzinfo is None else last_seen_at)
            <= datetime.now(timezone.utc) - ACTIVE_TOUCH_INTERVAL
        ):
            try:
                await account_sync_service.mark_user_active(
                    SessionLocal,
                    current_user.id,
                    credential.exchange,
                )
            except OperationalError:
                pass

    snapshot_exchange = bot_session.exchange if bot_session else credential.exchange if credential else None
    snapshot = None
    if snapshot_exchange is not None:
        snapshot_result = await db.execute(
            select(AccountSnapshot).where(
                AccountSnapshot.user_id == current_user.id,
                AccountSnapshot.exchange == snapshot_exchange,
            )
        )
        snapshot = snapshot_result.scalar_one_or_none()

    position_side_source = bot_session or latest_session
    runtime_position_side = await _resolve_runtime_position_side(
        db,
        current_user.id,
        position_side_source,
    )

    if bot_session is None:
        selected_symbol = (
            latest_session.config.get("symbol")
            if latest_session and latest_session.config
            else DEFAULT_SYMBOL
        )
        return BotStatusResponse(
            status="stopped",
            strategy_id=latest_session.strategy_id if latest_session else None,
            is_stopping=is_stopping,
            exchange=credential.exchange if credential else None,
            runtime_symbol=latest_session.runtime_symbol if latest_session else None,
            runtime_position_side=runtime_position_side,
            selected_symbol=selected_symbol,
            masked_api_key=credential.masked_api_key if credential else None,
            credential_status=credential.sync_status if credential else None,
            credential_error=credential.sync_error if credential else None,
            use_testnet=credential.use_testnet if credential else None,
            status_message=latest_session.status_message if latest_session else None,
            account_status_message=snapshot.status_message if snapshot else None,
            last_synced_at=snapshot.synced_at if snapshot else None,
            close_all_on_stop=latest_session.close_all_on_stop if latest_session else True,
            active_config=latest_session.config if latest_session else {"symbol": selected_symbol},
            balance=snapshot.balance if snapshot else 0,
            unrealized_pnl=snapshot.unrealized_pnl if snapshot else 0,
            exposure=snapshot.exposure if snapshot else 0,
            positions=[
                PositionResponse(
                    symbol=position["symbol"],
                    side=position["side"],
                    size=float(position["size"]),
                    entry_price=float(position["entry_price"]),
                )
                for position in (snapshot.positions if snapshot else [])
            ],
        )

    if credential is None or credential.exchange != bot_session.exchange:
        credential_result = await db.execute(
            select(ApiCredential).where(
                ApiCredential.user_id == current_user.id,
                ApiCredential.exchange == bot_session.exchange,
            )
        )
        credential = credential_result.scalar_one_or_none()

    return BotStatusResponse(
        status=bot_session.status,
        strategy_id=bot_session.strategy_id,
        is_stopping=is_stopping,
        exchange=bot_session.exchange,
        runtime_symbol=bot_session.runtime_symbol or bot_session.config.get("symbol"),
        runtime_position_side=runtime_position_side,
        selected_symbol=bot_session.runtime_symbol or bot_session.config.get("symbol"),
        masked_api_key=credential.masked_api_key if credential else None,
        credential_status=credential.sync_status if credential else None,
        credential_error=credential.sync_error if credential else None,
        use_testnet=credential.use_testnet if credential else bot_session.use_testnet,
        status_message=bot_session.status_message,
        account_status_message=snapshot.status_message if snapshot else None,
        last_synced_at=snapshot.synced_at if snapshot else None,
        close_all_on_stop=bot_session.close_all_on_stop,
        active_config=bot_session.config,
        balance=snapshot.balance if snapshot else bot_session.balance,
        unrealized_pnl=snapshot.unrealized_pnl if snapshot else bot_session.unrealized_pnl,
        exposure=snapshot.exposure if snapshot else bot_session.exposure,
        positions=[
            PositionResponse(
                symbol=position["symbol"],
                side=position["side"],
                size=float(position["size"]),
                entry_price=float(position["entry_price"]),
            )
            for position in (snapshot.positions if snapshot else [])
        ],
    )


@router.get("/trades", response_model=list[TradeResponse])
async def get_trades(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TradeResponse]:
    result = await db.execute(
        select(TradeRecord)
        .where(TradeRecord.user_id == current_user.id)
        .order_by(TradeRecord.created_at.desc())
        .limit(20)
    )
    trades = result.scalars().all()
    return [
        TradeResponse(
            id=trade.id,
            symbol=trade.symbol,
            side=trade.side,
            price=trade.price,
            quantity=trade.quantity,
            realized_pnl=trade.realized_pnl,
            created_at=trade.created_at,
        )
        for trade in trades
    ]
