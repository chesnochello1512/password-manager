from __future__ import annotations

import sqlite3

import pytest

from app.database.database import Database
from app.exceptions import BackupError
from app.security.key_manager import KeyManager
from app.services.backup_service import BackupService
from app.services.password_service import PasswordService


def test_backup_is_encrypted_and_valid(vault) -> None:
    vault.service.create_record(
        title="BackupSecretTitle",
        username="backup-user",
        password="BackupSecretPassword!",
        notes="BackupSecretNote",
    )
    backup = vault.tmp / "vault-backup"
    created = BackupService(vault.db).create_backup(backup)
    assert created.exists()
    assert created.suffix == ".pmvault"

    info = BackupService.validate_backup(created)
    assert info.valid
    assert info.record_count == 1

    raw = created.read_bytes()
    assert b"BackupSecretTitle" not in raw
    assert b"BackupSecretPassword!" not in raw
    assert b"BackupSecretNote" not in raw


def test_restore_backup_to_new_location(vault) -> None:
    vault.service.create_record(title="Restored", password="secret", category_id="work")
    backup = BackupService(vault.db).create_backup(vault.tmp / "backup.pmvault")
    vault.keys.lock()
    vault.db.close()

    target = vault.tmp / "restored-vault.db"
    safety = BackupService.restore_backup(backup, target)
    assert safety is None
    assert target.exists()
    assert backup.exists()  # source backup must not be consumed

    database = Database(target)
    database.connect()
    keys = KeyManager(database)
    keys.unlock(vault.password)
    service = PasswordService(database, keys)
    service.load()
    assert service.list_records()[0].title == "Restored"
    assert service.settings.category("work") is not None
    keys.close()


def test_restore_creates_safety_copy(vault) -> None:
    vault.service.create_record(title="Before", password="secret")
    backup = BackupService(vault.db).create_backup(vault.tmp / "backup.pmvault")
    vault.service.create_record(title="After", password="secret")
    vault.keys.lock()
    vault.db.close()

    safety = BackupService.restore_backup(backup, vault.path)
    assert safety is not None and safety.exists()
    assert "bak-" in safety.name

    database = Database(vault.path)
    database.connect()
    keys = KeyManager(database)
    keys.unlock(vault.password)
    service = PasswordService(database, keys)
    service.load()
    assert [item.title for item in service.list_records()] == ["Before"]
    keys.close()


def test_corrupted_backup_is_rejected(vault, tmp_path) -> None:
    backup = BackupService(vault.db).create_backup(tmp_path / "backup.pmvault")
    damaged = tmp_path / "damaged.pmvault"
    data = backup.read_bytes()
    damaged.write_bytes(data[:200])

    info = BackupService.validate_backup(damaged)
    assert not info.valid
    vault.keys.lock()
    vault.db.close()
    with pytest.raises(BackupError):
        BackupService.restore_backup(damaged, vault.path)
    assert vault.path.exists()


def test_backup_of_missing_file(vault, tmp_path) -> None:
    with pytest.raises(BackupError):
        BackupService.validate_backup(tmp_path / "missing.pmvault")


def test_restore_keeps_backup_password(vault, tmp_path) -> None:
    vault.keys.change_master_password(vault.password, "Backup-Master-Password-77!")
    backup = BackupService(vault.db).create_backup(tmp_path / "backup.pmvault")
    vault.keys.lock()
    vault.db.close()

    target = tmp_path / "restored.db"
    BackupService.restore_backup(backup, target)
    database = Database(target)
    database.connect()
    keys = KeyManager(database)
    with pytest.raises(Exception):
        keys.unlock(vault.password)
    keys.unlock("Backup-Master-Password-77!")
    assert keys.unlocked
    keys.close()


def test_cryptographic_verification_detects_tampering(vault, tmp_path) -> None:
    vault.service.create_record(title="Tamper", password="Tamper-Secret!42")
    backup = BackupService(vault.db).create_backup(tmp_path / "backup.pmvault")
    assert BackupService.verify_cryptographic(backup, vault.keys) == 1

    connection = sqlite3.connect(str(backup))
    try:
        row = connection.execute("SELECT id, ciphertext FROM records").fetchone()
        changed = bytearray(row[1])
        changed[0] ^= 0xFF
        connection.execute(
            "UPDATE records SET ciphertext = ? WHERE id = ?", (bytes(changed), row[0])
        )
        connection.commit()
    finally:
        connection.close()

    # Structural validation still passes: lengths are unchanged.
    assert Database.inspect_vault(backup).valid
    with pytest.raises(BackupError):
        BackupService.verify_cryptographic(backup, vault.keys)

