from __future__ import annotations

import pytest

from app.database.database import Database
from app.exceptions import StorageError, ValidationError, VaultLockedError
from app.services.generator import GeneratorOptions, generate_password
from app.services.password_service import PasswordService


def test_favorites_are_sorted_first(vault) -> None:
    service = vault.service
    service.create_record(title="Zulu", password="x")
    service.create_record(title="Alpha", password="x")
    service.create_record(title="Mike", password="x", favorite=True)

    titles = [item.title for item in service.list_records()]
    assert titles[0] == "Mike"
    assert titles[1:] == ["Alpha", "Zulu"]


def test_partial_search_across_fields(vault) -> None:
    service = vault.service
    service.create_record(title="Steam", username="player-one", password="x", url="store.steampowered.com")
    service.create_record(title="Epic", username="epic-user", password="x", url="epicgames.com")

    assert [item.title for item in service.list_records(search="player")] == ["Steam"]
    assert [item.title for item in service.list_records(search="steampowered")] == ["Steam"]
    assert [item.title for item in service.list_records(search="EPIC")] == ["Epic"]


def test_update_preserves_unspecified_fields(vault) -> None:
    service = vault.service
    record = service.create_record(
        title="Service", username="login", password="secret", url="https://service.example",
        category_id="work", notes="keep me", favorite=True,
    )
    updated = service.update_record(record.id, password=generate_password(GeneratorOptions(length=24)))
    assert updated.username == "login"
    assert updated.notes == "keep me"
    assert updated.category_id == "work"
    assert updated.favorite is True
    assert updated.url == "https://service.example"


def test_invalid_updates_are_rejected(vault) -> None:
    service = vault.service
    record = service.create_record(title="Service", password="secret")
    with pytest.raises(ValidationError):
        service.update_record(record.id, title="   ")
    with pytest.raises(ValidationError):
        service.update_record(record.id, category_id="missing")
    with pytest.raises(ValidationError):
        service.update_record(record.id, password="")


def test_duplicate_category_names_rejected_case_insensitive(vault) -> None:
    service = vault.service
    service.add_category("Streaming")
    with pytest.raises(ValidationError):
        service.add_category("STREAMING")
    with pytest.raises(ValidationError):
        service.add_category("   ")


def test_added_records_are_immediately_searchable(vault) -> None:
    service = vault.service
    for index in range(5):
        service.create_record(title=f"Site {index}", username=f"user{index}", password="x")
    assert len(service.list_records(search="site")) == 5
    assert len(service.list_records(search="user3")) == 1
    assert service.count_all() == 5


def test_service_requires_unlocked_state(vault) -> None:
    vault.keys.lock()
    with pytest.raises(VaultLockedError):
        vault.service.list_records()
    with pytest.raises(VaultLockedError):
        PasswordService(vault.db, vault.keys).load()


def test_stats_counts_in_one_call(vault) -> None:
    service = vault.service
    service.create_record(title="One", password="x", category_id="work", favorite=True)
    service.create_record(title="Two", password="x", category_id="work")
    service.create_record(title="Three", password="x", category_id="social")

    total, favorites, counts = service.stats()
    assert total == 3
    assert favorites == 1
    assert counts["work"] == 2
    assert counts["social"] == 1


def test_delete_category_is_atomic_on_midway_failure(vault, monkeypatch) -> None:
    service = vault.service
    for index in range(4):
        service.create_record(title=f"Work {index}", password="x", category_id="work")

    original = Database.update_record_raw
    calls = {"count": 0}

    def flaky(self, record, connection=None):
        calls["count"] += 1
        if calls["count"] == 2:
            raise StorageError("simulated failure")
        return original(self, record, connection)

    monkeypatch.setattr(Database, "update_record_raw", flaky)

    with pytest.raises(StorageError):
        service.delete_category("work")

    assert service.settings.category("work") is not None
    assert all(record.category_id == "work" for record in service.list_records())

    service.load()
    assert service.settings.category("work") is not None
    assert all(record.category_id == "work" for record in service.list_records())


def test_delete_category_rolls_back_when_settings_write_fails(vault, monkeypatch) -> None:
    service = vault.service
    service.create_record(title="Work", password="x", category_id="work")

    original = Database.set_settings_raw

    def failing(self, nonce, ciphertext, updated_at, connection=None):
        raise StorageError("settings failure")

    monkeypatch.setattr(Database, "set_settings_raw", failing)

    with pytest.raises(StorageError):
        service.delete_category("work")

    assert service.settings.category("work") is not None
    assert service.list_records()[0].category_id == "work"

    service.load()
    assert service.settings.category("work") is not None
    assert service.list_records()[0].category_id == "work"
    assert original is not None


def test_add_category_does_not_mutate_memory_before_commit(vault, monkeypatch) -> None:
    service = vault.service
    original_names = [category.name for category in service.settings.categories]

    def failing(self, nonce, ciphertext, updated_at, connection=None):
        raise StorageError("settings failure")

    monkeypatch.setattr(Database, "set_settings_raw", failing)

    with pytest.raises(StorageError):
        service.add_category("Should Not Exist")

    assert [category.name for category in service.settings.categories] == original_names
    service.load()
    assert [category.name for category in service.settings.categories] == original_names


def test_auto_lock_change_rolls_back_on_write_failure(vault, monkeypatch) -> None:
    service = vault.service
    before = service.settings.auto_lock_minutes
    candidate = service.settings
    candidate.auto_lock_minutes = 10 if before != 10 else 15

    def failing(self, nonce, ciphertext, updated_at, connection=None):
        raise StorageError("settings failure")

    monkeypatch.setattr(Database, "set_settings_raw", failing)

    with pytest.raises(StorageError):
        service.save_settings(candidate)

    assert service.settings.auto_lock_minutes == before
    service.load()
    assert service.settings.auto_lock_minutes == before
