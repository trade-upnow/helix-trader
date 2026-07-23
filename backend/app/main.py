from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.bot import router as bot_router
from app.api.routes.strategies import router as strategy_router
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.account_sync import account_sync_service
from app.services.bootstrap import init_database, seed_defaults
from app.services.bot_manager import bot_manager
from app.services.market_catalog import market_catalog_service


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_database()
    async with SessionLocal() as session:
        await seed_defaults(session)
    try:
        await market_catalog_service.sync_now(SessionLocal)
    except Exception:
        pass
    await market_catalog_service.start(SessionLocal)
    await account_sync_service.start(SessionLocal)
    await bot_manager.restore_running_bots(SessionLocal)
    yield
    await account_sync_service.stop()
    await market_catalog_service.stop()


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)

# JWT 走 Authorization 头，无需 cookie；若 allow_credentials=True 则不能用 "*"
# 否则浏览器会拒绝把响应交给 JS（登录 fetch 会表现为失败）。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(strategy_router)
app.include_router(bot_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
