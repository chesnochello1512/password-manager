"""Vault lifecycle: creation, unlocking, locking and master-password rotation."""

from __future__ import annotations

import base64
import json
import os
import uuid
from datetime import datetime, timezone

from app import config
from app.database.database import Database, RawRecord
from app.exceptions import (
    InvalidMasterPasswordError,
    StorageError,
    ValidationError,
    VaultCorruptedError,
    VaultExistsError,
    VaultLockedError,
    VaultNotFoundError,
)
from app.models import AppSettings, default_categories
from app.security import encryption
from app.security.encryption import KdfParams

VERIFIER_TEXT = b"PasswordManager vault verifier v1"


def _b64encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class KeyManager:
    """Owns the in-memory encryption key and the vault metadata."""

    def __init__(self, database: Database) -> None:
        self._db = database
        self._key: bytearray | None = None
        self._vault_id: str | None = None

    # ------------------------------------------------------------------ state
    @property
    def unlocked(self) -> bool:
        return self._key is not None

    @property
    def vault_id(self) -> str:
        if not self._vault_id:
            raise VaultLockedError("Хранилище заблокировано.")
        return self._vault_id

    @property
    def key(self) -> bytearray:
        if self._key is None:
            raise VaultLockedError("Хранилище заблокировано.")
        return self._key

    @property
    def key_version(self) -> int:
        self.key
        try:
            return max(1, int(self._db.get_meta("key_version") or "1"))
        except (ValueError, StorageError):
            return 1

    def lock(self) -> None:
        if self._key is not None:
            encryption.zeroize(self._key)
        self._key = None
        self._vault_id = None

    def close(self) -> None:
        self.lock()
        self._db.close()

    # ------------------------------------------------------------------ creation
    def create_vault(self, master_password: str) -> None:
        self._validate_master_password(master_password)
        self.lock()
        if self._db.exists():
            raise VaultExistsError("Хранилище уже существует.")

        target = self._db.path
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target.parent / f".{target.name}.new-{uuid.uuid4().hex}"
        temp_db = Database(temp_path)
        new_key: bytearray | None = None
        try:
            temp_db.connect()
            temp_db.ensure_schema()

            vault_id = str(uuid.uuid4())
            salt = encryption.random_bytes(config.SALT_SIZE)
            params = encryption.default_kdf_params()
            new_key = encryption.derive_key(master_password.encode("utf-8"), salt, params)

            verifier_nonce, verifier_ciphertext = encryption.encrypt_bytes(
                new_key,
                VERIFIER_TEXT,
                encryption.build_aad(vault_id, "verifier"),
            )
            settings = AppSettings(categories=default_categories())
            settings_nonce, settings_ciphertext = encryption.encrypt_bytes(
                new_key,
                json.dumps(settings.to_dict(), ensure_ascii=False).encode("utf-8"),
                encryption.build_aad(vault_id, "settings"),
            )

            meta = {
                "format_version": str(config.VAULT_FORMAT_VERSION),
                "schema_version": str(config.DB_SCHEMA_VERSION),
                "vault_id": vault_id,
                "created_at": _utc_iso(),
                "app_version": config.APP_VERSION,
                "key_version": "1",
                "kdf_salt": _b64encode(salt),
                "verifier_nonce": _b64encode(verifier_nonce),
                "verifier_ciphertext": _b64encode(verifier_ciphertext),
                **params.to_meta(),
            }
            with temp_db.transaction():
                temp_db.set_meta_many(meta)
                temp_db.set_settings_raw(settings_nonce, settings_ciphertext, _utc_iso())
            temp_db.close()

            info = Database.inspect_vault(temp_path)
            if not info.valid:
                raise VaultCorruptedError(f"Не удалось создать хранилище: {info.message}")
            os.replace(temp_path, target)
            self._db.connect()
            self._key = new_key
            self._vault_id = vault_id
            new_key = None
        except Exception:
            temp_db.close()
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            if new_key is not None:
                encryption.zeroize(new_key)
            raise

    # ------------------------------------------------------------------ unlock
    def unlock(self, master_password: str) -> None:
        if not master_password:
            raise InvalidMasterPasswordError("Введите мастер-пароль.")
        if len(master_password) > config.MAX_MASTER_PASSWORD_LENGTH:
            raise InvalidMasterPasswordError("Неверный мастер-пароль.")
        if self.unlocked:
            self.lock()
        if not self._db.exists():
            raise VaultNotFoundError("Файл хранилища не найден.")

        if not self._db.is_open:
            self._db.connect()
        meta, params, salt, verifier_nonce, verifier_ciphertext = self._read_crypto_meta()

        key = encryption.derive_key(master_password.encode("utf-8"), salt, params)
        try:
            verifier = encryption.decrypt_bytes(
                key,
                verifier_nonce,
                verifier_ciphertext,
                encryption.build_aad(meta["vault_id"], "verifier"),
            )
        except Exception:
            encryption.zeroize(key)
            raise InvalidMasterPasswordError("Неверный мастер-пароль.") from None

        if not encryption.constant_time_equals(verifier, VERIFIER_TEXT):
            encryption.zeroize(key)
            raise InvalidMasterPasswordError("Неверный мастер-пароль.")

        self._key = key
        self._vault_id = meta["vault_id"]

    def _read_crypto_meta(self) -> tuple[dict[str, str], KdfParams, bytes, bytes, bytes]:
        try:
            meta = self._db.load_meta()
        except StorageError as exc:
            raise VaultCorruptedError("Не удалось прочитать метаданные хранилища.") from exc

        if not meta or "vault_id" not in meta:
            raise VaultCorruptedError("Файл не является хранилищем Password Manager.")
        try:
            version = int(meta.get("format_version", "0"))
        except ValueError as exc:
            raise VaultCorruptedError("Некорректная версия формата хранилища.") from exc
        if version != config.VAULT_FORMAT_VERSION:
            raise VaultCorruptedError(
                f"Версия формата {version} не поддерживается этой версией приложения."
            )

        try:
            params = KdfParams.from_meta(meta)
            salt = _b64decode(meta["kdf_salt"])
            verifier_nonce = _b64decode(meta["verifier_nonce"])
            verifier_ciphertext = _b64decode(meta["verifier_ciphertext"])
        except (KeyError, ValueError, TypeError) as exc:
            raise VaultCorruptedError("Криптографические метаданные повреждены.") from exc
        if len(salt) < config.SALT_SIZE:
            raise VaultCorruptedError("Соль хранилища повреждена.")
        if len(verifier_nonce) != config.NONCE_SIZE:
            raise VaultCorruptedError("Проверочные данные хранилища повреждены.")
        if len(verifier_ciphertext) < config.AUTH_TAG_SIZE:
            raise VaultCorruptedError("Проверочные данные хранилища повреждены.")
        return meta, params, salt, verifier_nonce, verifier_ciphertext

    # ------------------------------------------------------------------ rotation
    def change_master_password(self, current_password: str, new_password: str) -> None:
        if not self.unlocked:
            raise VaultLockedError("Хранилище заблокировано.")
        if not current_password:
            raise ValidationError("Введите текущий мастер-пароль.")
        self._validate_master_password(new_password)
        if current_password == new_password:
            raise ValidationError("Новый мастер-пароль совпадает с текущим.")

        meta, params, salt, verifier_nonce, verifier_ciphertext = self._read_crypto_meta()
        current_key = encryption.derive_key(current_password.encode("utf-8"), salt, params)
        try:
            verifier = encryption.decrypt_bytes(
                current_key,
                verifier_nonce,
                verifier_ciphertext,
                encryption.build_aad(meta["vault_id"], "verifier"),
            )
            if not encryption.constant_time_equals(verifier, VERIFIER_TEXT):
                raise InvalidMasterPasswordError("Неверный текущий мастер-пароль.")
        except InvalidMasterPasswordError:
            raise
        except Exception:
            raise InvalidMasterPasswordError("Неверный текущий мастер-пароль.") from None
        finally:
            encryption.zeroize(current_key)

        vault_id = meta["vault_id"]
        new_salt = encryption.random_bytes(config.SALT_SIZE)
        new_params = encryption.default_kdf_params()
        new_key = encryption.derive_key(new_password.encode("utf-8"), new_salt, new_params)
        target = self._db.path

        temp_path = target.parent / f".{target.name}.rekey-{uuid.uuid4().hex}"
        temp_db = Database(temp_path)
        try:
            temp_db.connect()
            temp_db.ensure_schema()
            verifier_nonce_new, verifier_ciphertext_new = encryption.encrypt_bytes(
                new_key,
                VERIFIER_TEXT,
                encryption.build_aad(vault_id, "verifier"),
            )

            records: list[RawRecord] = []
            for raw in self._db.iter_records_raw():
                plaintext = encryption.decrypt_bytes(
                    self._key,
                    raw.nonce,
                    raw.ciphertext,
                    encryption.build_aad(vault_id, "record", raw.id, raw.format_version),
                )
                nonce, ciphertext = encryption.encrypt_bytes(
                    new_key,
                    plaintext,
                    encryption.build_aad(vault_id, "record", raw.id, raw.format_version),
                )
                records.append(
                    RawRecord(
                        id=raw.id,
                        nonce=nonce,
                        ciphertext=ciphertext,
                        key_version=raw.key_version + 1,
                        format_version=raw.format_version,
                        created_at=raw.created_at,
                        updated_at=raw.updated_at,
                    )
                )

            settings_raw = self._db.get_settings_raw()
            if settings_raw is None:
                raise VaultCorruptedError("В хранилище отсутствуют зашифрованные настройки.")
            settings_plaintext = encryption.decrypt_bytes(
                self._key,
                settings_raw.nonce,
                settings_raw.ciphertext,
                encryption.build_aad(vault_id, "settings"),
            )
            settings_nonce, settings_ciphertext = encryption.encrypt_bytes(
                new_key,
                settings_plaintext,
                encryption.build_aad(vault_id, "settings"),
            )

            try:
                next_key_version = max(1, int(meta.get("key_version", "1"))) + 1
            except ValueError:
                next_key_version = 2
            new_meta = {
                **meta,
                "key_version": str(next_key_version),
                "kdf_salt": _b64encode(new_salt),
                "verifier_nonce": _b64encode(verifier_nonce_new),
                "verifier_ciphertext": _b64encode(verifier_ciphertext_new),
                "app_version": config.APP_VERSION,
                **new_params.to_meta(),
            }
            with temp_db.transaction():
                temp_db.set_meta_many(new_meta)
                for record in records:
                    temp_db.insert_record_raw(record, temp_db.connection)
                temp_db.set_settings_raw(settings_nonce, settings_ciphertext, _utc_iso())
            temp_db.close()

            info = Database.inspect_vault(temp_path)
            if not info.valid:
                raise VaultCorruptedError(f"Проверка нового хранилища не пройдена: {info.message}")

            old_key = self._key
            self._db.close()
            os.replace(temp_path, target)
            self._key = new_key
            self._vault_id = vault_id
            new_key = None
            self._db.connect()
            if old_key is not None:
                encryption.zeroize(old_key)
        except Exception:
            temp_db.close()
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            if not self._db.is_open:
                try:
                    self._db.connect()
                except Exception:
                    pass
            raise
        finally:
            if new_key is not None:
                encryption.zeroize(new_key)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _validate_master_password(password: str) -> None:
        if not isinstance(password, str) or not password:
            raise ValidationError("Введите мастер-пароль.")
        if len(password) < config.MIN_MASTER_PASSWORD_LENGTH:
            raise ValidationError(
                f"Мастер-пароль должен содержать не менее {config.MIN_MASTER_PASSWORD_LENGTH} символов."
            )
        if len(password) > config.MAX_MASTER_PASSWORD_LENGTH:
            raise ValidationError("Мастер-пароль слишком длинный.")
