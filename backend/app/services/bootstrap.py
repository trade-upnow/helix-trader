from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import Base, engine
from app.models import StrategyDefinition, User


DEFAULT_STRATEGIES = [
    StrategyDefinition(
        id="trend_following_core",
        name="Helix Momentum X",
        description="Core trend-following logic using shared candle feeds and account-level risk controls.",
        strategy_type="momentum",
        default_params={
            "symbol": "BTC/USDT:USDT",
            "timeframe": "15m",
            "leverage": 3,
            "position_size_pct": 15,
            "stop_loss_pct": 2,
            "take_profit_pct": 5,
            "max_drawdown_pct": 12,
            "max_order_notional_usdt": 1000,
            "max_position_notional_usdt": 3000,
            "exchange_scope": ["binance", "okx"],
        },
    ),
    StrategyDefinition(
        id="trend_breakout_accel",
        name="Helix Breakout Pro",
        description="Breakout-focused momentum variant that reuses the same market data and execution pipeline.",
        strategy_type="momentum",
        default_params={
            "symbol": "BTC/USDT:USDT",
            "timeframe": "15m",
            "leverage": 2,
            "position_size_pct": 12,
            "stop_loss_pct": 1.8,
            "take_profit_pct": 6,
            "max_drawdown_pct": 10,
            "max_order_notional_usdt": 1000,
            "max_position_notional_usdt": 3000,
            "exchange_scope": ["binance", "okx"],
        },
    ),
]


async def init_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await _ensure_runtime_schema(connection)


async def _ensure_runtime_schema(connection) -> None:
    if connection.dialect.name != "sqlite":
        return

    async def ensure_column(table_name: str, column_name: str, ddl: str) -> None:
        result = await connection.exec_driver_sql(f"PRAGMA table_info({table_name})")
        columns = {row[1] for row in result.fetchall()}
        if column_name not in columns:
            await connection.exec_driver_sql(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"
            )

    await ensure_column("bot_sessions", "peak_balance", "FLOAT DEFAULT 0")
    await ensure_column("bot_sessions", "runtime_symbol", "VARCHAR(64)")
    await ensure_column("trade_records", "client_order_id", "VARCHAR(64)")
    await ensure_column("trade_records", "bot_tag", "VARCHAR(32)")
    await ensure_column("api_credentials", "sync_status", "VARCHAR(32) DEFAULT 'active'")
    await ensure_column("api_credentials", "sync_error", "VARCHAR(255)")
    await ensure_column("api_credentials", "last_seen_at", "DATETIME")
    await ensure_column("api_credentials", "last_synced_at", "DATETIME")
    await ensure_column("api_credentials", "last_error_at", "DATETIME")


async def seed_defaults(session: AsyncSession) -> None:
    settings = get_settings()
    if settings.seed_demo_users:
        for username, password, is_admin in [
            (settings.admin_username, settings.admin_password, True),
            (settings.client_username, settings.client_password, False),
        ]:
            result = await session.execute(select(User).where(User.username == username))
            user = result.scalar_one_or_none()
            if user is None:
                session.add(
                    User(
                        username=username,
                        password_hash=hash_password(password),
                        is_admin=is_admin,
                    )
                )

    for strategy in DEFAULT_STRATEGIES:
        result = await session.execute(
            select(StrategyDefinition).where(StrategyDefinition.id == strategy.id)
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            session.add(strategy)
            continue

        merged_params = {**strategy.default_params, **existing.default_params}
        if merged_params != existing.default_params:
            existing.default_params = merged_params

    await session.commit()
