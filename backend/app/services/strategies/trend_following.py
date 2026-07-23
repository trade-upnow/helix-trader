from __future__ import annotations

from app.services.strategies.base import (
    BaseStrategy,
    StrategyContext,
    StrategyPosition,
    StrategySignal,
)


def _close_prices(candles: list[list[float]]) -> list[float]:
    return [float(candle[4]) for candle in candles]


def _high_prices(candles: list[list[float]]) -> list[float]:
    return [float(candle[2]) for candle in candles]


def _low_prices(candles: list[list[float]]) -> list[float]:
    return [float(candle[3]) for candle in candles]


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    smoothing = 2 / (period + 1)
    ema_value = values[0]
    for value in values[1:]:
        ema_value = (value * smoothing) + (ema_value * (1 - smoothing))
    return ema_value


def _atr(candles: list[list[float]], period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0
    window = candles[-(period + 1) :]
    true_ranges: list[float] = []
    previous_close = float(window[0][4])
    for candle in window[1:]:
        high = float(candle[2])
        low = float(candle[3])
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
        previous_close = float(candle[4])
    if not true_ranges:
        return 0.0
    return sum(true_ranges) / len(true_ranges)


def _latest_position(positions: list[StrategyPosition]) -> StrategyPosition | None:
    return positions[0] if positions else None


class TrendFollowingStrategy(BaseStrategy):
    strategy_id = "trend_following_core"
    strategy_type = "momentum"

    def calculate_signal(self, context: StrategyContext) -> StrategySignal:
        closes = _close_prices(context.candles)
        highs = _high_prices(context.candles)
        lows = _low_prices(context.candles)
        if len(closes) < 80:
            return StrategySignal("hold", None, 0, "Not enough market data")

        latest = closes[-1]
        fast_ema = _ema(closes[-24:], 12)
        slow_ema = _ema(closes[-72:], 36)
        prev_fast_ema = _ema(closes[-25:-1], 12)
        prev_slow_ema = _ema(closes[-73:-1], 36)
        atr_value = _atr(context.candles, 14)
        atr_pct = atr_value / max(latest, 1e-9)
        momentum = (latest - closes[-7]) / max(closes[-7], 1e-9)
        long_structure = min(lows[-8:])
        short_structure = max(highs[-8:])
        trend_threshold = max(atr_pct * 0.6, 0.0025)
        target_pct = self.default_target_exposure_pct(context.config)
        position = _latest_position(context.positions)

        bullish = (
            fast_ema > slow_ema
            and prev_fast_ema >= prev_slow_ema
            and fast_ema > prev_fast_ema
            and latest > fast_ema
            and momentum > trend_threshold
        )
        bearish = (
            fast_ema < slow_ema
            and prev_fast_ema <= prev_slow_ema
            and fast_ema < prev_fast_ema
            and latest < fast_ema
            and momentum < -trend_threshold
        )

        if position is None:
            if bullish:
                return StrategySignal(
                    "open",
                    "long",
                    0.76,
                    "Trend and momentum aligned to the upside",
                    target_exposure_pct=target_pct,
                )
            if bearish:
                return StrategySignal(
                    "open",
                    "short",
                    0.74,
                    "Trend and momentum aligned to the downside",
                    target_exposure_pct=target_pct,
                )
            return StrategySignal("hold", None, 0.41, "Waiting for directional confirmation")

        if position.side == "long":
            structure_failed = latest < long_structure or fast_ema < slow_ema or momentum < -trend_threshold
            if structure_failed:
                return StrategySignal("close", "long", 0.68, "Long trend lost structure support")
            return StrategySignal(
                "hold",
                "long",
                0.53,
                "Long trend remains intact",
                target_exposure_pct=target_pct,
            )

        structure_failed = latest > short_structure or fast_ema > slow_ema or momentum > trend_threshold
        if structure_failed:
            return StrategySignal("close", "short", 0.68, "Short trend lost structure resistance")
        return StrategySignal(
            "hold",
            "short",
            0.52,
            "Short trend remains intact",
            target_exposure_pct=target_pct,
        )


class TrendBreakoutStrategy(BaseStrategy):
    strategy_id = "trend_breakout_accel"
    strategy_type = "momentum"

    def calculate_signal(self, context: StrategyContext) -> StrategySignal:
        closes = _close_prices(context.candles)
        highs = _high_prices(context.candles)
        lows = _low_prices(context.candles)
        if len(closes) < 60:
            return StrategySignal("hold", None, 0, "Not enough market data")

        latest = closes[-1]
        breakout_high = max(highs[-21:-1])
        breakout_low = min(lows[-21:-1])
        atr_value = _atr(context.candles, 14)
        trailing_buffer = max(atr_value * 1.8, latest * 0.006)
        target_pct = self.default_target_exposure_pct(context.config)
        position = _latest_position(context.positions)
        state = dict(context.state or {})

        if position is None:
            if latest > breakout_high * 1.0005:
                return StrategySignal(
                    "open",
                    "long",
                    0.79,
                    "Upside breakout confirmed",
                    target_exposure_pct=target_pct,
                    state={
                        "side": "long",
                        "breakout_level": breakout_high,
                        "best_price": latest,
                    },
                )
            if latest < breakout_low * 0.9995:
                return StrategySignal(
                    "open",
                    "short",
                    0.79,
                    "Downside breakout confirmed",
                    target_exposure_pct=target_pct,
                    state={
                        "side": "short",
                        "breakout_level": breakout_low,
                        "best_price": latest,
                    },
                )
            return StrategySignal("hold", None, 0.4, "Waiting for breakout expansion", state={})

        if position.side == "long":
            best_price = max(float(state.get("best_price") or latest), latest)
            breakout_level = float(state.get("breakout_level") or breakout_high)
            trail_stop = max(breakout_level, best_price - trailing_buffer)
            next_state = {
                "side": "long",
                "breakout_level": breakout_level,
                "best_price": best_price,
            }
            if latest <= trail_stop:
                return StrategySignal(
                    "close",
                    "long",
                    0.71,
                    "Long breakout lost trailing protection",
                    state={},
                )
            return StrategySignal(
                "hold",
                "long",
                0.56,
                "Long breakout remains protected by trailing stop",
                target_exposure_pct=target_pct,
                state=next_state,
            )

        best_price = min(float(state.get("best_price") or latest), latest)
        breakout_level = float(state.get("breakout_level") or breakout_low)
        trail_stop = min(breakout_level, best_price + trailing_buffer)
        next_state = {
            "side": "short",
            "breakout_level": breakout_level,
            "best_price": best_price,
        }
        if latest >= trail_stop:
            return StrategySignal(
                "close",
                "short",
                0.71,
                "Short breakout lost trailing protection",
                state={},
            )
        return StrategySignal(
            "hold",
            "short",
            0.56,
            "Short breakout remains protected by trailing stop",
            target_exposure_pct=target_pct,
            state=next_state,
        )
