from __future__ import annotations

import logging
import re
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import keyboards as kb
from ..config import Config
from ..db import STATUSES, Order, Shop
from ..keyboards import CartCB, OrderCB, rub
from .shop import cart_text, show

router = Router(name="orders")
log = logging.getLogger(__name__)


class Checkout(StatesGroup):
    name = State()
    phone = State()
    address = State()
    confirm = State()


def normalize_phone(text: str) -> str | None:
    """Accept domestic and international prefixes and remove separators."""
    digits = re.sub(r"[\s()\-]", "", text)
    if re.fullmatch(r"(\+7|8)\d{10}", digits):
        return "+7" + digits[-10:]
    return None


def order_text(shop: Shop, order: Order, for_admin: bool = False) -> str:
    items = "\n".join(f"{escape(t)}: {q} × {rub(p)}" for t, p, q in shop.order_items(order.id))
    lines = [f"<b>Заказ №{order.id}</b> · {STATUSES[order.status]}", "", items, f"Итого: <b>{rub(order.total)}</b>"]
    if for_admin:
        who = f"@{escape(order.username)}" if order.username else f"id {order.user_id}"
        lines += ["", f"{escape(order.customer_name)}, {escape(order.phone)}, {who}", escape(order.address)]
    return "\n".join(lines)


async def tell_admins(bot: Bot, config: Config, shop: Shop, order: Order) -> None:
    for admin in config.admins:
        try:
            await bot.send_message(admin, order_text(shop, order, for_admin=True),
                                   reply_markup=kb.admin_order(order.id))
        except TelegramAPIError as exc:
            log.warning("admin %s did not get order %s: %s", admin, order.id, exc)


@router.callback_query(CartCB.filter(F.action == "checkout"))
async def checkout(cb: CallbackQuery, state: FSMContext, shop: Shop) -> None:
    if not shop.cart(cb.from_user.id):
        await cb.answer("Корзина пуста", show_alert=True)
        return
    await state.set_state(Checkout.name)
    if isinstance(cb.message, Message):
        await cb.message.answer("Как к вам обращаться? Напишите имя получателя.\n\n/cancel: отменить оформление")
    await cb.answer()


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Оформление отменено, корзина сохранена.", reply_markup=kb.home())


@router.message(Checkout.name, F.text)
async def got_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not 2 <= len(name) <= 60:
        await message.answer("В имени должно быть от 2 до 60 символов. Напишите ещё раз:")
        return
    await state.update_data(name=name)
    await state.set_state(Checkout.phone)
    await message.answer("Телефон для курьера, 11 цифр, с +7 или 8 в начале:")


@router.message(Checkout.phone, F.text)
async def got_phone(message: Message, state: FSMContext) -> None:
    phone = normalize_phone(message.text or "")
    if not phone:
        await message.answer("Не получилось разобрать номер. Нужно 11 цифр, например в формате +7 ХХХ ХХХ-ХХ-ХХ:")
        return
    await state.update_data(phone=phone)
    await state.set_state(Checkout.address)
    await message.answer("Адрес доставки: улица, дом, квартира. Можно добавить комментарий для курьера.")


@router.message(Checkout.address, F.text)
async def got_address(message: Message, state: FSMContext, shop: Shop) -> None:
    address = (message.text or "").strip()
    if not 8 <= len(address) <= 300:
        await message.answer("Адрес слишком короткий или длинный. Уточните, пожалуйста:")
        return
    await state.update_data(address=address)
    await state.set_state(Checkout.confirm)
    data = await state.get_data()
    lines = shop.cart(message.from_user.id if message.from_user else 0)
    text = (f"{cart_text(lines)}\n\nПолучатель: {escape(data['name'])}, {escape(data['phone'])}\n"
            f"Адрес: {escape(address)}\n\nВсё верно?")
    await message.answer(text, reply_markup=kb.confirm())


@router.message(StateFilter(Checkout.name, Checkout.phone, Checkout.address))
async def not_text(message: Message) -> None:
    await message.answer("На этом шаге нужен обычный текст.")


@router.callback_query(Checkout.confirm, F.data == "confirm:yes")
async def confirmed(cb: CallbackQuery, state: FSMContext, shop: Shop, config: Config, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    user = cb.from_user
    order = shop.place_order(user.id, user.username or "", data["name"], data["phone"], data["address"])
    if order is None:
        await show(cb, "Корзина опустела, заказ не создан.", kb.home())
        return
    if config.demo_payments:
        await show(cb, order_text(shop, order) + "\n\nЭто демо-режим: настоящих денег кнопка не списывает.",
                   kb.pay(order.id, order.total))
    else:
        await show(cb, order_text(shop, order) + "\n\nМенеджер позвонит, чтобы подтвердить заказ.", kb.home())
        await tell_admins(bot, config, shop, order)


@router.callback_query(Checkout.confirm, F.data == "confirm:no")
async def declined(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show(cb, "Оформление отменено, корзина сохранена.", kb.home())


@router.callback_query(F.data.startswith("confirm:"))
async def stale_confirm(cb: CallbackQuery) -> None:
    await cb.answer("Это оформление уже закончено", show_alert=True)


@router.callback_query(OrderCB.filter(F.action.in_({"pay", "cancel"})))
async def customer_action(cb: CallbackQuery, callback_data: OrderCB, shop: Shop, config: Config, bot: Bot) -> None:
    order = shop.order(callback_data.id)
    if order is None or order.user_id != cb.from_user.id:
        await cb.answer("Заказ не найден", show_alert=True)
        return
    if callback_data.action == "pay":
        if not config.demo_payments:
            await cb.answer("Оплата через бота выключена", show_alert=True)
            return
        updated = shop.set_status(order.id, "paid", expected=("new",))
    else:
        updated = shop.set_status(order.id, "cancelled", expected=("new",))
    if updated is None:
        await cb.answer(f"Заказ уже {STATUSES[order.status]}", show_alert=True)
        return
    note = "Оплата прошла (демо). Соберём заказ сегодня." if updated.status == "paid" else "Заказ отменён."
    await show(cb, order_text(shop, updated) + f"\n\n{note}", kb.home())
    if updated.status == "paid":
        await tell_admins(bot, config, shop, updated)


@router.message(Command("orders"))
async def my_orders(message: Message, shop: Shop) -> None:
    orders = shop.orders(user_id=message.from_user.id if message.from_user else 0, limit=5)
    if not orders:
        await message.answer("Заказов пока нет.", reply_markup=kb.home())
        return
    await message.answer("\n\n".join(order_text(shop, o) for o in orders))
