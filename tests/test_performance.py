from __future__ import annotations

import pytest

from app.services.password_service import PasswordService


@pytest.mark.slow
def test_large_vault_operations(vault) -> None:
    service = vault.service
    for index in range(500):
        service.create_record(
            title=f"Service {index}",
            username=f"user{index}",
            password="Benchmark-Secret!42",
            category_id="other",
        )

    assert len(service.list_records()) == 500
    assert len(service.list_records(search="user499")) == 1
    total, favorites, counts = service.stats()
    assert total == 500
    assert favorites == 0
    assert counts["other"] == 500

    reloaded = PasswordService(vault.db, vault.keys)
    reloaded.load()
    assert len(reloaded.list_records()) == 500
