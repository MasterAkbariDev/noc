import pytest
from starlette.requests import Request

from noc.api.auth import UNKNOWN_CLIENT, client_ip
from noc.cli.main import api


def request_from(host: str | None) -> Request:
    client = None if host is None else (host, 50000)
    return Request({"type": "http", "method": "POST", "path": "/", "headers": [], "client": client})


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("203.0.113.7", "203.0.113.7"),
        ("2001:db8::1", "2001:db8::1"),
        ("not-an-address", UNKNOWN_CLIENT),
        ("1.2.3.4, 5.6.7.8", UNKNOWN_CLIENT),
        ("x" * 500, UNKNOWN_CLIENT),
        (None, UNKNOWN_CLIENT),
    ],
)
def test_client_ip_is_a_parsed_address_or_unknown(host: str | None, expected: str) -> None:
    assert client_ip(request_from(host)) == expected


def test_the_api_command_does_not_trust_forwarded_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(app: object, **options: object) -> None:
        captured.update(options)

    monkeypatch.setattr("noc.cli.main.uvicorn.run", fake_run)
    monkeypatch.setattr("noc.cli.main.create_app", lambda settings: object())
    api()
    assert captured["proxy_headers"] is False
