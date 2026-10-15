import re
from typing import Final

import httpx

API_BASE: Final = "https://api.telegram.org"
SEND_TIMEOUT_SECONDS: Final = 15.0
MESSAGE_MAX_LENGTH: Final = 3500
TOKEN_PATTERN: Final = re.compile(r"^\d{5,15}:[A-Za-z0-9_-]{30,64}$")
CHAT_ID_PATTERN: Final = re.compile(r"^(-?\d{1,20}|@[A-Za-z][A-Za-z0-9_]{4,31})$")
ERROR_MAX_LENGTH: Final = 300


class TelegramError(Exception):
    pass


def valid_token(token: str) -> bool:
    return TOKEN_PATTERN.fullmatch(token) is not None


def valid_chat_id(chat_id: str) -> bool:
    return CHAT_ID_PATTERN.fullmatch(chat_id) is not None


def scrub(text: str, token: str) -> str:
    return text.replace(token, "***")[:ERROR_MAX_LENGTH]


class TelegramSender:
    def __init__(self, token: str, proxy: str | None = None, api_base: str = API_BASE) -> None:
        self._token = token
        self._proxy = proxy
        self._api_base = api_base

    async def send(self, chat_id: str, text: str) -> None:
        url = f"{self._api_base}/bot{self._token}/sendMessage"
        body = {
            "chat_id": chat_id,
            "text": text[:MESSAGE_MAX_LENGTH],
            "disable_web_page_preview": True,
        }
        try:
            async with httpx.AsyncClient(proxy=self._proxy, timeout=SEND_TIMEOUT_SECONDS) as http:
                response = await http.post(url, json=body)
        except httpx.HTTPError as error:
            raise TelegramError(scrub(f"{type(error).__name__}: {error}", self._token)) from error
        if response.status_code != 200:
            raise TelegramError(scrub(f"HTTP {response.status_code}: {response.text}", self._token))
