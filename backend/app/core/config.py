from functools import lru_cache
from hashlib import sha256
import base64
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Helix AI Trader API"
    database_url: str = "sqlite+aiosqlite:///./helix.db"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    seed_demo_users: bool = True
    admin_username: str = "admin"
    admin_password: str = "ChangeMe123!"
    client_username: str = "client001"
    client_password: str = "ChangeMe123!"
    api_encryption_key: Optional[str] = Field(default=None, repr=False)
    bot_poll_seconds: int = 20
    exchange_proxy_url: Optional[str] = None
    exchange_http_proxy: Optional[str] = None
    exchange_https_proxy: Optional[str] = None

    @property
    def normalized_encryption_key(self) -> str:
        if self.api_encryption_key:
            return self.api_encryption_key

        digest = sha256(self.jwt_secret.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).decode("utf-8")

    @property
    def resolved_exchange_http_proxy(self) -> Optional[str]:
        # One EXCHANGE_PROXY_URL should cover both HTTP and HTTPS unless overridden.
        return self.exchange_http_proxy or self.exchange_proxy_url

    @property
    def resolved_exchange_https_proxy(self) -> Optional[str]:
        return self.exchange_https_proxy or self.exchange_proxy_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
