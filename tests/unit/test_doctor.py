import ssl
import time
from pathlib import Path

import pytest

from noc import doctor
from noc.config import PACKAGE_DIR, Settings
from noc.doctor import (
    check_certificate,
    check_key_file,
    check_llm,
    check_policy,
    check_secrets_dir,
)

SECONDS_PER_DAY = 86400
SENTINEL_URL = "https://demo-1.example:8443"


def live_settings() -> Settings:
    return Settings(_env_file=None, llm_mode="live")


def test_llm_check_needs_no_keys_outside_live_mode() -> None:
    result = check_llm(Settings(_env_file=None, llm_mode="replay"), {})
    assert result.status == "ok"


def test_llm_check_fails_when_live_without_any_key() -> None:
    assert check_llm(live_settings(), {}).status == "fail"


def test_llm_check_warns_when_one_provider_has_no_key() -> None:
    result = check_llm(live_settings(), {"GEMINI_API_KEY": "x"})
    assert result.status == "warn"
    assert "groq" in result.detail


def test_llm_check_accepts_the_key_list_variable() -> None:
    result = check_llm(live_settings(), {"GEMINI_API_KEYS": "a,b", "GROQ_API_KEY": "x"})
    assert result.status == "ok"


def test_key_file_missing_is_a_failure(tmp_path: Path) -> None:
    assert check_key_file(tmp_path, "noc-1").status == "fail"


def test_key_file_readable_by_others_is_a_warning(tmp_path: Path) -> None:
    key = tmp_path / "noc-1.key"
    key.write_text("secret")
    key.chmod(0o644)
    assert check_key_file(tmp_path, "noc-1").status == "warn"


def test_key_file_owner_only_is_ok(tmp_path: Path) -> None:
    key = tmp_path / "noc-1.key"
    key.write_text("secret")
    key.chmod(0o600)
    assert check_key_file(tmp_path, "noc-1").status == "ok"


def test_shipped_policy_passes() -> None:
    assert check_policy(PACKAGE_DIR / "policy" / "default_policy.yaml").status == "ok"


def test_broken_policy_fails(tmp_path: Path) -> None:
    broken = tmp_path / "policy.yaml"
    broken.write_text("actions: 3\n")
    assert check_policy(broken).status == "fail"


async def test_certificate_over_plain_http_is_only_a_warning() -> None:
    result = await check_certificate("demo-1", "http://demo-1.example:8443", None)
    assert result.status == "warn"


@pytest.mark.parametrize(
    ("days_left", "expected"), [(60, "ok"), (7, "warn"), (1, "fail"), (-3, "fail")]
)
async def test_certificate_status_follows_days_left(
    monkeypatch: pytest.MonkeyPatch, days_left: int, expected: str
) -> None:
    async def expiry(url: str, context: ssl.SSLContext) -> float:
        return time.time() + days_left * SECONDS_PER_DAY

    monkeypatch.setattr(doctor, "peer_certificate_expiry", expiry)
    result = await check_certificate("demo-1", SENTINEL_URL, ssl.create_default_context())
    assert result.status == expected


async def test_unreachable_certificate_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def expiry(url: str, context: ssl.SSLContext) -> float:
        raise ConnectionRefusedError

    monkeypatch.setattr(doctor, "peer_certificate_expiry", expiry)
    result = await check_certificate("demo-1", SENTINEL_URL, ssl.create_default_context())
    assert result.status == "fail"


def test_missing_secrets_folder_fails(tmp_path: Path) -> None:
    assert check_secrets_dir(tmp_path / "missing").status == "fail"


def test_read_only_secrets_folder_fails(tmp_path: Path) -> None:
    folder = tmp_path / "secrets"
    folder.mkdir()
    folder.chmod(0o500)
    try:
        assert check_secrets_dir(folder).status == "fail"
    finally:
        folder.chmod(0o700)


def test_secrets_folder_that_is_not_a_mount_is_a_warning(tmp_path: Path) -> None:
    folder = tmp_path / "secrets"
    folder.mkdir()
    assert check_secrets_dir(folder).status == "warn"
