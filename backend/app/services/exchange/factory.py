from typing import Optional

from app.core.config import get_settings
from app.services.exchange.ccxt_adapter import CcxtExchangeAdapter


def build_exchange_adapter(
    *,
    exchange: str,
    api_key: str,
    api_secret: str,
    passphrase: Optional[str],
    use_testnet: bool,
    market_type: str,
) -> CcxtExchangeAdapter:
    if exchange not in {"binance", "okx"}:
        raise ValueError(f"Unsupported exchange: {exchange}")

    settings = get_settings()

    return CcxtExchangeAdapter(
        exchange_id=exchange,
        api_key=api_key,
        api_secret=api_secret,
        passphrase=passphrase,
        use_testnet=use_testnet,
        market_type=market_type,
        http_proxy=settings.resolved_exchange_http_proxy,
        https_proxy=settings.resolved_exchange_https_proxy,
    )
