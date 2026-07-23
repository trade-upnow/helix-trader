from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import StrategyDefinition, User
from app.schemas.strategy import StrategyResponse


router = APIRouter(prefix="/api/strategies", tags=["strategies"])


@router.get("", response_model=list[StrategyResponse])
async def list_strategies(
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[StrategyResponse]:
    result = await db.execute(
        select(StrategyDefinition).where(StrategyDefinition.is_active.is_(True))
    )
    strategies = result.scalars().all()

    return [
        StrategyResponse(
            id=strategy.id,
            default_params=strategy.default_params,
        )
        for strategy in strategies
    ]
