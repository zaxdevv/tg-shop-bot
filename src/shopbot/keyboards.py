from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .db import Line, Product


class CategoryCB(CallbackData, prefix="cat"):
    id: int


class ProductCB(CallbackData, prefix="prd"):
    action: str
    id: int


class CartCB(CallbackData, prefix="crt"):
    action: str
    id: int = 0


class OrderCB(CallbackData, prefix="ord"):
    action: str
    id: int


def rub(value: int) -> str:
    return f"{value:,}".replace(",", " ") + " ₽"


def home() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Каталог", callback_data="catalog")
    kb.button(text="Корзина", callback_data="cart")
    return kb.as_markup()


def categories(items: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for category_id, title in items:
        kb.button(text=title, callback_data=CategoryCB(id=category_id))
    kb.button(text="Корзина", callback_data="cart")
    kb.adjust(2)
    return kb.as_markup()


def products(items: list[Product]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in items:
        kb.button(text=f"{p.title} · {rub(p.price)}", callback_data=ProductCB(action="view", id=p.id))
    kb.button(text="← Категории", callback_data="catalog")
    kb.adjust(1)
    return kb.as_markup()


def product(item: Product) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="В корзину", callback_data=ProductCB(action="add", id=item.id))
    kb.button(text="Корзина", callback_data="cart")
    kb.button(text="← Назад", callback_data=CategoryCB(id=item.category_id))
    kb.adjust(1, 2)
    return kb.as_markup()


def cart(lines: list[Line]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for line in lines:
        kb.button(text="−", callback_data=CartCB(action="dec", id=line.product.id))
        kb.button(text=f"{line.product.title} × {line.qty}", callback_data=ProductCB(action="view", id=line.product.id))
        kb.button(text="+", callback_data=CartCB(action="inc", id=line.product.id))
    sizes = [3] * len(lines)
    if lines:
        kb.button(text="Оформить заказ", callback_data=CartCB(action="checkout"))
        kb.button(text="Очистить", callback_data=CartCB(action="clear"))
        sizes += [1, 1]
    kb.button(text="← Каталог", callback_data="catalog")
    kb.adjust(*sizes, 1)
    return kb.as_markup()


def confirm() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Всё верно", callback_data="confirm:yes")
    kb.button(text="Отменить", callback_data="confirm:no")
    return kb.as_markup()


def pay(order_id: int, total: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=f"Оплатить {rub(total)} (демо)", callback_data=OrderCB(action="pay", id=order_id))
    kb.button(text="Отменить заказ", callback_data=OrderCB(action="cancel", id=order_id))
    kb.adjust(1)
    return kb.as_markup()


def admin_order(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Передан в доставку", callback_data=OrderCB(action="done", id=order_id))
    kb.button(text="Отменить", callback_data=OrderCB(action="reject", id=order_id))
    return kb.as_markup()
