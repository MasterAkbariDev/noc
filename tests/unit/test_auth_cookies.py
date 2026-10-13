import pytest
from fastapi import Response

from noc.api.auth import clear_session_cookies, set_session_cookies
from noc.auth.sessions import CSRF_COOKIE, SESSION_COOKIE
from noc.config import Settings


def cookie_headers(response: Response) -> dict[str, str]:
    headers = response.headers.getlist("set-cookie")
    return {header.split("=", 1)[0]: header.lower() for header in headers}


def issued_response(secure: bool) -> Response:
    settings = Settings(session_cookie_secure=secure, _env_file=None)
    response = Response()
    set_session_cookies(response, settings, token="session-value", csrf_token="csrf-value")
    return response


def test_session_cookie_is_http_only_strict_and_site_wide() -> None:
    session_header = cookie_headers(issued_response(secure=True))[SESSION_COOKIE]
    assert "httponly" in session_header
    assert "samesite=strict" in session_header
    assert "path=/" in session_header


def test_csrf_cookie_is_readable_by_script() -> None:
    csrf_header = cookie_headers(issued_response(secure=True))[CSRF_COOKIE]
    assert "httponly" not in csrf_header
    assert "samesite=strict" in csrf_header
    assert "path=/" in csrf_header


def test_both_cookies_live_for_the_absolute_session_lifetime() -> None:
    headers = cookie_headers(issued_response(secure=True))
    assert "max-age=43200" in headers[SESSION_COOKIE]
    assert "max-age=43200" in headers[CSRF_COOKIE]


@pytest.mark.parametrize("secure", [True, False])
def test_secure_flag_follows_the_setting(secure: bool) -> None:
    headers = cookie_headers(issued_response(secure=secure))
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        assert ("; secure" in headers[name]) is secure


def test_logout_expires_both_cookies_with_the_same_attributes() -> None:
    settings = Settings(session_cookie_secure=True, _env_file=None)
    response = Response()
    clear_session_cookies(response, settings)
    headers = cookie_headers(response)
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        assert "max-age=0" in headers[name]
        assert "samesite=strict" in headers[name]
        assert "path=/" in headers[name]
        assert "; secure" in headers[name]
    assert "httponly" in headers[SESSION_COOKIE]
    assert "httponly" not in headers[CSRF_COOKIE]
