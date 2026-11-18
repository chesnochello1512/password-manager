"""Encrypted backup creation, verification and restoration."""

from __future__ import annotations

import base64
import binascii
import json
import os
import shutil
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from app import config
from app.database.database import Database, VaultFileInfo
from app.exceptions import BackupError, DecryptionError
from app.security import encryption
from app.security.key_manager import VERIFIER_TEXT, KeyManager


def _decode(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


class BackupService:
    def __init__(self, database: Database) -> None:
        self._db = database

    @staticmethod
    def suggested_filename() -> str:
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        return f"PasswordManager-backup-{stamp}{config.BACKUP_SUFFIX}"

    def create_backup(self, destination: Path | str) -> Path:
        destination = Path(destination).expanduser()
        if destination.suffix.lower() != config.BACKUP_SUFFIX:
            destination = destination.with_name(destination.name + config.BACKUP_SUFFIX)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.resolve() == self._db.path.resolve():
            raise BackupError("Нельзя сохранить резервную копию поверх файла хранилища.")

        temp_path = destination.parent / f".{destination.name}.tmp-{uuid.uuid4().hex}"
        try:
            self._db.backup_to(temp_path)
            info = Database.inspect_vault(temp_path)
            if not info.valid:
                raise BackupError(f"Резервная копия не прошла проверку: {info.message}")
            os.replace(temp_path, destination)
            if os.name != "nt":
                try:
                    destination.chmod(0o600)
                except OSError:
                    pass
        except Exception:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        return destination

    @staticmethod
    def validate_backup(path: Path | str) -> VaultFileInfo:
        path = Path(path).expanduser()
        if not path.exists():
            raise BackupError("Файл резервной копии не найден.")
        if not path.is_file():
            raise BackupError("Указанный путь не является файлом.")
        return Database.inspect_vault(path)

    @staticmethod
    def verify_cryptographic(path: Path | str, key_manager: KeyManager) -> int:
        """Verify every ciphertext block using the currently unlocked key.

        Returns the number of verified records.  Only possible when the backup
        belongs to the currently opened vault; otherwise the password of the
        backup would be required.
        """

        path = Path(path).expanduser()
        info = BackupService.validate_backup(path)
        if not info.valid:
            raise BackupError(info.message)
        if not key_manager.unlocked:
            raise BackupError("Хранилище заблокировано, проверка шифротекста недоступна.")
        vault_id = info.vault_id
        if vault_id != key_manager.vault_id:
            raise BackupError("Копия относится к другому хранилищу.")
        if info.key_version != key_manager.key_version:
            raise BackupError(
                "Копия создана с другим ключом (до смены мастер-пароля); "
                "проверка текущим ключом невозможна."
            )

        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(str(path), timeout=10, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            meta = {
                str(row["key"]): str(row["value"])
                for row in connection.execute("SELECT key, value FROM meta").fetchall()
            }
            verifier_nonce = _decode(meta["verifier_nonce"])
            verifier_ciphertext = _decode(meta["verifier_ciphertext"])
            verifier = encryption.decrypt_bytes(
                key_manager.key,
                verifier_nonce,
                verifier_ciphertext,
                encryption.build_aad(vault_id, "verifier"),
            )
            if not encryption.constant_time_equals(verifier, VERIFIER_TEXT):
                raise BackupError("Проверочный блок копии не совпадает.")

            settings_row = connection.execute(
                "SELECT nonce, ciphertext FROM vault_settings WHERE id = 1"
            ).fetchone()
            if settings_row is None:
                raise BackupError("В копии отсутствуют настройки.")
            settings_plaintext = encryption.decrypt_bytes(
                key_manager.key,
                bytes(settings_row["nonce"]),
                bytes(settings_row["ciphertext"]),
                encryption.build_aad(vault_id, "settings"),
            )
            json.loads(settings_plaintext.decode("utf-8"))

            verified = 0
            cursor = connection.execute(
                "SELECT id, nonce, ciphertext, format_version FROM records"
            )
            for row in cursor:
                encryption.decrypt_bytes(
                    key_manager.key,
                    bytes(row["nonce"]),
                    bytes(row["ciphertext"]),
                    encryption.build_aad(
                        vault_id,
                        "record",
                        str(row["id"]),
                        int(row["format_version"]),
                    ),
                )
                verified += 1
            return verified
        except (sqlite3.Error, KeyError, ValueError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error) as exc:
            raise BackupError("Не удалось прочитать зашифрованные данные копии.") from exc
        except DecryptionError as exc:
            raise BackupError("Шифротекст резервной копии повреждён или изменён.") from exc
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def restore_backup(
        backup_path: Path | str,
        vault_path: Path | str,
        safety_copy: bool = True,
    ) -> Path | None:
        """Replace the vault with a verified backup.

        The source backup is copied, never moved.  The caller must close all
        connections to the current vault before invoking this method.
        """

        backup_path = Path(backup_path).expanduser()
        vault_path = Path(vault_path).expanduser()
        info = BackupService.validate_backup(backup_path)
        if not info.valid:
            raise BackupError(f"Резервная копия повреждена: {info.message}")
        if backup_path.resolve() == vault_path.resolve():
            raise BackupError("Выбранный файл совпадает с текущим хранилищем.")

        vault_path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safety_path: Path | None = None
        if vault_path.exists():
            if safety_copy:
                safety_path = vault_path.with_name(f"{vault_path.name}.bak-{stamp}")
                shutil.copy2(vault_path, safety_path)
            else:
                vault_path.replace(vault_path.with_name(f"{vault_path.name}.bak-{stamp}"))

        temp_path = vault_path.parent / f".{vault_path.name}.restore-{uuid.uuid4().hex}"
        try:
            shutil.copy2(backup_path, temp_path)
            copy_info = Database.inspect_vault(temp_path)
            if not copy_info.valid:
                raise BackupError(f"Копия резервной копии повреждена: {copy_info.message}")
            os.replace(temp_path, vault_path)
        except Exception:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        return safety_path
