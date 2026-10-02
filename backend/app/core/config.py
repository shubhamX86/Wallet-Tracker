"""Environment-driven settings. No secrets have defaults that are safe for production."""
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_JWT_SECRET = "dev-only-insecure-jwt-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Whale Tracker"
    app_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://whale:whale@localhost:5432/whale"
    redis_url: str = "redis://localhost:6379/0"

    # Comma-separated list of allowed browser origins.
    cors_origins: str = "http://localhost:3000,http://localhost"

    # Blockchain RPC. URLs come ONLY from the environment (never from user input => no SSRF).
    # The default is the public no-key endpoint: fine for development, rate-limited, so use a
    # dedicated provider (URL may embed an API key — never logged or returned) in production.
    rpc_timeout_seconds: float = 10.0
    rpc_max_retries: int = 2
    bnb_rpc_url: str = "https://bsc-dataseed.bnbchain.org"

    jwt_secret: str = _DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _require_real_secret_outside_dev(self) -> "Settings":
        if self.environment != "development":
            if self.jwt_secret == _DEV_JWT_SECRET or len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET must be set to a random value of 32+ chars")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
