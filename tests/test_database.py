from __future__ import annotations

import base64
from datetime import datetime

import pytest

from app.database.database import Database
from app.exceptions import InvalidMasterPasswordError, ValidationError, VaultCorruptedError
from app.security.key_manager import KeyManager
from app.services.password_service import PasswordService


def test_plain_values_never_reach_sqlite(vault) -> None:
    service = vault.service
    service.create_record(
        title="VeryUniqueServiceName",
        username="unique-login-42",
        password="Pa55w0rd-Unique-!!",
        url="https://unique-host.example",
        category_id="work",
        notes="very unique secret note",
    )
    vault.keys.lock()
    vault.db.close()

    raw = vault.path.read_bytes()
    for secret in (
        b"VeryUniqueServiceName",
        b"unique-login-42",
        b"Pa55w0rd-Unique-!!",
        b"unique-host.example",
        b"very unique secret note",
    ):
        assert secret not in raw

    vault.db.connect()
    vault.keys.unlock(vault.password)
    service_after = PasswordService(vault.db, vault.keys)
    service_after.load()
    record = service_after.list_records()[0]
    assert record.title == "VeryUniqueServiceName"
    assert record.password == "Pa55w0rd-Unique-!!"


def test_schema_versions_and_ciphertext_shape(vault) -> None:
    record = vault.service.create_record(title="Example", password="secret")
    rows = vault.db.list_records_raw()
    assert len(rows) == 1
    raw = rows[0]
    assert raw.id == record.id
    assert len(raw.nonce) == 12
    assert len(raw.ciphertext) >= 16
    assert raw.format_version == 1
    assert raw.key_version == 1
    assert datetime.fromisoformat(raw.created_at).tzinfo is not None
    meta = vault.db.load_meta()
    assert meta["format_version"] == "1"
    assert base64.b64decode(meta["kdf_salt"])
    assert Database.inspect_vault(vault.path).valid


def test_create_update_delete(vault) -> None:
    service = vault.service
    record = service.create_record(title="Mail", username="me", password="first", category_id="email")
    assert service.count_all() == 1
    assert service.count_by_category("email") == 1

    updated = service.update_record(record.id, title="Mail 2", password="second", favorite=True)
    assert updated.title == "Mail 2"
    assert updated.password == "second"
    assert updated.favorite is True
    assert updated.created_at == record.created_at
    assert updated.updated_at >= record.updated_at
    assert service.count_favorites() == 1

    service.delete_record(record.id)
    assert service.count_all() == 0
    with pytest.raises(ValidationError):
        service.get_record(record.id)


def test_validation_rules(vault) -> None:
    service = vault.service
    with pytest.raises(ValidationError):
        service.create_record(title="", password="x")
    with pytest.raises(ValidationError):
        service.create_record(title="No password", password="")
    with pytest.raises(ValidationError):
        service.create_record(title="Unknown category", password="x", category_id="unknown")
    with pytest.raises(ValidationError):
        service.create_record(title="Bad url", password="x", url="has space.com")
    record = service.create_record(title="Domain", password="x", url="example.com")
    assert record.url == "https://example.com"


def test_search_filter_and_favorites(vault) -> None:
    service = vault.service
    social = service.create_record(
        title="Instagram", username="alice", password="p1", url="https://instagram.com", category_id="social"
    )
    work = service.create_record(
        title="GitHub", username="bob", password="p2", url="https://github.com", category_id="work"
    )
    service.create_record(
        title="Bank", username="carol", password="p3", url="https://bank.example", category_id="banks"
    )
    service.toggle_favorite(work.id)

    assert {item.title for item in service.list_records(search="insta")} == {"Instagram"}
    assert {item.title for item in service.list_records(search="BOB")} == {"GitHub"}
    assert {item.title for item in service.list_records(search="bank.example")} == {"Bank"}
    assert {item.title for item in service.list_records(category_id="work")} == {"GitHub"}
    favorites = service.list_records(favorites_only=True)
    assert [item.title for item in favorites] == ["GitHub"]
    assert social.title not in {item.title for item in favorites}


