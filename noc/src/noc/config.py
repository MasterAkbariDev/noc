from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR = Path(__file__).resolve().parent

LlmMode = Literal["live", "record", "replay"]
AgentMode = Literal["single", "multi"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOC_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://noc:noc@localhost:5432/noc"
    prometheus_url: str = "http://localhost:9090"
    api_token: SecretStr | None = None
    frontend_dist: Path | None = None
    version: str = "dev"
    git_sha: str = "unknown"
    update_status_file: Path | None = None
    session_cookie_secure: bool = True
    session_idle_minutes: int = 60
    session_absolute_hours: int = 12
    login_ip_limit: int = Field(20, ge=0)

    poll_interval_seconds: float = 10.0
    missing_polls_to_resolve: int = 2
    max_concurrent_incidents: int = 2
    job_lease_seconds: int = 120
    worker_metrics_port: int = 9108
    worker_heartbeat_seconds: float = 15.0
    prometheus_targets_dir: Path | None = None
    file_sd_interval_seconds: float = 60

    execution_enabled: bool = False
    automation_paused: bool = False
    approval_ttl_seconds: int = 3600
    verify_settle_seconds: float = 30.0
    verify_timeout_seconds: float = 300.0
    verify_poll_seconds: float = 15.0
    investigator_max_rounds: int = 3
    investigator_max_tool_calls: int = 8
    agent_mode: AgentMode = "single"
    specialist_max_rounds: int = 3
    specialist_max_tool_calls: int = 6
    policy_file: Path = PACKAGE_DIR / "policy" / "default_policy.yaml"

    llm_mode: LlmMode = "replay"
    llm_providers_file: Path = PACKAGE_DIR / "llm" / "providers.yaml"
    llm_fallback_enabled: bool = True
    llm_wait_deadline_seconds: float = 90.0
    llm_request_timeout_seconds: float = 25.0
    cassette_dir: Path = Path("tests/cassettes")
    cassette_name: str = "default"

    sentinel_key_dir: Path = Path("/etc/noc/keys")
    sentinel_client_cert: Path | None = None
    sentinel_client_key: Path | None = None
    sentinel_ca_file: Path | None = None
    sentinel_timeout_seconds: float = 10.0

    chaos_key_id: str = "noc-chaos"
    chaos_key_dir: Path | None = None
    scenarios_dir: Path = Path("scenarios")

    @property
    def libpq_url(self) -> str:
        return self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
