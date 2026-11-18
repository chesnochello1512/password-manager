from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app import config  # noqa: E402
from app.database.database import Database  # noqa: E402
from app.security.key_manager import KeyManager  # noqa: E402
from app.services.password_service import PasswordService  # noqa: E402

# Argon2id is intentionally expensive in production.  Tests use a cheaper
# profile to keep the suite fast; production defaults live in app/config.py.
config.ARGON2_MEMORY_KIB = 8 * 1024
config.ARGON2_TIME_COST = 1
config.ARGON2_PARALLELISM = 2

VAULT_PASSWORD = "Correct-Horse-Battery-42!"


@pytest.fixture()
def vault(tmp_path: Path) -> SimpleNamespace:
    path = tmp_path / "vault.db"
    database = Database(path)
    keys = KeyManager(database)
    keys.create_vault(VAULT_PASSWORD)
    service = PasswordService(database, keys)
    service.load()
    namespace = SimpleNamespace(
        path=path,
        db=database,
        keys=keys,
        service=service,
        password=VAULT_PASSWORD,
        tmp=tmp_path,
    )
    yield namespace
    keys.close()
