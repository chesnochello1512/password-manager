"""Domain models shared by the storage, service and UI layers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app import config
from app.exceptions import ValidationError


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_timestamp(value: str | None) -> datetime:
    if not value:
        return utc_now()
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Некорректная дата в хранилище.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_timestamp(value: datetime | None) -> str:
    return (value or utc_now()).astimezone(timezone.utc).isoformat(timespec="seconds")


def display_timestamp(value: datetime | None) -> str:
    if not value:
        return "—"
    return value.astimezone().strftime("%d.%m.%Y %H:%M")


@dataclass(slots=True)
class Category:
    id: str
    name: str
    builtin: bool = False
    order: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "builtin": bool(self.builtin),
            "order": int(self.order),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Category:
        category_id = str(raw.get("id", "")).strip()
        name = str(raw.get("name", "")).strip()
        if not category_id or not name:
            raise ValidationError("Повреждена категория в настройках хранилища.")
        if len(name) > config.MAX_CATEGORY_NAME_LENGTH:
            name = name[: config.MAX_CATEGORY_NAME_LENGTH]
        return cls(
            id=category_id,
            name=name,
            builtin=bool(raw.get("builtin", False)),
            order=int(raw.get("order", 0) or 0),
        )


def default_categories() -> list[Category]:
    return [
        Category(id=category_id, name=name, builtin=True, order=index)
        for index, (category_id, name) in enumerate(config.DEFAULT_CATEGORIES)
    ]


@dataclass(slots=True)
class AppSettings:
    categories: list[Category] = field(default_factory=default_categories)
    auto_lock_minutes: int = config.DEFAULT_AUTO_LOCK_MINUTES
    clipboard_clear_seconds: int = config.DEFAULT_CLIPBOARD_CLEAR_SECONDS

    def to_dict(self) -> dict[str, Any]:
        return {
            "categories": [category.to_dict() for category in self.categories],
            "auto_lock_minutes": self.auto_lock_minutes,
            "clipboard_clear_seconds": self.clipboard_clear_seconds,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> AppSettings:
        settings = cls()
        if not isinstance(raw, dict):
            return settings

        categories_raw = raw.get("categories")
        parsed: list[Category] = []
        if isinstance(categories_raw, list):
            seen: set[str] = set()
            for item in categories_raw:
                if not isinstance(item, dict):
                    continue
                try:
                    category = Category.from_dict(item)
                except (ValidationError, TypeError, ValueError):
                    continue
                if category.id in seen:
                    continue
                seen.add(category.id)
                parsed.append(category)
        if parsed:
            settings.categories = parsed

        auto_lock = raw.get("auto_lock_minutes", settings.auto_lock_minutes)
        clipboard = raw.get("clipboard_clear_seconds", settings.clipboard_clear_seconds)
        try:
            auto_lock = int(auto_lock)
        except (TypeError, ValueError):
            auto_lock = config.DEFAULT_AUTO_LOCK_MINUTES
        if auto_lock not in {value for value, _ in config.AUTO_LOCK_OPTIONS}:
            auto_lock = config.DEFAULT_AUTO_LOCK_MINUTES

        try:
            clipboard = int(clipboard)
        except (TypeError, ValueError):
            clipboard = config.DEFAULT_CLIPBOARD_CLEAR_SECONDS
        if clipboard not in {value for value, _ in config.CLIPBOARD_OPTIONS}:
            clipboard = config.DEFAULT_CLIPBOARD_CLEAR_SECONDS

        settings.auto_lock_minutes = auto_lock
        settings.clipboard_clear_seconds = clipboard

        known_ids = {category.id for category in settings.categories}
        if "other" not in known_ids:
            settings.categories.append(Category("other", "Другое", builtin=True, order=len(settings.categories)))
        settings.categories.sort(key=lambda item: (item.order, item.name.casefold()))
        return settings

    def category(self, category_id: str) -> Category | None:
        return next((item for item in self.categories if item.id == category_id), None)

    def category_name(self, category_id: str) -> str:
        category = self.category(category_id)
        return category.name if category else "Другое"

    def ensure_category(self, category_id: str) -> str:
        return category_id if self.category(category_id) else "other"


@dataclass(slots=True)
class PasswordRecord:
    id: str
    title: str
    username: str
    password: str
    url: str
    category_id: str
    notes: str
    favorite: bool
    created_at: datetime
    updated_at: datetime
    format_version: int = config.VAULT_FORMAT_VERSION
    key_version: int = 1
    _search_text: str = field(default="", init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._search_text = f"{self.title}\n{self.username}\n{self.url}".casefold()

    @property
    def search_text(self) -> str:
        """Pre-folded text used by the in-memory search."""

        return self._search_text

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())

    def to_payload(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "username": self.username,
            "password": self.password,
            "url": self.url,
            "category_id": self.category_id,
            "notes": self.notes,
            "favorite": self.favorite,
        }

    @classmethod
    def from_payload(
        cls,
        record_id: str,
        payload: dict[str, Any],
        created_at: datetime,
        updated_at: datetime,
        format_version: int,
        key_version: int,
    ) -> PasswordRecord:
        if not isinstance(payload, dict):
            raise ValidationError("Повреждена запись хранилища.")

        def text(name: str, limit: int, required: bool = False) -> str:
            value = payload.get(name, "")
            if value is None:
                value = ""
            if not isinstance(value, str):
                raise ValidationError(f"Поле «{name}» имеет неверный тип.")
            value = value.strip() if name != "password" else value
            if required and not value:
                raise ValidationError("В записи отсутствует название.")
            if len(value) > limit:
                value = value[:limit]
            return value

        category_id = payload.get("category_id") or "other"
        if not isinstance(category_id, str):
            category_id = "other"

        return cls(
            id=record_id,
            title=text("title", config.MAX_TITLE_LENGTH, required=True),
            username=text("username", config.MAX_USERNAME_LENGTH),
            password=text("password", config.MAX_PASSWORD_LENGTH),
            url=text("url", config.MAX_URL_LENGTH),
            category_id=category_id,
            notes=text("notes", config.MAX_NOTES_LENGTH),
            favorite=bool(payload.get("favorite", False)),
            created_at=created_at,
            updated_at=updated_at,
            format_version=format_version,
            key_version=key_version,
        )
