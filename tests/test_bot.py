from __future__ import annotations

import pytest

from shopbot import config as settings
from shopbot.db import MAX_QTY, Shop
from shopbot.handlers.orders import normalize_phone
from shopbot.keyboards import CartCB, CategoryCB, OrderCB, ProductCB

from .conftest import ADMIN, CUSTOMER, Harness


async def fill_cart_and_checkout(h: Harness) -> None:
    await h.press(ProductCB(action="add", id=1).pack())
    await h.press(ProductCB(action="add", id=1).pack())
    await h.press(CartCB(action="checkout").pack())
    await h.send("Ольга")
    await h.send("8 (900) 123-45-67")
    await h.send("Солодовый переулок, 7, кв. 3")
    await h.press("confirm:yes")


async def test_start_escapes_user_name(harness):
    await harness.send("/start")
    text = harness.last_text()
    assert "Оля &lt;b&gt;" in text
    assert ("Каталог", "catalog") in harness.buttons()


async def test_catalog_to_product(harness):
    await harness.press("catalog")
    assert "Каталог" in harness.last_text()
    first_category = harness.buttons()[0][1]
    await harness.press(first_category)
    assert "Каркассон" in [b[0].split(" · ")[0] for b in harness.buttons()]
    await harness.press(ProductCB(action="view", id=1).pack())
    assert "Каркассон" in harness.last_text() and "2 490 ₽" in harness.last_text()


async def test_unknown_product_and_category(harness):
    await harness.press(ProductCB(action="add", id=999).pack())
    await harness.press(CategoryCB(id=999).pack())
    assert harness.alerts()[-2:] == ["Такой игры уже нет", "Раздел не найден"]


async def test_cart_survives_restart(tmp_path):
    db = tmp_path / "shop.db"
    first = Shop(db)
    first.add_to_cart(CUSTOMER, 1)
    first.close()
    second = Shop(db)
    assert [(ln.product.title, ln.qty) for ln in second.cart(CUSTOMER)] == [("Каркассон", 1)]
    second.close()


async def test_quantity_is_capped(shop):
    for _ in range(MAX_QTY + 5):
        shop.add_to_cart(CUSTOMER, 2)
    shop.change_qty(CUSTOMER, 2, +1)
    assert shop.cart(CUSTOMER)[0].qty == MAX_QTY


async def test_minus_to_zero_removes_line(harness, shop):
    shop.add_to_cart(CUSTOMER, 3)
    await harness.press(CartCB(action="dec", id=3).pack())
    assert shop.cart(CUSTOMER) == []
    assert "Корзина пуста" in harness.last_text()


async def test_checkout_rejects_bad_phone_and_short_address(harness):
    await harness.press(ProductCB(action="add", id=1).pack())
    await harness.press(CartCB(action="checkout").pack())
    await harness.send("Ольга")
    await harness.send("позвоните мне")
    assert "Не получилось разобрать номер" in harness.last_text()
    await harness.send("+7 900 123 45 67")
    await harness.send("дом")
    assert "Адрес слишком короткий" in harness.last_text()


async def test_full_order_with_demo_payment(harness, shop):
    await fill_cart_and_checkout(harness)
    [order] = shop.orders()
    assert order.status == "new" and order.total == 2 * 2490 and order.phone == "+79001234567"
    assert shop.cart(CUSTOMER) == []
    assert "Оплатить" in harness.buttons()[0][0]

    await harness.press(OrderCB(action="pay", id=order.id).pack())
    assert shop.order(order.id).status == "paid"
    to_admin = [m for m in harness.sent("SendMessage") if m.chat_id == ADMIN]
    assert len(to_admin) == 1 and "Солодовый" in to_admin[0].text


async def test_paying_twice_does_nothing(harness, shop):
    await fill_cart_and_checkout(harness)
    order_id = shop.orders()[0].id
    await harness.press(OrderCB(action="pay", id=order_id).pack())
    await harness.press(OrderCB(action="pay", id=order_id).pack())
    assert harness.alerts()[-1] == "Заказ уже оплачен"
    assert len([m for m in harness.sent("SendMessage") if m.chat_id == ADMIN]) == 1


async def test_other_user_cannot_pay_someone_elses_order(harness, shop):
    await fill_cart_and_checkout(harness)
    order_id = shop.orders()[0].id
    await harness.press(OrderCB(action="pay", id=order_id).pack(), user_id=3000)
    assert harness.alerts()[-1] == "Заказ не найден"
    assert shop.order(order_id).status == "new"


async def test_admin_actions_need_admin(harness, shop):
    await fill_cart_and_checkout(harness)
    order_id = shop.orders()[0].id
    await harness.press(OrderCB(action="done", id=order_id).pack(), user_id=CUSTOMER)
    assert harness.alerts()[-1] == "Недостаточно прав"
    assert shop.order(order_id).status == "new"

    await harness.press(OrderCB(action="done", id=order_id).pack(), user_id=ADMIN)
    assert shop.order(order_id).status == "done"
    note = [m for m in harness.sent("SendMessage") if m.chat_id == CUSTOMER][-1]
    assert "передан в доставку" in note.text


async def test_stats_only_for_admin(harness):
    await harness.send("/stats", user_id=CUSTOMER)
    assert "только для администратора" in harness.last_text()
    await harness.send("/stats", user_id=ADMIN)
    assert "Выручка" in harness.last_text()


@pytest.mark.parametrize(("raw", "expected"), [
    ("+7 (900) 123-45-67", "+79001234567"),
    ("89001234567", "+79001234567"),
    ("8 900 123 45 67", "+79001234567"),
    ("123", None),
    ("+1 900 123 45 67", None),
])
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_config_errors(tmp_path):
    missing = tmp_path / "none.env"
    with pytest.raises(settings.ConfigError, match="не задан BOT_TOKEN"):
        settings.load(missing, environ={})
    with pytest.raises(settings.ConfigError, match="не число"):
        settings.load(missing, environ={"BOT_TOKEN": "123456789:AAH-abcdefghijklmnopqrstuvwxyz012345",
                                        "ADMIN_IDS": "1, me"})
    cfg = settings.load(missing, environ={"BOT_TOKEN": "123456789:AAH-abcdefghijklmnopqrstuvwxyz012345",
                                          "ADMIN_IDS": "1, 2", "DEMO_PAYMENTS": "0"})
    assert cfg.admins == {1, 2} and not cfg.demo_payments
