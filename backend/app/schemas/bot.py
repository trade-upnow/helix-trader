from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SaveCredentialRequest(BaseModel):
    exchange: str
    api_key: str
    api_secret: str
    passphrase: Optional[str] = None
    use_testnet: bool = False


class SaveCredentialResponse(BaseModel):
    masked_api_key: str


class StartBotRequest(BaseModel):
    strategy_id: str
    exchange: str
    symbol: str = "BTC/USDT:USDT"
    market_type: str = "usdt_perp"
    leverage: float = Field(default=3, gt=0)
    position_size_pct: float = Field(default=15, gt=0, le=100)
    stop_loss_pct: float = Field(default=2, gt=0, le=100)
    take_profit_pct: float = Field(default=5, gt=0, le=100)
    max_drawdown_pct: float = Field(default=12, gt=0, le=100)
    max_order_notional_usdt: float = Field(default=1000, gt=0)
    max_position_notional_usdt: float = Field(default=3000, gt=0)
    close_all_on_stop: bool = True
    use_testnet: bool = False


class UpdateBotConfigRequest(BaseModel):
    leverage: float = Field(gt=0)
    position_size_pct: float = Field(gt=0, le=100)
    stop_loss_pct: float = Field(gt=0, le=100)
    take_profit_pct: float = Field(gt=0, le=100)
    max_drawdown_pct: float = Field(gt=0, le=100)
    max_order_notional_usdt: float = Field(gt=0)
    max_position_notional_usdt: float = Field(gt=0)
    close_all_on_stop: Optional[bool] = None


class UpdateBotConfigResponse(BaseModel):
    detail: str
    config: dict


class StopBotRequest(BaseModel):
    close_all: bool = False


class PositionResponse(BaseModel):
    symbol: str
    side: str
    size: float
    entry_price: float


class MarketSymbolResponse(BaseModel):
    symbol: str
    base: str
    quote: str
    min_qty: float
    min_notional: float
    qty_precision: Optional[int] = None
    price_precision: Optional[int] = None


class BotStatusResponse(BaseModel):
    status: str
    strategy_id: Optional[str] = None
    is_stopping: bool = False
    exchange: Optional[str] = None
    runtime_symbol: Optional[str] = None
    runtime_position_side: Optional[str] = None
    selected_symbol: Optional[str] = None
    masked_api_key: Optional[str] = None
    credential_status: Optional[str] = None
    credential_error: Optional[str] = None
    # None means no exchange credential is saved yet (not "live").
    use_testnet: Optional[bool] = None
    status_message: Optional[str] = None
    account_status_message: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    close_all_on_stop: bool = True
    active_config: Optional[dict] = None
    balance: float = 0
    unrealized_pnl: float = 0
    exposure: float = 0
    positions: list[PositionResponse] = Field(default_factory=list)


class TradeResponse(BaseModel):
    id: str
    symbol: str
    side: str
    price: float
    quantity: float
    realized_pnl: Optional[float] = None
    created_at: datetime