def test_persistence_after_relock(vault) -> None:
    vault.service.create_record(title="Telegram", username="user", password="secret", category_id="social")
    vault.keys.lock()
    vault.db.close()

    database = Database(vault.path)
    database.connect()
    keys = KeyManager(database)
    with pytest.raises(InvalidMasterPasswordError):
        keys.unlock("wrong")
    keys.unlock(vault.password)
    service = PasswordService(database, keys)
    service.load()
    assert service.list_records()[0].title == "Telegram"
    keys.close()


def test_categories_are_editable(vault) -> None:
    service = vault.service
    record = service.create_record(title="Custom", password="secret", category_id="work")

    category = service.add_category("  Мои   сервисы ")
    assert category.name == "Мои сервисы"
    with pytest.raises(ValidationError):
        service.add_category("мои сервисы")
    service.update_record(record.id, category_id=category.id)
    service.rename_category(category.id, "Личное")
    assert service.settings.category_name(category.id) == "Личное"
    assert service.list_records(category_id=category.id)[0].id == record.id

    service.delete_category(category.id)
    assert service.settings.category(category.id) is None
    assert service.get_record(record.id).category_id == "other"
    with pytest.raises(ValidationError):
        service.delete_category("other")


def test_settings_roundtrip(vault) -> None:
    service = vault.service
    settings = service.settings
    settings.auto_lock_minutes = 15
    settings.clipboard_clear_seconds = 60
    service.save_settings(settings)

    vault.keys.lock()
    vault.db.close()
    database = Database(vault.path)
    database.connect()
    keys = KeyManager(database)
    keys.unlock(vault.password)
    service2 = PasswordService(database, keys)
    service2.load()
    assert service2.settings.auto_lock_minutes == 15
    assert service2.settings.clipboard_clear_seconds == 60
    service2.save_settings(service2.settings)
    keys.close()


def test_master_password_change_reencrypts_everything(vault) -> None:
    service = vault.service
    record = service.create_record(
        title="Rotate me", username="user", password="old-secret", notes="note", category_id="work"
    )
    old_rows = {row.id: row.ciphertext for row in vault.db.list_records_raw()}

    vault.keys.change_master_password(vault.password, "New-Master-Password-99!")
    new_rows = {row.id: row.ciphertext for row in vault.db.list_records_raw()}
    assert old_rows[record.id] != new_rows[record.id]

    vault.keys.lock()
    with pytest.raises(InvalidMasterPasswordError):
        vault.keys.unlock(vault.password)
    vault.keys.unlock("New-Master-Password-99!")

    service2 = PasswordService(vault.db, vault.keys)
    service2.load()
    loaded = service2.get_record(record.id)
    assert loaded.password == "old-secret"
    assert loaded.notes == "note"
    assert service2.settings.category("work") is not None
    assert Database.inspect_vault(vault.path).valid


def test_damaged_record_is_skipped(vault) -> None:
    service = vault.service
    good = service.create_record(title="Good", password="secret")
    damaged = service.create_record(title="Damaged", password="secret")
    row = next(item for item in vault.db.list_records_raw() if item.id == damaged.id)
    tampered = bytearray(row.ciphertext)
    tampered[0] ^= 0xFF
    vault.db.connection.execute(
        "UPDATE records SET ciphertext = ? WHERE id = ?",
        (bytes(tampered), damaged.id),
    )

    service2 = PasswordService(vault.db, vault.keys)
    service2.load()
    assert service2.corrupt_records == 1
    assert [item.id for item in service2.list_records()] == [good.id]
    assert service2.load_warnings


def test_inspect_detects_wrong_format(tmp_path) -> None:
    path = tmp_path / "broken.db"
    path.write_bytes(b"not a database at all")
    info = Database.inspect_vault(path)
    assert not info.valid
    with pytest.raises(VaultCorruptedError):
        Database.validate_or_raise(path)
