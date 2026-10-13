from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR = Path(__file__).resolve().parent

LlmMode = Literal["live", "record", "replay"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOC_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://noc:noc@localhost:5432/noc"
    prometheus_url: str = "http://localhost:9090"
    api_token: SecretStr | None = None
    frontend_dist: Path | None = None

    poll_interval_seconds: float = 10.0
    missing_polls_to_resolve: int = 2
    max_concurrent_incidents: int = 2
    job_lease_seconds: int = 120
    worker_metrics_port: int = 9108
    prometheus_targets_dir: Path | None = None
    file_sd_interval_seconds: float = 60

    execution_enabled: bool = False
    automation_paused: bool = False
    investigator_max_rounds: int = 3
    investigator_max_tool_calls: int = 8
    policy_file: Path = PACKAGE_DIR / "policy" / "default_policy.yaml"

    llm_mode: LlmMode = "replay"
    llm_providers_file: Path = PACKAGE_DIR / "llm" / "providers.yaml"
    llm_fallback_enabled: bool = True
    llm_wait_deadline_seconds: float = 90.0
    cassette_dir: Path = Path("tests/cassettes")
    cassette_name: str = "default"

    sentinel_key_dir: Path = Path("/etc/noc/keys")
    sentinel_client_cert: Path | None = None
    sentinel_client_key: Path | None = None
    sentinel_ca_file: Path | None = None
    sentinel_timeout_seconds: float = 10.0

    @property
    def libpq_url(self) -> str:
        return self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
