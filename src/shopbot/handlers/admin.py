from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ..config import Config
from ..db import Shop
from ..keyboards import OrderCB, rub
from .orders import order_text
from .shop import show

router = Router(name="admin")
log = logging.getLogger(__name__)


def is_admin(user_id: int | None, config: Config) -> bool:
    return user_id is not None and user_id in config.admins


@router.message(Command("stats"))
async def stats(message: Message, shop: Shop, config: Config) -> None:
    if not is_admin(message.from_user.id if message.from_user else None, config):
        await message.answer("Эта команда только для администратора магазина.")
        return
    count, revenue, top = shop.stats()
    lines = [f"<b>Оплаченные заказы:</b> {count}", f"<b>Выручка:</b> {rub(revenue)}"]
    if top:
        lines += ["", "Чаще всего берут:"] + [f"{i}. {title}: {sold} шт." for i, (title, sold) in enumerate(top, 1)]
    await message.answer("\n".join(lines))


@router.message(Command("all_orders"))
async def all_orders(message: Message, shop: Shop, config: Config) -> None:
    if not is_admin(message.from_user.id if message.from_user else None, config):
        await message.answer("Эта команда только для администратора магазина.")
        return
    orders = shop.orders(limit=10)
    await message.answer("\n\n".join(order_text(shop, o, for_admin=True) for o in orders) or "Заказов нет.")


@router.callback_query(OrderCB.filter(F.action.in_({"done", "reject"})))
async def admin_action(cb: CallbackQuery, callback_data: OrderCB, shop: Shop, config: Config, bot: Bot) -> None:
    if not is_admin(cb.from_user.id, config):
        log.warning("user %s tried admin action %s on order %s",
                    cb.from_user.id, callback_data.action, callback_data.id)
        await cb.answer("Недостаточно прав", show_alert=True)
        return
    if callback_data.action == "done":
        order = shop.set_status(callback_data.id, "done", expected=("paid", "new"))
        note = "Ваш заказ №{id} передан в доставку. Курьер позвонит заранее."
    else:
        order = shop.set_status(callback_data.id, "cancelled", expected=("paid", "new"))
        note = "Заказ №{id} отменён магазином. Если вы уже платили, деньги вернутся в течение трёх дней."
    if order is None:
        await cb.answer("Статус уже изменён", show_alert=True)
        return
    await show(cb, order_text(shop, order, for_admin=True), None)
    try:
        await bot.send_message(order.user_id, note.format(id=order.id))
    except TelegramAPIError as exc:
        log.warning("customer %s was not notified about order %s: %s", order.user_id, order.id, exc)
