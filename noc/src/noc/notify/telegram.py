import re
from typing import Any, Final

import httpx
from pydantic import BaseModel, ConfigDict, Field

API_BASE: Final = "https://api.telegram.org"
SEND_TIMEOUT_SECONDS: Final = 15.0
POLL_TIMEOUT_SECONDS: Final = 25
MESSAGE_MAX_LENGTH: Final = 3500
TOKEN_PATTERN: Final = re.compile(r"^\d{5,15}:[A-Za-z0-9_-]{30,64}$")
USER_ID_PATTERN: Final = re.compile(r"^\d{1,16}$")
USERNAME_PATTERN: Final = re.compile(r"^@[A-Za-z][A-Za-z0-9_]{4,31}$")
ERROR_MAX_LENGTH: Final = 300


class TelegramError(Exception):
    pass


class TelegramUser(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    username: str | None = None
    first_name: str = ""


class TelegramChat(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    type: str


class TelegramMessage(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    message_id: int
    chat: TelegramChat
    sender: TelegramUser | None = Field(default=None, alias="from")
    text: str = ""


class CallbackQuery(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    sender: TelegramUser = Field(alias="from")
    message: TelegramMessage | None = None
    data: str = ""


class TelegramUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    update_id: int
    message: TelegramMessage | None = None
    callback_query: CallbackQuery | None = None


class Button(BaseModel):
    text: str
    callback_data: str


Keyboard = list[list[Button]]


def valid_token(token: str) -> bool:
    return TOKEN_PATTERN.fullmatch(token) is not None


def valid_user_handle(handle: str) -> bool:
    return (
        USER_ID_PATTERN.fullmatch(handle) is not None
        or USERNAME_PATTERN.fullmatch(handle) is not None
    )


def scrub(text: str, token: str) -> str:
    return text.replace(token, "***")[:ERROR_MAX_LENGTH]


def keyboard_markup(keyboard: Keyboard) -> dict[str, Any]:
    return {"inline_keyboard": [[button.model_dump() for button in row] for row in keyboard]}


class TelegramSender:
    def __init__(self, token: str, proxy: str | None = None, api_base: str = API_BASE) -> None:
        self._token = token
        self._proxy = proxy
        self._api_base = api_base

    async def send(self, chat_id: str, text: str, keyboard: Keyboard | None = None) -> None:
        body: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text[:MESSAGE_MAX_LENGTH],
            "disable_web_page_preview": True,
        }
        if keyboard is not None:
            body["reply_markup"] = keyboard_markup(keyboard)
        await self._call("sendMessage", body, SEND_TIMEOUT_SECONDS)

    async def edit(
        self, chat_id: str, message_id: int, text: str, keyboard: Keyboard | None = None
    ) -> None:
        body: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text[:MESSAGE_MAX_LENGTH],
            "disable_web_page_preview": True,
        }
        if keyboard is not None:
            body["reply_markup"] = keyboard_markup(keyboard)
        await self._call("editMessageText", body, SEND_TIMEOUT_SECONDS)

    async def answer(self, callback_id: str, text: str) -> None:
        body = {"callback_query_id": callback_id, "text": text[:200]}
        await self._call("answerCallbackQuery", body, SEND_TIMEOUT_SECONDS)

    async def updates(self, offset: int | None) -> list[TelegramUpdate]:
        body: dict[str, Any] = {
            "timeout": POLL_TIMEOUT_SECONDS,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            body["offset"] = offset
        result = await self._call("getUpdates", body, POLL_TIMEOUT_SECONDS + 10)
        if not isinstance(result, list):
            raise TelegramError("getUpdates returned no list")
        return [TelegramUpdate.model_validate(item) for item in result]

    async def _call(self, method: str, body: dict[str, Any], wait_seconds: float) -> Any:
        url = f"{self._api_base}/bot{self._token}/{method}"
        try:
            async with httpx.AsyncClient(proxy=self._proxy, timeout=wait_seconds) as http:
                response = await http.post(url, json=body)
        except httpx.HTTPError as error:
            raise TelegramError(scrub(f"{type(error).__name__}: {error}", self._token)) from error
        if response.status_code != 200:
            raise TelegramError(scrub(f"HTTP {response.status_code}: {response.text}", self._token))
        try:
            payload: Any = response.json()
        except ValueError as error:
            raise TelegramError("Telegram answered with something that is not JSON") from error
        return payload.get("result") if isinstance(payload, dict) else None
