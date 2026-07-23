from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from ccxt.base.errors import AuthenticationError, PermissionDenied
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import AccountSnapshot, ApiCredential, BotSession
from app.services.encryption import EncryptionService
from app.services.exchange.factory import build_exchange_adapter

logger = logging.getLogger(__name__)
ACTIVE_WINDOW = timedelta(minutes=2)
FAILED_SYNC_STATES = {"decrypt_failed", "auth_failed"}


def _safe_float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def extract_account_equity(balance_payload: dict) -> float:
    info = balance_payload.get("info")
    if isinstance(info, dict):
        if "totalEq" in info:
            return _safe_float(info.get("totalEq"))
        data = info.get("data")
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                if "totalEq" in first:
                    return _safe_float(first.get("totalEq"))
                if "totalWalletBalance" in first:
                    return _safe_float(first.get("totalWalletBalance"))
    return _safe_float(
        balance_payload.get("total", {}).get("USDT")
        or balance_payload.get("total", {}).get("USD")
        or balance_payload.get("USDT", {}).get("total")
        or balance_payload.get("info", {}).get("totalWalletBalance")
        or balance_payload.get("info", {}).get("equity")
        or 0
    )


def normalize_positions(positions: list[dict]) -> tuple[list[dict], float, float]:
    normalized: list[dict] = []
    exposure = 0.0
    unrealized = 0.0
    for position in positions:
        contracts = float(position.get("contracts") or position.get("contractsSize") or 0)
        if not contracts:
            continue

        contract_size = _safe_float(
            position.get("contractSize")
            or position.get("contract_size")
            or position.get("info", {}).get("ctVal")
            if isinstance(position.get("info"), dict)
            else 0
        )
        if contract_size <= 0:
            contract_size = 1.0
        mark_price = float(position.get("markPrice") or position.get("last") or 0)
        entry_price = float(position.get("entryPrice") or mark_price)
        side = str(position.get("side") or "unknown")
        exposure += abs(contracts) * mark_price * contract_size
        unrealized += float(position.get("unrealizedPnl") or 0)
        normalized.append(
            {
                "symbol": position.get("symbol") or "",
                "side": side,
                "size": contracts,
                "entry_price": entry_price,
            }
        )
    return normalized, exposure, unrealized


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class AccountSyncService:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._refresh_event = asyncio.Event()
        self._encryption = EncryptionService()

    async def start(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._refresh_event.clear()
        self._task = asyncio.create_task(self._run(session_factory))

    async def stop(self) -> None:
        if not self._task:
            return
        self._stop_event.set()
        self._refresh_event.set()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    def request_refresh(self) -> None:
        self._refresh_event.set()

    async def mark_user_active(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        user_id: str,
        exchange: str | None = None,
    ) -> None:
        async with session_factory() as session:
            await self._mark_user_active_in_session(session, user_id, exchange)
            await session.commit()

    async def sync_user(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        user_id: str,
        exchange: str | None = None,
    ) -> None:
        async with session_factory() as session:
            await self._mark_user_active_in_session(session, user_id, exchange)
            query = select(ApiCredential).where(ApiCredential.user_id == user_id)
            if exchange:
                query = query.where(ApiCredential.exchange == exchange)
            result = await session.execute(query)
            credentials = result.scalars().all()
            for credential in credentials:
                await self._sync_credential(session, credential, force=True)
            await session.commit()

    async def _run(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        while not self._stop_event.is_set():
            try:
                await self._sync_all(session_factory)
            except Exception:
                logger.exception("Account snapshot sync loop failed")

            self._refresh_event.clear()
            try:
                await asyncio.wait_for(self._refresh_event.wait(), timeout=10)
            except asyncio.TimeoutError:
                pass

    async def _sync_all(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        async with session_factory() as session:
            credentials = await self._list_background_candidates(session)
            for credential in credentials:
                await self._sync_credential(session, credential, force=False)
            await session.commit()

    async def _sync_credential(
        self,
        session: AsyncSession,
        credential: ApiCredential,
        *,
        force: bool,
    ) -> None:
        if not force and credential.sync_status in FAILED_SYNC_STATES:
            return

        result = await session.execute(
            select(AccountSnapshot).where(
                AccountSnapshot.user_id == credential.user_id,
                AccountSnapshot.exchange == credential.exchange,
            )
        )
        snapshot = result.scalar_one_or_none()
        if snapshot is None:
            snapshot = AccountSnapshot(
                user_id=credential.user_id,
                exchange=credential.exchange,
                positions=[],
            )
            session.add(snapshot)

        snapshot.use_testnet = credential.use_testnet
        snapshot.synced_at = datetime.now(timezone.utc)
        credential.last_synced_at = snapshot.synced_at

        adapter = None
        try:
            adapter = build_exchange_adapter(
                exchange=credential.exchange,
                api_key=self._encryption.decrypt(credential.api_key_encrypted),
                api_secret=self._encryption.decrypt(credential.api_secret_encrypted),
                passphrase=(
                    self._encryption.decrypt(credential.passphrase_encrypted)
                    if credential.passphrase_encrypted
                    else None
                ),
                use_testnet=credential.use_testnet,
                market_type="usdt_perp",
            )
            balance_payload = await adapter.fetch_balance()
            try:
                raw_positions = await adapter.fetch_positions() or []
            except Exception:
                raw_positions = []

            positions, exposure, unrealized = normalize_positions(raw_positions)
            snapshot.balance = extract_account_equity(balance_payload)
            snapshot.unrealized_pnl = unrealized
            snapshot.exposure = exposure
            snapshot.positions = positions
            snapshot.status_message = None
            credential.sync_status = "active"
            credential.sync_error = None
            credential.last_error_at = None
        except Exception as exc:
            sync_status, user_message = self._classify_sync_error(exc)
            snapshot.status_message = user_message
            credential.sync_status = sync_status
            credential.sync_error = user_message
            credential.last_error_at = snapshot.synced_at
            if sync_status in FAILED_SYNC_STATES:
                logger.warning(
                    "Account snapshot sync disabled for credential",
                    extra={
                        "user_id": credential.user_id,
                        "exchange": credential.exchange,
                        "sync_status": sync_status,
                    },
                )
            else:
                logger.exception(
                    "Account snapshot sync failed",
                    extra={
                        "user_id": credential.user_id,
                        "exchange": credential.exchange,
                        "use_testnet": credential.use_testnet,
                    },
                )
        finally:
            if adapter is not None:
                await adapter.close()

    async def _mark_user_active_in_session(
        self,
        session: AsyncSession,
        user_id: str,
        exchange: str | None = None,
    ) -> None:
        query = select(ApiCredential).where(ApiCredential.user_id == user_id)
        if exchange:
            query = query.where(ApiCredential.exchange == exchange)
        result = await session.execute(query)
        now = datetime.now(timezone.utc)
        for credential in result.scalars().all():
            credential.last_seen_at = now

    async def _list_background_candidates(
        self,
        session: AsyncSession,
    ) -> list[ApiCredential]:
        now = datetime.now(timezone.utc)
        active_cutoff = now - ACTIVE_WINDOW

        running_result = await session.execute(
            select(BotSession.user_id).where(BotSession.status == "running")
        )
        running_user_ids = set(running_result.scalars().all())

        result = await session.execute(select(ApiCredential).order_by(ApiCredential.updated_at.desc()))
        credentials = result.scalars().all()
        return [
            credential
            for credential in credentials
            if credential.sync_status not in FAILED_SYNC_STATES
            and (
                credential.user_id in running_user_ids
                or (
                    credential.last_seen_at is not None
                    and ensure_utc(credential.last_seen_at) >= active_cutoff
                )
            )
        ]

    def _classify_sync_error(self, exc: Exception) -> tuple[str, str]:
        message = str(exc)
        lowered = message.lower()

        if "cannot be decrypted" in lowered or "encryption key likely changed" in lowered:
            return "decrypt_failed", (
                "Stored API credentials cannot be decrypted. Please re-save this credential."
            )

        auth_keywords = (
            "invalid api",
            "api key",
            "invalid signature",
            "permission denied",
            "passphrase",
            "authentication",
            "api-secret",
            "unauthorized",
        )
        if isinstance(exc, (AuthenticationError, PermissionDenied)) or any(
            keyword in lowered for keyword in auth_keywords
        ):
            return "auth_failed", (
                "Exchange authentication failed. Check API key, secret, passphrase, permissions, and IP whitelist."
            )

        return "refresh_error", message[:255]


account_sync_service = AccountSyncService()
