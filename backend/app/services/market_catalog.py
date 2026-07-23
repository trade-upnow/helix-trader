from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import ccxt.async_support as ccxt
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.models import MarketSymbolCatalog

logger = logging.getLogger(__name__)
SYNC_INTERVAL = timedelta(minutes=30)
SUPPORTED_EXCHANGES = ("binance", "okx")


class MarketCatalogService:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._rules_cache: dict[tuple[str, str], dict[str, Any]] = {}

    async def start(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(session_factory))

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def sync_now(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        await self._sync_all(session_factory)

    async def list_symbols(
        self, session: AsyncSession, exchange: str
    ) -> list[MarketSymbolCatalog]:
        result = await session.execute(
            select(MarketSymbolCatalog)
            .where(
                MarketSymbolCatalog.exchange == exchange,
                MarketSymbolCatalog.is_active.is_(True),
            )
            .order_by(MarketSymbolCatalog.symbol.asc())
        )
        rows = result.scalars().all()
        for row in rows:
            self._rules_cache[(row.exchange, row.symbol)] = self._row_to_rules(row)
        return rows

    async def get_symbol(
        self, session: AsyncSession, exchange: str, symbol: str
    ) -> MarketSymbolCatalog | None:
        result = await session.execute(
            select(MarketSymbolCatalog).where(
                MarketSymbolCatalog.exchange == exchange,
                MarketSymbolCatalog.symbol == symbol,
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            self._rules_cache[(exchange, symbol)] = self._row_to_rules(row)
        return row

    async def get_runtime_rules(
        self,
        session: AsyncSession,
        exchange: str,
        symbol: str,
    ) -> dict[str, Any] | None:
        cached = self._rules_cache.get((exchange, symbol))
        if cached is not None:
            return dict(cached)

        row = await self.get_symbol(session, exchange, symbol)
        if row is None or not row.is_active:
            return None
        return self._row_to_rules(row)

    def is_runtime_rules_fresh(
        self,
        rules: dict[str, Any] | None,
        *,
        max_age: timedelta,
    ) -> bool:
        if not rules:
            return False
        synced_at = rules.get("synced_at")
        if synced_at is None:
            return False
        if synced_at.tzinfo is None:
            synced_at = synced_at.replace(tzinfo=timezone.utc)
        return synced_at >= datetime.now(timezone.utc) - max_age

    async def upsert_runtime_rules(
        self,
        session: AsyncSession,
        exchange: str,
        rules: dict[str, Any],
    ) -> dict[str, Any]:
        symbol = str(rules.get("symbol") or "")
        if not symbol:
            raise ValueError("Symbol is required to upsert runtime rules")

        base, quote = self._infer_base_quote(symbol)
        normalized = {
            "exchange": exchange,
            "symbol": symbol,
            "base": str(rules.get("base") or base),
            "quote": str(rules.get("quote") or quote),
            "market_type": str(rules.get("market_type") or "swap"),
            "contract_size": float(rules.get("contract_size") or 1),
            "min_qty": float(rules.get("min_qty") or 0),
            "min_notional": float(rules.get("min_notional") or 0),
            "qty_precision": self._normalize_precision_value(rules.get("qty_precision")),
            "price_precision": self._normalize_precision_value(rules.get("price_precision")),
            "is_active": True,
            "synced_at": rules.get("synced_at") or datetime.now(timezone.utc),
        }

        row = await self.get_symbol(session, exchange, symbol)
        if row is None:
            row = MarketSymbolCatalog(**normalized)
            session.add(row)
            await session.flush()
        else:
            row.base = normalized["base"]
            row.quote = normalized["quote"]
            row.market_type = normalized["market_type"]
            row.contract_size = normalized["contract_size"]
            row.min_qty = normalized["min_qty"]
            row.min_notional = normalized["min_notional"]
            row.qty_precision = normalized["qty_precision"]
            row.price_precision = normalized["price_precision"]
            row.is_active = True
            row.synced_at = normalized["synced_at"]

        stored = self._row_to_rules(row)
        self._rules_cache[(exchange, symbol)] = stored
        return dict(stored)

    async def _run(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        while not self._stop_event.is_set():
            try:
                await self._sync_all(session_factory)
            except Exception:
                logger.exception("Market catalog sync loop failed")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=SYNC_INTERVAL.total_seconds())
            except asyncio.TimeoutError:
                pass

    async def _sync_all(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        for exchange in SUPPORTED_EXCHANGES:
            try:
                markets = await self._fetch_exchange_markets(exchange)
            except Exception:
                logger.exception("Market catalog sync failed for exchange", extra={"exchange": exchange})
                markets = self._fallback_markets(exchange)
            if not markets:
                markets = self._fallback_markets(exchange)
            async with session_factory() as session:
                await self._store_exchange_markets(session, exchange, markets)
                await session.commit()

    async def _fetch_exchange_markets(self, exchange: str) -> list[dict[str, Any]]:
        settings = get_settings()
        exchange_class = getattr(ccxt, "binanceusdm" if exchange == "binance" else exchange)
        params: dict[str, Any] = {"enableRateLimit": True}
        if exchange == "binance":
            params["options"] = {"defaultType": "future", "defaultSubType": "linear"}
        else:
            params["options"] = {"defaultType": "swap"}
        client = exchange_class(params)
        # Newer ccxt rejects httpsProxy + aiohttp_proxy as "multiple proxies".
        if settings.resolved_exchange_http_proxy:
            client.httpProxy = settings.resolved_exchange_http_proxy
            client.http_proxy = settings.resolved_exchange_http_proxy
        if settings.resolved_exchange_https_proxy:
            client.httpsProxy = settings.resolved_exchange_https_proxy
            client.https_proxy = settings.resolved_exchange_https_proxy
            if getattr(client, "aiohttp_proxy", None):
                client.aiohttp_proxy = None
        try:
            await client.load_markets()
            synced_at = datetime.now(timezone.utc)
            markets: list[dict[str, Any]] = []
            for market in client.markets.values():
                if not self._is_supported_market(market):
                    continue
                limits = market.get("limits") or {}
                amount_limits = limits.get("amount") or {}
                cost_limits = limits.get("cost") or {}
                precision = market.get("precision") or {}
                markets.append(
                    {
                        "exchange": exchange,
                        "symbol": market["symbol"],
                        "base": market.get("base") or "",
                        "quote": market.get("quote") or "",
                        "market_type": "swap",
                        "contract_size": float(market.get("contractSize") or 1),
                        "min_qty": float(amount_limits.get("min") or 0),
                        "min_notional": float(cost_limits.get("min") or 0),
                        "qty_precision": self._normalize_precision_value(precision.get("amount")),
                        "price_precision": self._normalize_precision_value(precision.get("price")),
                        "is_active": True,
                        "synced_at": synced_at,
                    }
                )
            return markets
        finally:
            await client.close()

    async def _store_exchange_markets(
        self,
        session: AsyncSession,
        exchange: str,
        markets: list[dict[str, Any]],
    ) -> None:
        existing_result = await session.execute(
            select(MarketSymbolCatalog).where(MarketSymbolCatalog.exchange == exchange)
        )
        existing = {
            item.symbol: item
            for item in existing_result.scalars().all()
        }
        incoming_symbols = {market["symbol"] for market in markets}

        for market in markets:
            row = existing.get(market["symbol"])
            if row is None:
                row = MarketSymbolCatalog(**market)
                session.add(row)
                self._rules_cache[(exchange, market["symbol"])] = self._row_to_rules(row)
                continue

            row.base = market["base"]
            row.quote = market["quote"]
            row.market_type = market["market_type"]
            row.contract_size = market["contract_size"]
            row.min_qty = market["min_qty"]
            row.min_notional = market["min_notional"]
            row.qty_precision = market["qty_precision"]
            row.price_precision = market["price_precision"]
            row.is_active = True
            row.synced_at = market["synced_at"]
            self._rules_cache[(exchange, market["symbol"])] = self._row_to_rules(row)

        if incoming_symbols:
            stale_keys = [
                key
                for key in self._rules_cache
                if key[0] == exchange and key[1] not in incoming_symbols
            ]
            for key in stale_keys:
                self._rules_cache.pop(key, None)
            await session.execute(
                delete(MarketSymbolCatalog).where(
                    MarketSymbolCatalog.exchange == exchange,
                    MarketSymbolCatalog.symbol.not_in(incoming_symbols),
                )
            )

    def _is_supported_market(self, market: dict[str, Any]) -> bool:
        return bool(
            market.get("active", True)
            and market.get("swap")
            and market.get("quote") == "USDT"
            and market.get("symbol")
        )

    def _normalize_precision_value(self, value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            if value >= 1:
                return 0
            text = f"{value:.12f}".rstrip("0")
            return len(text.split(".")[1]) if "." in text else 0
        return None

    def _fallback_markets(self, exchange: str) -> list[dict[str, Any]]:
        return [
            {
                "exchange": exchange,
                "symbol": "BTC/USDT:USDT",
                "base": "BTC",
                "quote": "USDT",
                "market_type": "swap",
                "contract_size": 0.01 if exchange == "okx" else 1.0,
                "min_qty": 0.0,
                "min_notional": 0.0,
                "qty_precision": None,
                "price_precision": None,
                "is_active": True,
                "synced_at": datetime.now(timezone.utc),
            }
        ]

    def _row_to_rules(self, row: MarketSymbolCatalog) -> dict[str, Any]:
        synced_at = row.synced_at
        if synced_at is not None and synced_at.tzinfo is None:
            synced_at = synced_at.replace(tzinfo=timezone.utc)
        return {
            "symbol": row.symbol,
            "base": row.base,
            "quote": row.quote,
            "market_type": row.market_type,
            "contract_size": float(row.contract_size or 1),
            "min_qty": float(row.min_qty or 0),
            "min_notional": float(row.min_notional or 0),
            "qty_precision": row.qty_precision,
            "price_precision": row.price_precision,
            "synced_at": synced_at,
        }

    def _infer_base_quote(self, symbol: str) -> tuple[str, str]:
        pair = symbol.split(":")[0]
        if "/" in pair:
            base, quote = pair.split("/", 1)
            return base, quote
        return symbol, ""


market_catalog_service = MarketCatalogService()
