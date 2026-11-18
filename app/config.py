"""Application-wide constants and filesystem locations."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Password Manager"
APP_SLUG = "PasswordManager"
APP_VERSION = "1.0.0"

VAULT_FILENAME = "vault.db"
VAULT_FORMAT_VERSION = 1
DB_SCHEMA_VERSION = 1
BACKUP_SUFFIX = ".pmvault"

MIN_MASTER_PASSWORD_LENGTH = 8
MAX_MASTER_PASSWORD_LENGTH = 256

# AES-256-GCM
KEY_SIZE = 32
SALT_SIZE = 16
NONCE_SIZE = 12
AUTH_TAG_SIZE = 16

# Argon2id defaults. Values are stored in the vault so they can be raised later.
ARGON2_MEMORY_KIB = 64 * 1024
ARGON2_TIME_COST = 3
ARGON2_PARALLELISM = 4
ARGON2_HASH_LEN = KEY_SIZE

AUTO_LOCK_OPTIONS: tuple[tuple[int, str], ...] = (
    (0, "Никогда"),
    (1, "Через 1 минуту"),
    (5, "Через 5 минут"),
    (10, "Через 10 минут"),
    (15, "Через 15 минут"),
)
DEFAULT_AUTO_LOCK_MINUTES = 5

CLIPBOARD_OPTIONS: tuple[tuple[int, str], ...] = (
    (0, "Не очищать"),
    (15, "Через 15 секунд"),
    (30, "Через 30 секунд"),
    (60, "Через 1 минуту"),
)
DEFAULT_CLIPBOARD_CLEAR_SECONDS = 30

DEFAULT_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("social", "Социальные сети"),
    ("games", "Игры"),
    ("work", "Работа"),
    ("email", "Почта"),
    ("banks", "Банки"),
    ("other", "Другое"),
)

MAX_TITLE_LENGTH = 200
MAX_USERNAME_LENGTH = 256
MAX_PASSWORD_LENGTH = 1024
MAX_URL_LENGTH = 2048
MAX_NOTES_LENGTH = 5000
MAX_CATEGORY_NAME_LENGTH = 40


def data_dir() -> Path:
    """Return the directory that stores the vault and logs.

    ``PM_DATA_DIR`` overrides the location (used by tests and portable setups).
    """

    override = os.environ.get("PM_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()

    if os.name == "nt":
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Roaming"
        return root / APP_SLUG
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_SLUG
    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / APP_SLUG


def vault_path() -> Path:
    return data_dir() / VAULT_FILENAME


def logs_dir() -> Path:
    return data_dir() / "logs"


def ensure_directories() -> None:
    for path in (data_dir(), logs_dir()):
        path.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            try:
                path.chmod(0o700)
            except OSError:
                pass
