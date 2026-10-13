from collections.abc import Mapping
from typing import Final

from pydantic import BaseModel, Field

CHAOS_HOST: Final = "127.0.0.1"


class Settings(BaseModel):
    database_url: str | None = None
    chaos_port: int = Field(default=8099, ge=1024, le=65535)
    reports_interval_seconds: int = Field(default=60, ge=1, le=3600)

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> "Settings":
        return cls(
            database_url=environ.get("DEMO_DATABASE_URL") or None,
            chaos_port=int(environ.get("DEMO_CHAOS_PORT", "8099")),
            reports_interval_seconds=int(environ.get("DEMO_REPORTS_INTERVAL_SECONDS", "60")),
        )
