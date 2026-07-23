from app.services.strategies.base import BaseStrategy
from app.services.strategies.trend_following import (
    TrendBreakoutStrategy,
    TrendFollowingStrategy,
)


STRATEGY_REGISTRY: dict[str, BaseStrategy] = {
    TrendFollowingStrategy.strategy_id: TrendFollowingStrategy(),
    TrendBreakoutStrategy.strategy_id: TrendBreakoutStrategy(),
}


def get_strategy(strategy_id: str) -> BaseStrategy:
    strategy = STRATEGY_REGISTRY.get(strategy_id)
    if not strategy:
        raise ValueError(f"Unsupported strategy: {strategy_id}")
    return strategy
