from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError
from aiogram.fsm.storage.memory import MemoryStorage

from . import config as settings
from .db import Shop
from .handlers import routers

log = logging.getLogger("shopbot")


def build_dispatcher(shop: Shop, config: settings.Config) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage(), shop=shop, config=config)
    dp.include_routers(*routers)
    return dp


async def serve(config: settings.Config) -> None:
    shop = Shop(config.db_path)
    bot = Bot(config.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        me = await bot.get_me()
        log.info("@%s запущен, админов: %d, демо-оплата: %s", me.username, len(config.admins),
                 "да" if config.demo_payments else "нет")
        if not config.admins:
            log.warning("ADMIN_IDS пуст: уведомления о заказах никто не получит")
        await bot.delete_webhook(drop_pending_updates=True)
        await build_dispatcher(shop, config).start_polling(bot)
    finally:
        await bot.session.close()
        shop.close()


def run() -> None:
    # Windows pipes default to the ANSI code page and cannot print Cyrillic.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and (stream.encoding or "").lower() not in ("utf-8", "utf8"):
            stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    try:
        config = settings.load()
    except settings.ConfigError as exc:
        print(f"Ошибка в настройках: {exc}", file=sys.stderr)
        sys.exit(2)
    try:
        asyncio.run(serve(config))
    except TelegramUnauthorizedError:
        print("Telegram не принял BOT_TOKEN: токен отозван или скопирован с ошибкой. Возьмите новый у @BotFather.",
              file=sys.stderr)
        sys.exit(2)
    except TelegramNetworkError as exc:
        print(f"Нет связи с Telegram: {exc}. Проверьте интернет или прокси.", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        pass
