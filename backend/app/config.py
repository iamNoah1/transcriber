from __future__ import annotations

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    env: str = "development"
    log_level: str = "INFO"

    # Auth
    oidc_issuer_url: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_scopes: str = "openid profile email"
    owner_open_id: str = ""
    jwt_secret: str = ""
    session_cookie_name: str = "tc_session"
    auth_disabled: bool = True

    # Jobs
    job_retention_days: int = 30
    max_upload_mb: int = 500
    max_total_upload_mb: int = 2048

    # Paths
    data_dir: Path = Field(default=Path("./data"))
    storage_dir: Path = Field(default=Path("./storage"))

    @model_validator(mode="after")
    def _validate_auth(self) -> "Settings":
        if self.env == "production" and self.auth_disabled:
            raise ValueError("AUTH_DISABLED must be false in production")
        if not self.auth_disabled and not (self.owner_open_id and self.jwt_secret):
            raise ValueError("OWNER_OPEN_ID and JWT_SECRET are required when auth is enabled")
        return self

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def jobs_dir(self) -> Path:
        return self.storage_dir / "jobs"


def get_settings() -> Settings:
    return Settings()
