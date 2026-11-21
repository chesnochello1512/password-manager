"""SQLite persistence for the encrypted vault.

Only record identifiers, timestamps, format versions and opaque ciphertext are
stored in clear columns.  All user content lives inside AES-GCM ciphertext.
"""

from __future__ import annotations

import base64
import os
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app import config
from app.exceptions import StorageError, VaultCorruptedError
from app.security.encryption import KdfParams

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS records (
    id             TEXT PRIMARY KEY,
    nonce          BLOB NOT NULL,
    ciphertext     BLOB NOT NULL,
    key_version    INTEGER NOT NULL DEFAULT 1,
    format_version INTEGER NOT NULL,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vault_settings (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    nonce      BLOB NOT NULL,
    ciphertext BLOB NOT NULL,
    updated_at TEXT NOT NULL
);
"""

REQUIRED_META_KEYS = (
    "format_version",
    "schema_version",
    "vault_id",
    "kdf_algorithm",
    "kdf_memory_kib",
    "kdf_time_cost",
    "kdf_parallelism",
    "kdf_hash_len",
    "kdf_salt",
    "verifier_nonce",
    "verifier_ciphertext",
)


@dataclass(slots=True)
class VaultFileInfo:
    path: Path
    valid: bool
    message: str
    record_count: int = 0
    format_version: int = 0
    schema_version: int = 0
    key_version: int = 0
    app_version: str = ""
    created_at: str = ""
    vault_id: str = ""


@dataclass(slots=True)
class RawRecord:
    id: str
    nonce: bytes
    ciphertext: bytes
    key_version: int
    format_version: int
    created_at: str
    updated_at: str


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------ lifecycle
    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise StorageError("База данных не открыта.")
        return self._conn

    @property
    def is_open(self) -> bool:
        return self._conn is not None

    def exists(self) -> bool:
        try:
            return self.path.is_file() and self.path.stat().st_size > 0
        except OSError:
            return False

    def connect(self) -> None:
        if self._conn is not None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                str(self.path),
                timeout=15,
                isolation_level=None,
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
            cursor = self._conn.cursor()
            cursor.execute("PRAGMA journal_mode=DELETE")
            cursor.execute("PRAGMA synchronous=FULL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA secure_delete=ON")
            cursor.execute("PRAGMA busy_timeout=15000")
            if os.name != "nt":
                try:
                    self.path.chmod(0o600)
                except OSError:
                    pass
        except sqlite3.Error as exc:
            self._conn = None
            raise StorageError("Не удалось открыть файл хранилища.") from exc

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
            self._conn = None

    def reopen(self) -> None:
        self.close()
        self.connect()

    def ensure_schema(self) -> None:
        try:
            self.connection.executescript(_SCHEMA)
        except sqlite3.Error as exc:
            raise StorageError("Не удалось подготовить схему базы данных.") from exc

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connection
        try:
            connection.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as exc:
            raise StorageError("Не удалось начать операцию с базой данных.") from exc
        try:
            yield connection
        except Exception:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        else:
            try:
                connection.execute("COMMIT")
            except sqlite3.Error as exc:
                try:
                    connection.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise StorageError("Не удалось зафиксировать изменения в базе данных.") from exc

    # ------------------------------------------------------------------ meta
    def get_meta(self, key: str) -> str | None:
        try:
            row = self.connection.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        except sqlite3.Error as exc:
            raise StorageError("Не удалось прочитать метаданные хранилища.") from exc
        return str(row["value"]) if row else None

    def load_meta(self) -> dict[str, str]:
        try:
            rows = self.connection.execute("SELECT key, value FROM meta").fetchall()
        except sqlite3.Error as exc:
            raise StorageError("Не удалось прочитать метаданные хранилища.") from exc
        return {str(row["key"]): str(row["value"]) for row in rows}

    def set_meta(self, key: str, value: str) -> None:
        self.set_meta_many({key: value})

    def set_meta_many(self, values: dict[str, str], connection: sqlite3.Connection | None = None) -> None:
        target = connection or self.connection
        try:
            target.executemany(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                [(str(key), str(value)) for key, value in values.items()],
            )
        except sqlite3.Error as exc:
            raise StorageError("Не удалось сохранить метаданные хранилища.") from exc

    # ------------------------------------------------------------------ records
    def list_records_raw(self) -> list[RawRecord]:
        try:
            rows = self.connection.execute(
                "SELECT id, nonce, ciphertext, key_version, format_version, created_at, updated_at "
                "FROM records"
            ).fetchall()
        except sqlite3.Error as exc:
            raise StorageError("Не удалось прочитать записи.") from exc
        return [self._to_raw_record(row) for row in rows]

    def iter_records_raw(self) -> Iterator[RawRecord]:
        try:
            cursor = self.connection.execute(
                "SELECT id, nonce, ciphertext, key_version, format_version, created_at, updated_at "
                "FROM records"
            )
            for row in cursor:
                yield self._to_raw_record(row)
        except sqlite3.Error as exc:
            raise StorageError("Не удалось прочитать записи.") from exc

    @staticmethod
    def _to_raw_record(row: sqlite3.Row) -> RawRecord:
        return RawRecord(
            id=str(row["id"]),
            nonce=bytes(row["nonce"]),
            ciphertext=bytes(row["ciphertext"]),
            key_version=int(row["key_version"]),
            format_version=int(row["format_version"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def insert_record_raw(
        self,
        record: RawRecord,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        target = connection or self.connection
        try:
            target.execute(
                "INSERT INTO records(id, nonce, ciphertext, key_version, format_version, created_at, updated_at) "
                "VALUES(?, ?, ?, ?, ?, ?, ?)",
                (
                    record.id,
                    sqlite3.Binary(record.nonce),
                    sqlite3.Binary(record.ciphertext),
                    record.key_version,
                    record.format_version,
                    record.created_at,
                    record.updated_at,
                ),
            )
        except sqlite3.Error as exc:
            raise StorageError("Не удалось сохранить запись.") from exc

    def update_record_raw(self, record: RawRecord, connection: sqlite3.Connection | None = None) -> None:
        target = connection or self.connection
        try:
            cursor = target.execute(
                "UPDATE records SET nonce = ?, ciphertext = ?, key_version = ?, format_version = ?, "
                "updated_at = ? WHERE id = ?",
                (
                    sqlite3.Binary(record.nonce),
                    sqlite3.Binary(record.ciphertext),
                    record.key_version,
                    record.format_version,
                    record.updated_at,
                    record.id,
                ),
            )
        except sqlite3.Error as exc:
            raise StorageError("Не удалось обновить запись.") from exc
        if cursor.rowcount == 0:
            raise StorageError("Запись не найдена.")

    def delete_record(
        self,
        record_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        target = connection or self.connection
        try:
            target.execute("DELETE FROM records WHERE id = ?", (record_id,))
        except sqlite3.Error as exc:
            raise StorageError("Не удалось удалить запись.") from exc

    def record_count(self) -> int:
        try:
            row = self.connection.execute("SELECT COUNT(*) AS total FROM records").fetchone()
        except sqlite3.Error as exc:
            raise StorageError("Не удалось подсчитать записи.") from exc
        return int(row["total"]) if row else 0

    # ------------------------------------------------------------------ settings
    def get_settings_raw(self) -> RawRecord | None:
        try:
            row = self.connection.execute(
                "SELECT nonce, ciphertext, updated_at FROM vault_settings WHERE id = 1"
            ).fetchone()
        except sqlite3.Error as exc:
            raise StorageError("Не удалось прочитать настройки хранилища.") from exc
        if not row:
            return None
        return RawRecord(
            id="settings",
            nonce=bytes(row["nonce"]),
            ciphertext=bytes(row["ciphertext"]),
            key_version=1,
            format_version=config.VAULT_FORMAT_VERSION,
            created_at=str(row["updated_at"]),
            updated_at=str(row["updated_at"]),
        )

    def set_settings_raw(
        self,
        nonce: bytes,
        ciphertext: bytes,
        updated_at: str,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        target = connection or self.connection
        try:
            target.execute(
                "INSERT INTO vault_settings(id, nonce, ciphertext, updated_at) VALUES(1, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET nonce = excluded.nonce, "
                "ciphertext = excluded.ciphertext, updated_at = excluded.updated_at",
                (sqlite3.Binary(nonce), sqlite3.Binary(ciphertext), updated_at),
            )
        except sqlite3.Error as exc:
            raise StorageError("Не удалось сохранить настройки хранилища.") from exc

    # ------------------------------------------------------------------ maintenance
    def integrity_check(self) -> tuple[bool, str]:
        try:
            rows = self.connection.execute("PRAGMA integrity_check").fetchall()
        except sqlite3.Error as exc:
            return False, f"Ошибка чтения базы данных: {exc}"
        messages = [str(row[0]) for row in rows]
        if messages == ["ok"]:
            return True, "ok"
        return False, "; ".join(messages) or "неизвестная ошибка"

    def backup_to(self, destination: Path) -> None:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        target: sqlite3.Connection | None = None
        try:
            target = sqlite3.connect(str(destination))
            self.connection.backup(target)
            target.commit()
        except sqlite3.Error as exc:
            raise StorageError("Не удалось создать снимок базы данных.") from exc
        finally:
            if target is not None:
                target.close()

    # ------------------------------------------------------------------ inspection
    @staticmethod
    def inspect_vault(path: Path | str) -> VaultFileInfo:
        path = Path(path)
        info = VaultFileInfo(path=path, valid=False, message="")
        try:
            if not path.is_file() or path.stat().st_size == 0:
                info.message = "Файл не существует или пуст."
                return info
        except OSError as exc:
            info.message = f"Не удалось прочитать файл: {exc}"
            return info

        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(str(path), timeout=10, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            check_rows = connection.execute("PRAGMA integrity_check").fetchall()
            check_messages = [str(row[0]) for row in check_rows]
            if check_messages != ["ok"]:
                info.message = "База данных повреждена: " + ("; ".join(check_messages) or "неизвестно")
                return info

            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            required_tables = {"meta", "records", "vault_settings"}
            if not required_tables.issubset(tables):
                info.message = "Файл не является хранилищем Password Manager."
                return info

            meta = {
                str(row["key"]): str(row["value"])
                for row in connection.execute("SELECT key, value FROM meta").fetchall()
            }
            missing = [key for key in REQUIRED_META_KEYS if key not in meta]
            if missing:
                info.message = "В хранилище отсутствуют обязательные метаданные."
                return info

            try:
                info.format_version = int(meta["format_version"])
                info.schema_version = int(meta["schema_version"])
                info.key_version = max(1, int(meta.get("key_version", "1")))
                KdfParams.from_meta(meta)
                salt = base64.b64decode(meta["kdf_salt"], validate=True)
                verifier_nonce = base64.b64decode(meta["verifier_nonce"], validate=True)
                verifier_ciphertext = base64.b64decode(meta["verifier_ciphertext"], validate=True)
            except Exception:
                info.message = "Метаданные хранилища повреждены."
                return info

            if info.format_version != config.VAULT_FORMAT_VERSION:
                info.message = f"Неподдерживаемая версия формата: {info.format_version}."
                return info
            if len(salt) < config.SALT_SIZE or len(verifier_nonce) != config.NONCE_SIZE:
                info.message = "Криптографические метаданные повреждены."
                return info
            if len(verifier_ciphertext) < config.AUTH_TAG_SIZE:
                info.message = "Проверочный блок хранилища повреждён."
                return info
            if not meta.get("vault_id"):
                info.message = "В хранилище отсутствует идентификатор."
                return info

            row = connection.execute("SELECT COUNT(*) AS total FROM records").fetchone()
            info.record_count = int(row["total"]) if row else 0
            info.vault_id = meta["vault_id"]
            info.app_version = meta.get("app_version", "")
            info.created_at = meta.get("created_at", "")

            broken = connection.execute(
                "SELECT COUNT(*) AS total FROM records "
                "WHERE length(nonce) != ? OR length(ciphertext) < ?",
                (config.NONCE_SIZE, config.AUTH_TAG_SIZE),
            ).fetchone()
            if broken and int(broken["total"]) > 0:
                info.message = "Часть записей имеет некорректный формат шифротекста."
                return info

            settings_row = connection.execute(
                "SELECT length(nonce) AS nonce_len, length(ciphertext) AS ct_len FROM vault_settings WHERE id = 1"
            ).fetchone()
            if settings_row is None:
                info.message = "В хранилище отсутствуют зашифрованные настройки."
                return info
            if (
                int(settings_row["nonce_len"] or 0) != config.NONCE_SIZE
                or int(settings_row["ct_len"] or 0) < config.AUTH_TAG_SIZE
            ):
                info.message = "Настройки хранилища повреждены."
                return info

            info.valid = True
            info.message = "Хранилище корректно."
            return info
        except sqlite3.DatabaseError as exc:
            info.message = f"Файл не является корректной базой данных: {exc}"
            return info
        except OSError as exc:
            info.message = f"Не удалось прочитать файл: {exc}"
            return info
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def validate_or_raise(path: Path | str) -> VaultFileInfo:
        info = Database.inspect_vault(path)
        if not info.valid:
            raise VaultCorruptedError(info.message)
        return info


def timestamps_for_row(created_at: datetime, updated_at: datetime) -> Sequence[str]:
    """Small helper used by tests and services for consistent SQLite timestamps."""

    return (
        created_at.isoformat(timespec="seconds"),
        updated_at.isoformat(timespec="seconds"),
    )
