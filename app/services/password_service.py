"""Business logic for encrypted password records and categories."""

from __future__ import annotations

import copy
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import TypedDict
from urllib.parse import urlsplit

from app import config
from app.database.database import Database, RawRecord
from app.exceptions import (
    DecryptionError,
    ValidationError,
    VaultCorruptedError,
    VaultLockedError,
)
from app.models import (
    AppSettings,
    Category,
    PasswordRecord,
    format_timestamp,
    parse_timestamp,
    utc_now,
)
from app.security import encryption
from app.security.key_manager import KeyManager

logger = logging.getLogger(__name__)


class _ValidatedFields(TypedDict):
    title: str
    username: str
    password: str
    url: str
    category_id: str
    notes: str
    favorite: bool


class PasswordService:
    """Decrypts the vault into memory and provides CRUD/search operations."""

    def __init__(self, database: Database, key_manager: KeyManager) -> None:
        self._db = database
        self._keys = key_manager
        self._records: dict[str, PasswordRecord] = {}
        self._settings: AppSettings | None = None
        self._loaded = False
        self.corrupt_records = 0
        self.load_warnings: list[str] = []

    # ------------------------------------------------------------------ loading
    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def settings(self) -> AppSettings:
        if self._settings is None:
            raise VaultLockedError("Хранилище заблокировано.")
        # Callers may edit a snapshot before saving it; return a copy so a
        # failed write can never leave the in-memory state half-updated.
        return copy.deepcopy(self._settings)

    def load(self) -> None:
        if not self._keys.unlocked:
            raise VaultLockedError("Хранилище заблокировано.")
        self.clear()
        self._settings = self._load_settings()
        self._records = self._load_records()
        self._loaded = True

    def clear(self) -> None:
        self._records.clear()
        self._settings = None
        self._loaded = False
        self.corrupt_records = 0
        self.load_warnings = []

    def _settings_aad(self) -> bytes:
        return encryption.build_aad(self._keys.vault_id, "settings")

    def _record_aad(self, record_id: str, format_version: int) -> bytes:
        return encryption.build_aad(self._keys.vault_id, "record", record_id, format_version)

    def _load_settings(self) -> AppSettings:
        raw = self._db.get_settings_raw()
        if raw is None:
            settings = AppSettings()
            self._store_settings(settings)
            return settings
        try:
            plaintext = encryption.decrypt_bytes(
                self._keys.key, raw.nonce, raw.ciphertext, self._settings_aad()
            )
            payload = json.loads(plaintext.decode("utf-8"))
            return AppSettings.from_dict(payload)
        except (DecryptionError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise VaultCorruptedError("Не удалось расшифровать настройки хранилища.") from exc

    def _load_records(self) -> dict[str, PasswordRecord]:
        records: dict[str, PasswordRecord] = {}
        warnings: list[str] = []
        for raw in self._db.iter_records_raw():
            try:
                plaintext = encryption.decrypt_bytes(
                    self._keys.key,
                    raw.nonce,
                    raw.ciphertext,
                    self._record_aad(raw.id, raw.format_version),
                )
                payload = json.loads(plaintext.decode("utf-8"))
                record = PasswordRecord.from_payload(
                    raw.id,
                    payload,
                    parse_timestamp(raw.created_at),
                    parse_timestamp(raw.updated_at),
                    raw.format_version,
                    raw.key_version,
                )
                if self._settings and not self._settings.category(record.category_id):
                    record.category_id = "other"
                records[record.id] = record
            except (DecryptionError, ValidationError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self.corrupt_records += 1
                logger.warning("Skipping damaged record %s (%s)", raw.id[:8], type(exc).__name__)
                warnings.append(f"Запись {raw.id[:8]}… повреждена и не была загружена.")

        self.load_warnings = warnings
        if warnings:
            logger.warning("%d damaged record(s) skipped", len(warnings))
        return records

    # ------------------------------------------------------------------ queries
    def list_records(
        self,
        search: str = "",
        category_id: str | None = None,
        favorites_only: bool = False,
    ) -> list[PasswordRecord]:
        self._require_loaded()
        needle = " ".join((search or "").casefold().split())
        result: list[PasswordRecord] = []
        for record in self._records.values():
            if favorites_only and not record.favorite:
                continue
            if category_id and record.category_id != category_id:
                continue
            if needle:
                if needle not in record.search_text:
                    continue
            result.append(record)
        result.sort(key=lambda item: (not item.favorite, item.title.casefold(), item.username.casefold()))
        return result

    def get_record(self, record_id: str) -> PasswordRecord:
        self._require_loaded()
        record = self._records.get(record_id)
        if record is None:
            raise ValidationError("Запись не найдена.")
        return record

    def count_all(self) -> int:
        self._require_loaded()
        return len(self._records)

    def count_favorites(self) -> int:
        self._require_loaded()
        return sum(1 for record in self._records.values() if record.favorite)

    def count_by_category(self, category_id: str) -> int:
        self._require_loaded()
        return sum(1 for record in self._records.values() if record.category_id == category_id)

    def stats(self) -> tuple[int, int, dict[str, int]]:
        """Return total, favorites and per-category counts in one pass."""

        self._require_loaded()
        counts: dict[str, int] = {}
        favorites = 0
        for record in self._records.values():
            counts[record.category_id] = counts.get(record.category_id, 0) + 1
            if record.favorite:
                favorites += 1
        return len(self._records), favorites, counts

    # ------------------------------------------------------------------ mutations
    def create_record(
        self,
        title: str,
        username: str = "",
        password: str = "",
        url: str = "",
        category_id: str = "other",
        notes: str = "",
        favorite: bool = False,
    ) -> PasswordRecord:
        self._require_loaded()
        cleaned = self._validate_fields(title, username, password, url, category_id, notes, favorite)
        now = utc_now()
        record = PasswordRecord(
            id=PasswordRecord.new_id(),
            created_at=now,
            updated_at=now,
            format_version=config.VAULT_FORMAT_VERSION,
            key_version=self._keys.key_version,
            **cleaned,
        )
        raw = self._encrypt_record(record)
        self._db.insert_record_raw(raw)
        self._records[record.id] = record
        return record

    def update_record(self, record_id: str, **fields: str | bool) -> PasswordRecord:
        self._require_loaded()
        existing = self.get_record(record_id)
        updated = self._build_updated_record(existing, **fields)
        raw = self._encrypt_record(updated)
        self._db.update_record_raw(raw)
        self._records[updated.id] = updated
        return updated

    def _build_updated_record(self, existing: PasswordRecord, **fields: str | bool) -> PasswordRecord:
        cleaned = self._validate_fields(
            str(fields.get("title", existing.title)),
            str(fields.get("username", existing.username)),
            str(fields.get("password", existing.password)),
            str(fields.get("url", existing.url)),
            str(fields.get("category_id", existing.category_id)),
            str(fields.get("notes", existing.notes)),
            bool(fields.get("favorite", existing.favorite)),
        )
        return PasswordRecord(
            id=existing.id,
            created_at=existing.created_at,
            updated_at=utc_now(),
            format_version=existing.format_version,
            key_version=self._keys.key_version,
            **cleaned,
        )

    def delete_record(self, record_id: str) -> None:
        self._require_loaded()
        self.get_record(record_id)
        self._db.delete_record(record_id)
        self._records.pop(record_id, None)

    def toggle_favorite(self, record_id: str) -> PasswordRecord:
        record = self.get_record(record_id)
        return self.update_record(record_id, favorite=not record.favorite)

    def _encrypt_record(self, record: PasswordRecord) -> RawRecord:
        payload = json.dumps(
            record.to_payload(), ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        nonce, ciphertext = encryption.encrypt_bytes(
            self._keys.key,
            payload,
            self._record_aad(record.id, record.format_version),
        )
        return RawRecord(
            id=record.id,
            nonce=nonce,
            ciphertext=ciphertext,
            key_version=record.key_version,
            format_version=record.format_version,
            created_at=format_timestamp(record.created_at),
            updated_at=format_timestamp(record.updated_at),
        )

    def _validate_fields(
        self,
        title: str,
        username: str,
        password: str,
        url: str,
        category_id: str,
        notes: str,
        favorite: bool,
    ) -> _ValidatedFields:
        title = (title or "").strip()
        username = (username or "").strip()
        password = password or ""
        url = (url or "").strip()
        notes = notes or ""
        category_id = (category_id or "other").strip() or "other"

        if not title:
            raise ValidationError("Укажите название сервиса.")
        if len(title) > config.MAX_TITLE_LENGTH:
            raise ValidationError(f"Название не должно превышать {config.MAX_TITLE_LENGTH} символов.")
        if not password:
            raise ValidationError("Укажите пароль.")
        if len(username) > config.MAX_USERNAME_LENGTH:
            raise ValidationError("Логин слишком длинный.")
        if len(password) > config.MAX_PASSWORD_LENGTH:
            raise ValidationError("Пароль слишком длинный.")
        if len(url) > config.MAX_URL_LENGTH:
            raise ValidationError("Ссылка слишком длинная.")
        if len(notes) > config.MAX_NOTES_LENGTH:
            raise ValidationError("Заметка слишком длинная.")
        if self._settings is None or not self._settings.category(category_id):
            raise ValidationError("Выбранная категория не существует.")

        url = self._normalize_url(url)
        if len(url) > config.MAX_URL_LENGTH:
            raise ValidationError("Ссылка слишком длинная.")
        return {
            "title": title,
            "username": username,
            "password": password,
            "url": url,
            "category_id": category_id,
            "notes": notes.strip(),
            "favorite": bool(favorite),
        }

    @staticmethod
    def _normalize_url(url: str) -> str:
        if not url:
            return ""
        if any(char.isspace() for char in url):
            raise ValidationError("Ссылка не должна содержать пробелы.")
        try:
            parsed = urlsplit(url)
        except ValueError as exc:
            raise ValidationError("Некорректная ссылка.") from exc
        if not parsed.scheme and "://" not in url and "." in url:
            url = "https://" + url
        return url

    # ------------------------------------------------------------------ categories
    def save_settings(self, settings: AppSettings) -> None:
        self._require_loaded()
        self._validate_settings(settings)
        snapshot = copy.deepcopy(settings)
        self._store_settings(snapshot)
        self._settings = snapshot

    @staticmethod
    def _validate_settings(settings: AppSettings) -> None:
        allowed_auto_lock = {value for value, _ in config.AUTO_LOCK_OPTIONS}
        allowed_clipboard = {value for value, _ in config.CLIPBOARD_OPTIONS}
        if settings.auto_lock_minutes not in allowed_auto_lock:
            raise ValidationError("Некорректное значение автоблокировки.")
        if settings.clipboard_clear_seconds not in allowed_clipboard:
            raise ValidationError("Некорректное значение автоочистки буфера.")
        if not settings.categories:
            raise ValidationError("Должна быть хотя бы одна категория.")
        if not any(category.id == "other" for category in settings.categories):
            raise ValidationError("Категория «Другое» должна существовать.")

    def _store_settings(
        self,
        settings: AppSettings,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        payload = json.dumps(settings.to_dict(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        nonce, ciphertext = encryption.encrypt_bytes(
            self._keys.key, payload, self._settings_aad()
        )
        self._db.set_settings_raw(
            nonce,
            ciphertext,
            format_timestamp(utc_now()),
            connection=connection,
        )

    def add_category(self, name: str) -> Category:
        name = self._validate_category_name(name)
        settings = copy.deepcopy(self._settings)
        if settings is None:
            raise VaultLockedError("Хранилище заблокировано.")
        if any(item.name.casefold() == name.casefold() for item in settings.categories):
            raise ValidationError("Категория с таким названием уже существует.")
        order = max((item.order for item in settings.categories), default=0) + 1
        category = Category(id=str(uuid.uuid4()), name=name, builtin=False, order=order)
        settings.categories.append(category)
        self.save_settings(settings)
        return self.settings.category(category.id) or category

    def rename_category(self, category_id: str, name: str) -> None:
        name = self._validate_category_name(name)
        settings = copy.deepcopy(self._settings)
        if settings is None:
            raise VaultLockedError("Хранилище заблокировано.")
        category = settings.category(category_id)
        if category is None:
            raise ValidationError("Категория не найдена.")
        if any(
            item.id != category_id and item.name.casefold() == name.casefold()
            for item in settings.categories
        ):
            raise ValidationError("Категория с таким названием уже существует.")
        category.name = name
        self.save_settings(settings)

    def delete_category(self, category_id: str) -> None:
        if category_id == "other":
            raise ValidationError("Категорию «Другое» удалить нельзя.")
        settings = copy.deepcopy(self._settings)
        if settings is None:
            raise VaultLockedError("Хранилище заблокировано.")
        if settings.category(category_id) is None:
            raise ValidationError("Категория не найдена.")

        updated_records: list[PasswordRecord] = []
        raw_records: list[RawRecord] = []
        for record in self._records.values():
            if record.category_id != category_id:
                continue
            updated = self._build_updated_record(record, category_id="other")
            updated_records.append(updated)
            raw_records.append(self._encrypt_record(updated))

        settings.categories = [item for item in settings.categories if item.id != category_id]
        self._validate_settings(settings)

        with self._db.transaction() as connection:
            for raw in raw_records:
                self._db.update_record_raw(raw, connection)
            self._store_settings(settings, connection)

        for updated in updated_records:
            self._records[updated.id] = updated
        self._settings = settings

    @staticmethod
    def _validate_category_name(name: str) -> str:
        name = " ".join((name or "").split())
        if not name:
            raise ValidationError("Укажите название категории.")
        if len(name) > config.MAX_CATEGORY_NAME_LENGTH:
            raise ValidationError(
                f"Название категории не должно превышать {config.MAX_CATEGORY_NAME_LENGTH} символов."
            )
        return name

    # ------------------------------------------------------------------ helpers
    def _require_loaded(self) -> None:
        if not self._keys.unlocked:
            raise VaultLockedError("Хранилище заблокировано.")
        if not self._loaded:
            raise VaultLockedError("Данные хранилища не загружены.")


def utc_timestamp_now() -> datetime:
    return datetime.now(timezone.utc)
