from __future__ import annotations

from contextlib import suppress
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from .. import keyboards as kb
from ..db import Line, Shop
from ..keyboards import CartCB, CategoryCB, ProductCB, rub

router = Router(name="shop")

GREETING = (
    "Здравствуйте, {name}. Это «Ход», магазин настольных игр.\n\n"
    "В каталоге семейные игры, стратегии и игры для компании. Соберите корзину, "
    "оформление займёт минуту, доставка по Москве на следующий день."
)


async def show(cb: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None) -> None:
    """Edits the message the button belongs to; Telegram rejects an edit that changes nothing, that is fine."""
    if isinstance(cb.message, Message):
        with suppress(TelegramBadRequest):
            await cb.message.edit_text(text, reply_markup=markup)
    await cb.answer()


def cart_text(lines: list[Line]) -> str:
    if not lines:
        return "<b>Корзина пуста</b>\n\nЗагляните в каталог."
    rows = [f"{escape(ln.product.title)} — {ln.qty} × {rub(ln.product.price)} = {rub(ln.sum)}" for ln in lines]
    return "<b>Корзина</b>\n\n" + "\n".join(rows) + f"\n\n<b>Итого: {rub(sum(ln.sum for ln in lines))}</b>"


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    name = escape(message.from_user.first_name if message.from_user else "")
    await message.answer(GREETING.format(name=name), reply_markup=kb.home())


@router.callback_query(F.data == "catalog")
async def catalog(cb: CallbackQuery, shop: Shop) -> None:
    await show(cb, "<b>Каталог</b>\nВыберите раздел:", kb.categories(shop.categories()))


@router.callback_query(CategoryCB.filter())
async def category(cb: CallbackQuery, callback_data: CategoryCB, shop: Shop) -> None:
    title = shop.category_title(callback_data.id)
    items = shop.products(callback_data.id)
    if not title or not items:
        await cb.answer("Раздел не найден", show_alert=True)
        return
    await show(cb, f"<b>{escape(title)}</b>\nВыберите игру:", kb.products(items))


@router.callback_query(ProductCB.filter(F.action == "view"))
async def product(cb: CallbackQuery, callback_data: ProductCB, shop: Shop) -> None:
    item = shop.product(callback_data.id)
    if not item:
        await cb.answer("Такой игры уже нет", show_alert=True)
        return
    text = f"<b>{escape(item.title)}</b>\n\n{escape(item.description)}\n\nЦена: <b>{rub(item.price)}</b>"
    await show(cb, text, kb.product(item))


@router.callback_query(ProductCB.filter(F.action == "add"))
async def add(cb: CallbackQuery, callback_data: ProductCB, shop: Shop) -> None:
    item = shop.product(callback_data.id)
    if not item or not cb.from_user:
        await cb.answer("Такой игры уже нет", show_alert=True)
        return
    qty = shop.add_to_cart(cb.from_user.id, item.id)
    await cb.answer(f"«{item.title}» в корзине, {qty} шт.")


@router.callback_query(F.data == "cart")
async def cart(cb: CallbackQuery, shop: Shop) -> None:
    lines = shop.cart(cb.from_user.id)
    await show(cb, cart_text(lines), kb.cart(lines))


@router.callback_query(CartCB.filter(F.action.in_({"inc", "dec", "clear"})))
async def cart_change(cb: CallbackQuery, callback_data: CartCB, shop: Shop) -> None:
    user = cb.from_user.id
    if callback_data.action == "clear":
        shop.clear_cart(user)
    else:
        shop.change_qty(user, callback_data.id, 1 if callback_data.action == "inc" else -1)
    lines = shop.cart(user)
    await show(cb, cart_text(lines), kb.cart(lines))
