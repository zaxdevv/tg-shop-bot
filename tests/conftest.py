from __future__ import annotations

import itertools
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

import pytest
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.methods import TelegramMethod
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from shopbot.config import Config
from shopbot.db import Shop
from shopbot.handlers import routers
from shopbot.main import build_dispatcher

ADMIN = 1000
CUSTOMER = 2000


class RecordingSession(BaseSession):
    """Answers every Bot API call locally and keeps the calls, so tests can read what the bot sent."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []
        self.ids = itertools.count(100)

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None) -> Any:
        self.calls.append(method)
        name = type(method).__name__
        if name == "SendMessage":
            return Message(message_id=next(self.ids), date=datetime.now(), text=method.text,
                           chat=Chat(id=method.chat_id, type="private"))
        return True

    async def close(self) -> None:
        return None

    async def stream_content(self, *args: Any, **kwargs: Any) -> AsyncGenerator[bytes, None]:
        yield b""


class Harness:
    def __init__(self, shop: Shop, config: Config) -> None:
        for router in routers:  # module-level routers attach once per process; each test builds a new dispatcher
            router._parent_router = None
        self.session = RecordingSession()
        self.bot = Bot("123456789:test-token-for-unit-tests-only-xxxx", session=self.session,
                       default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = build_dispatcher(shop, config)
        self.shop = shop
        self.updates = itertools.count(1)

    def user(self, user_id: int) -> User:
        return User(id=user_id, is_bot=False, first_name="Оля <b>", username=f"user{user_id}")

    def message_obj(self, user_id: int, text: str = "") -> Message:
        return Message(message_id=next(self.updates), date=datetime.now(), text=text,
                       chat=Chat(id=user_id, type="private"), from_user=self.user(user_id))

    async def send(self, text: str, user_id: int = CUSTOMER) -> None:
        msg = self.message_obj(user_id, text)
        await self.dp.feed_update(self.bot, Update(update_id=next(self.updates), message=msg))

    async def press(self, data: str, user_id: int = CUSTOMER) -> None:
        cb = CallbackQuery(id=str(next(self.updates)), from_user=self.user(user_id), chat_instance="test",
                           data=data, message=self.message_obj(user_id, "старое сообщение"))
        await self.dp.feed_update(self.bot, Update(update_id=next(self.updates), callback_query=cb))

    def sent(self, kind: str) -> list[Any]:
        return [c for c in self.session.calls if type(c).__name__ == kind]

    def last_text(self) -> str:
        texts = [c.text for c in self.session.calls if type(c).__name__ in ("SendMessage", "EditMessageText")]
        return texts[-1]

    def alerts(self) -> list[str]:
        return [c.text or "" for c in self.sent("AnswerCallbackQuery")]

    def buttons(self) -> list[tuple[str, str]]:
        for call in reversed(self.session.calls):
            markup = getattr(call, "reply_markup", None)
            if markup is not None:
                return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]
        return []


@pytest.fixture
def shop() -> Shop:
    s = Shop(":memory:")
    yield s
    s.close()


@pytest.fixture
def harness(shop: Shop) -> Harness:
    config = Config(token="x", admins=frozenset({ADMIN}), db_path=":memory:", demo_payments=True)  # type: ignore[arg-type]
    return Harness(shop, config)
