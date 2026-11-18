from __future__ import annotations

import pytest

from app.exceptions import ValidationError
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
    with pytest.raises(Exception):
        vault.service.list_records()
    with pytest.raises(Exception):
        PasswordService(vault.db, vault.keys).load()
