"""Application configuration loaded from environment variables (prefix ``CRISEES_``)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent

API_VERSION = "0.1.0"
API_PREFIX = "/api/v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CRISEES_",
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "development"
    log_level: str = "INFO"
    data_dir: Path = Field(default=REPO_ROOT / "data")
    cors_origins: list[str] | str = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    cors_origin_regex: str | None = Field(
        default=None, description="Optional regex for extra allowed origins, e.g. Vercel preview URLs"
    )
    default_page_size: int = Field(default=500, ge=1)
    max_page_size: int = Field(default=5000, ge=1)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return value

    @field_validator("data_dir", mode="after")
    @classmethod
    def _resolve_data_dir(cls, value: Path) -> Path:
        # Relative paths are resolved against the backend directory so the
        # result does not depend on the shell's working directory.
        return value if value.is_absolute() else (BACKEND_DIR / value).resolve()

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"


@lru_cache
def get_settings() -> Settings:
    return Settings()
