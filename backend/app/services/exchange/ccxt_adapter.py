from __future__ import annotations

import asyncio
from decimal import Decimal, ROUND_DOWN
from typing import Any, Optional

import ccxt.async_support as ccxt
from ccxt.base.errors import InvalidOrder

from app.services.rate_limiter import rate_limiter


class CcxtExchangeAdapter:
    def __init__(
        self,
        *,
        exchange_id: str,
        api_key: str,
        api_secret: str,
        passphrase: Optional[str],
        use_testnet: bool,
        market_type: str,
        http_proxy: Optional[str] = None,
        https_proxy: Optional[str] = None,
    ) -> None:
        options = {
            "defaultType": "swap" if "perp" in market_type else "delivery",
        }
        params: dict[str, Any] = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": options,
        }

        if exchange_id == "okx" and passphrase:
            params["password"] = passphrase

        exchange_class = getattr(ccxt, exchange_id)
        self.exchange = exchange_class(params)
        self.exchange_id = exchange_id
        self.use_testnet = use_testnet

        if self.use_testnet and hasattr(self.exchange, "set_sandbox_mode"):
            self.exchange.set_sandbox_mode(True)

        # ccxt rejects multiple proxy fields (e.g. httpProxy + httpsProxy together).
        # OKX REST is HTTPS; use a single https proxy when URLs match or only one is set.
        proxy = https_proxy or http_proxy
        if proxy:
            self.exchange.httpsProxy = proxy
            self.exchange.https_proxy = proxy
            if getattr(self.exchange, "aiohttp_proxy", None):
                self.exchange.aiohttp_proxy = None

    async def initialize(self) -> None:
        await rate_limiter.execute(self.exchange_id, self.exchange.load_markets)

    async def refresh_markets(self) -> None:
        await rate_limiter.execute(
            self.exchange_id,
            lambda: self.exchange.load_markets(True),
        )

    async def close(self) -> None:
        await self.exchange.close()

    async def set_hedge_mode(self) -> None:
        if self.exchange_id == "binance":
            await rate_limiter.execute(
                self.exchange_id,
                lambda: self.exchange.set_position_mode(True),
            )
        elif self.exchange_id == "okx":
            position_mode = await rate_limiter.execute(
                self.exchange_id,
                lambda: self.exchange.fetch_position_mode(),
            )
            if position_mode.get("hedged"):
                return
            await rate_limiter.execute(
                self.exchange_id,
                lambda: self.exchange.set_position_mode(True),
            )

    async def set_leverage(self, symbol: str, leverage: float) -> None:
        try:
            await rate_limiter.execute(
                self.exchange_id,
                lambda: self.exchange.set_leverage(leverage, symbol),
            )
        except Exception:
            return

    async def fetch_balance(self) -> dict:
        return await rate_limiter.execute(self.exchange_id, self.exchange.fetch_balance)

    async def fetch_positions(self, symbols: Optional[list[str]] = None) -> list[dict]:
        if hasattr(self.exchange, "fetch_positions"):
            return await rate_limiter.execute(
                self.exchange_id,
                lambda: self.exchange.fetch_positions(symbols),
            )
        return []

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str, limit: int
    ) -> list[list[float]]:
        return await rate_limiter.execute(
            self.exchange_id,
            lambda: self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit),
        )

    async def fetch_ticker(self, symbol: str) -> dict:
        return await rate_limiter.execute(
            self.exchange_id, lambda: self.exchange.fetch_ticker(symbol)
        )

    def get_market_rules(self, symbol: str) -> dict[str, Any]:
        market = self.exchange.market(symbol)
        limits = market.get("limits") or {}
        precision = market.get("precision") or {}
        return {
            "symbol": symbol,
            "contract_size": float(market.get("contractSize") or 1),
            "min_qty": float((limits.get("amount") or {}).get("min") or 0),
            "min_notional": float((limits.get("cost") or {}).get("min") or 0),
            "qty_precision": precision.get("amount"),
            "price_precision": precision.get("price"),
        }

    async def fetch_market_rules(self, symbol: str, *, reload: bool = False) -> dict[str, Any]:
        if reload or symbol not in getattr(self.exchange, "markets", {}):
            await self.refresh_markets()
        elif not getattr(self.exchange, "markets", None):
            await self.initialize()
        return self.get_market_rules(symbol)

    def estimate_notional(
        self,
        symbol: str,
        amount: float,
        price: float,
        *,
        rules: Optional[dict[str, Any]] = None,
    ) -> float:
        rules = rules or self.get_market_rules(symbol)
        contract_size = float(rules.get("contract_size") or 0)
        if contract_size <= 0:
            contract_size = 1.0
        return abs(amount) * max(price, 0) * contract_size

    def normalize_order_amount(
        self,
        symbol: str,
        amount: float,
        *,
        price: float,
        rules: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        normalized = abs(amount)
        rules = rules or self.get_market_rules(symbol)
        qty_precision = rules.get("qty_precision")
        if qty_precision is not None:
            normalized = self._round_amount(normalized, int(qty_precision))
        elif hasattr(self.exchange, "amount_to_precision"):
            try:
                normalized = float(self.exchange.amount_to_precision(symbol, normalized))
            except InvalidOrder as exc:
                return {"ok": False, "reason": str(exc)}
        notional = self.estimate_notional(symbol, normalized, price, rules=rules)
        if normalized <= 0:
            return {"ok": False, "reason": "Order amount is zero after precision normalization"}
        if rules["min_qty"] > 0 and normalized < rules["min_qty"]:
            return {
                "ok": False,
                "reason": f"Order amount {normalized} is below min qty {rules['min_qty']}",
            }
        if rules["min_notional"] > 0 and notional < rules["min_notional"]:
            return {
                "ok": False,
                "reason": (
                    f"Order notional {notional:.4f} is below min notional {rules['min_notional']}"
                ),
            }
        return {
            "ok": True,
            "amount": normalized,
            "notional": notional,
            "rules": rules,
        }

    def _round_amount(self, amount: float, precision: int) -> float:
        if precision < 0:
            precision = 0
        quantum = Decimal("1") if precision == 0 else Decimal(f"1e-{precision}")
        return float(Decimal(str(amount)).quantize(quantum, rounding=ROUND_DOWN))

    async def fetch_open_orders(self, symbol: str) -> list[dict]:
        if hasattr(self.exchange, "fetch_open_orders"):
            return await rate_limiter.execute(
                self.exchange_id,
                lambda: self.exchange.fetch_open_orders(symbol),
            )
        return []

    async def cancel_order(self, order_id: str, symbol: str) -> dict | None:
        if hasattr(self.exchange, "cancel_order"):
            return await rate_limiter.execute(
                self.exchange_id,
                lambda: self.exchange.cancel_order(order_id, symbol),
            )
        return None

    async def create_market_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        *,
        reduce_only: bool = False,
        pos_side: Optional[str] = None,
        client_order_id: Optional[str] = None,
    ) -> dict:
        params = {}
        if reduce_only:
            params["reduceOnly"] = True
        if self.exchange_id == "okx":
            inferred_pos_side = pos_side
            if inferred_pos_side is None:
                inferred_pos_side = "long" if side == "buy" else "short"
            params["posSide"] = inferred_pos_side
            if client_order_id:
                params["clOrdId"] = client_order_id
        elif self.exchange_id == "binance" and client_order_id:
            params["newClientOrderId"] = client_order_id
        return await rate_limiter.execute(
            self.exchange_id,
            lambda: self.exchange.create_order(
                symbol=symbol,
                type="market",
                side=side,
                amount=amount,
                params=params,
            ),
        )

    async def close_all_positions(self, symbol: str) -> None:
        positions = await self.fetch_positions([symbol])
        for position in positions:
            contracts = float(position.get("contracts") or position.get("contractsSize") or 0)
            if not contracts:
                continue
            position_side = str(position.get("side") or "long")
            side = "sell" if position_side == "long" else "buy"
            await self.create_market_order(
                symbol,
                side,
                abs(contracts),
                reduce_only=True,
                pos_side=position_side,
            )
            await asyncio.sleep(0.1)
