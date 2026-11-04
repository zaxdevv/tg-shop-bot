from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

TOKEN = re.compile(r"^\d{5,12}:[A-Za-z0-9_-]{30,}$")


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    token: str
    admins: frozenset[int]
    db_path: Path
    demo_payments: bool


def read_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip("'\"")
    return values


def load(env_file: Path | str = ".env", environ: dict[str, str] | None = None) -> Config:
    env = {**read_env_file(Path(env_file)), **(os.environ if environ is None else environ)}

    token = env.get("BOT_TOKEN", "").strip()
    if not token:
        raise ConfigError(
            "не задан BOT_TOKEN.\n"
            "1. Создайте бота у @BotFather и скопируйте токен.\n"
            "2. Скопируйте .env.example в .env и впишите токен после BOT_TOKEN=.\n"
            "3. Запустите снова: uv run shopbot")
    if not TOKEN.match(token):
        raise ConfigError("BOT_TOKEN не похож на токен: ожидается вид 123456789:AA..., его выдаёт @BotFather")

    admins = set()
    for part in filter(None, (p.strip() for p in env.get("ADMIN_IDS", "").split(","))):
        if not part.isdigit():
            raise ConfigError(
                f"ADMIN_IDS — числовые id через запятую, а {part!r} не число. Свой id покажет @userinfobot")
        admins.add(int(part))

    demo = env.get("DEMO_PAYMENTS", "1").strip().lower()
    if demo not in ("1", "0", "true", "false", "yes", "no"):
        raise ConfigError("DEMO_PAYMENTS — 1 или 0")

    return Config(
        token=token,
        admins=frozenset(admins),
        db_path=Path(env.get("DB_PATH") or "data/shop.db"),
        demo_payments=demo in ("1", "true", "yes"),
    )
