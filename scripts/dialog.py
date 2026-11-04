"""Runs a real conversation through the bot's handlers without Telegram and writes it as an HTML chat.

uv run python scripts/dialog.py docs/dialog.html
The README screenshots are taken from that page.
"""
from __future__ import annotations

import asyncio
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiogram.types import User

from shopbot.config import Config
from shopbot.db import Shop
from shopbot.keyboards import CartCB, OrderCB, ProductCB
from tests.conftest import CUSTOMER, Harness

STYLE = """
body { margin: 0; background: #dfe7ee; font: 15px/1.4 system-ui, sans-serif; }
.chat { width: 420px; margin: 0 auto; padding: 16px 12px; display: flex; flex-direction: column; gap: 8px; }
.me, .bot { max-width: 82%; padding: 8px 12px; border-radius: 14px; white-space: pre-wrap; }
.me { align-self: flex-end; background: #d9f6c6; border-bottom-right-radius: 4px; }
.bot { align-self: flex-start; background: #fff; border-bottom-left-radius: 4px; }
.kb { align-self: flex-start; max-width: 82%; display: grid; gap: 4px; margin-top: -4px; }
.kb div { display: flex; gap: 4px; }
.kb span { flex: 1; text-align: center; background: rgba(255,255,255,.65); border-radius: 8px; padding: 7px 8px; font-size: 13px; }
.toast { align-self: center; background: rgba(0,0,0,.55); color: #fff; padding: 4px 10px; border-radius: 10px; font-size: 13px; }
"""


async def main(out: Path) -> None:
    shop = Shop(":memory:")
    h = Harness(shop, Config(token="x", admins=frozenset(), db_path=Path(":memory:"), demo_payments=True))
    h.user = lambda uid: User(id=uid, is_bot=False, first_name="Оля")  # type: ignore[method-assign]
    html: list[str] = []
    seen = 0

    def flush() -> None:
        nonlocal seen
        for call in h.session.calls[seen:]:
            kind = type(call).__name__
            if kind in ("SendMessage", "EditMessageText"):
                html.append(f'<div class="bot">{call.text}</div>')
                markup = getattr(call, "reply_markup", None)
                if markup:
                    rows = "".join("<div>" + "".join(f"<span>{escape(b.text)}</span>" for b in row) + "</div>"
                                   for row in markup.inline_keyboard)
                    html.append(f'<div class="kb">{rows}</div>')
            elif kind == "AnswerCallbackQuery" and call.text:
                html.append(f'<div class="toast">{escape(call.text)}</div>')
        seen = len(h.session.calls)

    async def say(text: str) -> None:
        html.append(f'<div class="me">{escape(text)}</div>')
        await h.send(text)
        flush()

    async def tap(label: str, data: str) -> None:
        html.append(f'<div class="me">↳ {escape(label)}</div>')
        await h.press(data)
        flush()

    await say("/start")
    await tap("Каталог", "catalog")
    await tap("Семейные", h.buttons()[0][1])
    await tap("Каркассон · 2 490 ₽", ProductCB(action="view", id=1).pack())
    await tap("В корзину", ProductCB(action="add", id=1).pack())
    await tap("Манчкин → В корзину", ProductCB(action="add", id=7).pack())
    await tap("Корзина", "cart")
    await tap("Оформить заказ", CartCB(action="checkout").pack())
    await say("Оля")
    await say("+7 900 000-00-00")
    await say("Солодовый переулок, 7, кв. 3, домофон 3К")
    await tap("Всё верно", "confirm:yes")
    order = shop.orders(user_id=CUSTOMER)[0]
    await tap("Оплатить (демо)", OrderCB(action="pay", id=order.id).pack())

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f'<!DOCTYPE html><html lang="ru"><meta charset="utf-8"><style>{STYLE}</style>'
                   f'<div class="chat">{"".join(html)}</div></html>', encoding="utf-8")
    await h.bot.session.close()
    print(out)


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1] if len(sys.argv) > 1 else "docs/dialog.html")))
