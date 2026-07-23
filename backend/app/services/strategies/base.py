from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class StrategyPosition:
    symbol: str
    side: Literal["long", "short"]
    quantity: float
    entry_price: float


@dataclass
class StrategyContext:
    candles: list[list[float]]
    positions: list[StrategyPosition]
    config: dict[str, Any]
    state: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategySignal:
    intent: Literal["open", "close", "reduce", "hold"]
    side: Literal["long", "short"] | None
    confidence: float
    reason: str
    target_exposure_pct: float | None = None
    state: dict[str, Any] = field(default_factory=dict)


class BaseStrategy(ABC):
    strategy_id: str
    strategy_type: str

    @property
    def candle_limit(self) -> int:
        return 120

    def default_target_exposure_pct(self, config: dict[str, Any]) -> float:
        return float(config.get("position_size_pct") or 0)

    @abstractmethod
    def calculate_signal(self, context: StrategyContext) -> StrategySignal:
        raise NotImplementedError
