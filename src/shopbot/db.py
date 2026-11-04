from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

MAX_QTY = 20

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id    INTEGER PRIMARY KEY,
    title TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY,
    category_id INTEGER NOT NULL REFERENCES categories(id),
    title       TEXT NOT NULL,
    description TEXT NOT NULL,
    price       INTEGER NOT NULL CHECK (price > 0)
);
CREATE TABLE IF NOT EXISTS cart (
    user_id    INTEGER NOT NULL,
    product_id INTEGER NOT NULL REFERENCES products(id),
    qty        INTEGER NOT NULL CHECK (qty BETWEEN 1 AND 20),
    PRIMARY KEY (user_id, product_id)
);
CREATE TABLE IF NOT EXISTS orders (
    id            INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL,
    username      TEXT NOT NULL DEFAULT '',
    customer_name TEXT NOT NULL,
    phone         TEXT NOT NULL,
    address       TEXT NOT NULL,
    total         INTEGER NOT NULL,
    status        TEXT NOT NULL DEFAULT 'new',
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS order_items (
    order_id      INTEGER NOT NULL REFERENCES orders(id),
    product_id    INTEGER NOT NULL,
    product_title TEXT NOT NULL,
    price         INTEGER NOT NULL,
    qty           INTEGER NOT NULL
);
"""

STATUSES = {"new": "ждёт оплаты", "paid": "оплачен", "done": "передан в доставку", "cancelled": "отменён"}

CATALOG: dict[str, list[tuple[str, str, int]]] = {
    "Семейные": [
        ("Каркассон", "Выкладываете плитки, строите дороги и города. Правила объясняются за пять минут, "
         "партия идёт сорок. Хороший первый шаг после «Монополии».", 2490),
        ("Диксит", "Описываете свою карточку так, чтобы угадали не все. Странные картинки, "
         "много разговоров, от трёх игроков.", 3290),
        ("Имаджинариум", "Похож на «Диксит», но с русскими художниками и более мрачными картинками.", 2190),
    ],
    "Стратегии": [
        ("Колонизаторы", "Ресурсы, дороги, торговля с соседями. Классика, с которой многие начинают "
         "серьёзные настолки. На 3-4 игроков.", 4290),
        ("Зельеварение", "Собираете ингредиенты и варите зелья раньше соперников. Карточная стратегия "
         "на полчаса.", 3690),
    ],
    "Пати-игры": [
        ("Кодовые имена", "Две команды, одно слово-подсказка, нужно угадать свои карты и не задеть чужие.", 1790),
        ("Манчкин", "Убиваете монстров, подставляете друзей и первым доходите до десятого уровня.", 1990),
        ("Свинтус", "Карточная гонка, где правила меняются на ходу. Подходит для детей и взрослых.", 990),
        ("Экивоки", "Объясняете слова жестами, рисунком или парой слов, пока не кончилось время.", 1290),
    ],
    "Для детей": [
        ("Барабашка", "Игра на реакцию: успеть схватить нужный предмет раньше всех. С шести лет.", 1190),
        ("Дженга", "Вытаскиваете бруски из башни и стараетесь её не уронить.", 1490),
    ],
}


@dataclass(frozen=True)
class Product:
    id: int
    category_id: int
    title: str
    description: str
    price: int


@dataclass(frozen=True)
class Line:
    product: Product
    qty: int

    @property
    def sum(self) -> int:
        return self.product.price * self.qty


@dataclass(frozen=True)
class Order:
    id: int
    user_id: int
    username: str
    customer_name: str
    phone: str
    address: str
    total: int
    status: str
    created_at: str


class Shop:
    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        self._seed()

    def close(self) -> None:
        self.db.close()

    def _seed(self) -> None:
        if self.db.execute("SELECT 1 FROM products LIMIT 1").fetchone():
            return
        with self.db:
            for title, products in CATALOG.items():
                category_id = self.db.execute("INSERT INTO categories (title) VALUES (?)", (title,)).lastrowid
                self.db.executemany(
                    "INSERT INTO products (category_id, title, description, price) VALUES (?, ?, ?, ?)",
                    [(category_id, *p) for p in products])

    def categories(self) -> list[tuple[int, str]]:
        return [(r["id"], r["title"]) for r in self.db.execute("SELECT id, title FROM categories ORDER BY id")]

    def category_title(self, category_id: int) -> str | None:
        row = self.db.execute("SELECT title FROM categories WHERE id = ?", (category_id,)).fetchone()
        return row["title"] if row else None

    def products(self, category_id: int) -> list[Product]:
        rows = self.db.execute("SELECT * FROM products WHERE category_id = ? ORDER BY id", (category_id,))
        return [Product(**dict(r)) for r in rows]

    def product(self, product_id: int) -> Product | None:
        row = self.db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        return Product(**dict(row)) if row else None

    def add_to_cart(self, user_id: int, product_id: int) -> int:
        """Returns the new quantity; stays at MAX_QTY instead of growing forever."""
        with self.db:
            self.db.execute(
                "INSERT INTO cart (user_id, product_id, qty) VALUES (?, ?, 1) "
                "ON CONFLICT (user_id, product_id) DO UPDATE SET qty = MIN(qty + 1, ?)",
                (user_id, product_id, MAX_QTY))
        row = self.db.execute("SELECT qty FROM cart WHERE user_id = ? AND product_id = ?", (user_id, product_id))
        return int(row.fetchone()["qty"])

    def change_qty(self, user_id: int, product_id: int, delta: int) -> None:
        with self.db:
            self.db.execute("DELETE FROM cart WHERE user_id = ? AND product_id = ? AND qty + ? <= 0",
                            (user_id, product_id, delta))
            self.db.execute("UPDATE cart SET qty = MIN(qty + ?, ?) WHERE user_id = ? AND product_id = ?",
                            (delta, MAX_QTY, user_id, product_id))

    def remove_from_cart(self, user_id: int, product_id: int) -> None:
        with self.db:
            self.db.execute("DELETE FROM cart WHERE user_id = ? AND product_id = ?", (user_id, product_id))

    def clear_cart(self, user_id: int) -> None:
        with self.db:
            self.db.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))

    def cart(self, user_id: int) -> list[Line]:
        rows = self.db.execute(
            "SELECT p.*, c.qty FROM cart c JOIN products p ON p.id = c.product_id WHERE c.user_id = ? ORDER BY p.id",
            (user_id,))
        result = []
        for r in rows:
            data = dict(r)
            qty = data.pop("qty")
            result.append(Line(Product(**data), qty))
        return result

    def place_order(self, user_id: int, username: str, name: str, phone: str, address: str) -> Order | None:
        """Moves the cart into an order in one transaction. None if the cart is empty."""
        lines = self.cart(user_id)
        if not lines:
            return None
        total = sum(line.sum for line in lines)
        created = datetime.now().isoformat(timespec="seconds")
        with self.db:
            order_id = self.db.execute(
                "INSERT INTO orders (user_id, username, customer_name, phone, address, total, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)", (user_id, username, name, phone, address, total, created)).lastrowid
            self.db.executemany(
                "INSERT INTO order_items (order_id, product_id, product_title, price, qty) VALUES (?, ?, ?, ?, ?)",
                [(order_id, ln.product.id, ln.product.title, ln.product.price, ln.qty) for ln in lines])
            self.db.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
        return self.order(int(order_id or 0))

    def order(self, order_id: int) -> Order | None:
        row = self.db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        return Order(**dict(row)) if row else None

    def order_items(self, order_id: int) -> list[tuple[str, int, int]]:
        rows = self.db.execute("SELECT product_title, price, qty FROM order_items WHERE order_id = ?", (order_id,))
        return [(r["product_title"], r["price"], r["qty"]) for r in rows]

    def orders(self, user_id: int | None = None, limit: int = 10) -> list[Order]:
        if user_id is None:
            rows = self.db.execute("SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,))
        else:
            rows = self.db.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))
        return [Order(**dict(r)) for r in rows]

    def set_status(self, order_id: int, status: str, expected: tuple[str, ...]) -> Order | None:
        """Changes status only from one of the expected states, so a double tap cannot pay or cancel twice."""
        if status not in STATUSES:
            raise ValueError(status)
        with self.db:
            changed = self.db.execute(
                "UPDATE orders SET status = ? WHERE id = ? AND status IN (SELECT value FROM json_each(?))",
                (status, order_id, json.dumps(expected))).rowcount
        return self.order(order_id) if changed else None

    def stats(self) -> tuple[int, int, list[tuple[str, int]]]:
        row = self.db.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(total), 0) AS revenue FROM orders WHERE status IN ('paid', 'done')"
        ).fetchone()
        top = self.db.execute(
            "SELECT i.product_title, SUM(i.qty) AS sold FROM order_items i JOIN orders o ON o.id = i.order_id "
            "WHERE o.status IN ('paid', 'done') GROUP BY i.product_title ORDER BY sold DESC LIMIT 5")
        return int(row["n"]), int(row["revenue"]), [(r["product_title"], int(r["sold"])) for r in top]
