from __future__ import annotations

import os

import pytest

from app import config
from app.database.database import Database
from app.exceptions import (
    DecryptionError,
    InvalidMasterPasswordError,
    ValidationError,
    VaultCorruptedError,
)
from app.security import encryption
from app.security.encryption import KdfParams, derive_key
from app.security.key_manager import KeyManager


def test_production_crypto_constants_are_strong() -> None:
    assert KdfParams(memory_kib=64 * 1024, time_cost=3, parallelism=4).hash_len == 32
    assert config.ARGON2_HASH_LEN == 32
    assert config.NONCE_SIZE == 12
    assert config.SALT_SIZE == 16
    assert config.KEY_SIZE == 32


def test_derive_key_is_deterministic_and_salt_dependent() -> None:
    params = KdfParams(memory_kib=8192, time_cost=1, parallelism=2)
    salt_a = b"a" * 16
    salt_b = b"b" * 16
    first = derive_key(b"password", salt_a, params)
    second = derive_key(b"password", salt_a, params)
    other = derive_key(b"password", salt_b, params)
    assert bytes(first) == bytes(second)
    assert bytes(first) != bytes(other)
    assert len(first) == 32


def test_kdf_params_validation() -> None:
    with pytest.raises(ValidationError):
        KdfParams(memory_kib=1, time_cost=1, parallelism=1).validate()
    with pytest.raises(ValidationError):
        KdfParams(memory_kib=8192, time_cost=0, parallelism=1).validate()
    with pytest.raises(ValidationError):
        KdfParams(memory_kib=8192, time_cost=1, parallelism=0).validate()
    with pytest.raises(ValidationError):
        KdfParams(memory_kib=8192, time_cost=1, parallelism=1, hash_len=8).validate()


def test_roundtrip_and_unique_nonces() -> None:
    key = bytearray(os.urandom(32))
    aad = encryption.build_aad("vault-id", "record", "record-id")
    plaintext = "Секрет с юникодом 🔐".encode()
    first_nonce, first_ciphertext = encryption.encrypt_bytes(key, plaintext, aad)
    second_nonce, _ = encryption.encrypt_bytes(key, plaintext, aad)
    assert len(first_nonce) == 12
    assert first_nonce != second_nonce
    assert encryption.decrypt_bytes(key, first_nonce, first_ciphertext, aad) == plaintext
    assert len(first_ciphertext) == len(plaintext) + 16


def test_tampering_is_detected() -> None:
    key = bytearray(os.urandom(32))
    aad = b"pm:v1:vault:record:1"
    nonce, ciphertext = encryption.encrypt_bytes(key, b"top-secret", aad)

    tampered = bytearray(ciphertext)
    tampered[0] ^= 0x01
    with pytest.raises(DecryptionError):
        encryption.decrypt_bytes(key, nonce, bytes(tampered), aad)

    with pytest.raises(DecryptionError):
        encryption.decrypt_bytes(key, nonce, ciphertext, b"wrong-aad")

    with pytest.raises(DecryptionError):
        encryption.decrypt_bytes(key, nonce[:-1], ciphertext, aad)


def test_wrong_key_is_rejected() -> None:
    key = bytearray(os.urandom(32))
    other = bytearray(os.urandom(32))
    nonce, ciphertext = encryption.encrypt_bytes(key, b"hello", b"aad")
    with pytest.raises(DecryptionError):
        encryption.decrypt_bytes(other, nonce, ciphertext, b"aad")


def test_zeroize() -> None:
    buffer = bytearray(b"super-secret")
    encryption.zeroize(buffer)
    assert buffer == b"\x00" * len(b"super-secret")


def test_master_password_flow(vault) -> None:
    keys = vault.keys
    assert keys.unlocked

    with pytest.raises(InvalidMasterPasswordError):
        keys.unlock("wrong-password")

    keys.lock()
    assert not keys.unlocked
    with pytest.raises(InvalidMasterPasswordError):
        keys.unlock("wrong-password")

    keys.unlock(vault.password)
    assert keys.unlocked
    assert keys.vault_id
    assert len(keys.key) == 32


def test_verifier_tampering_is_rejected(tmp_path) -> None:
    path = tmp_path / "vault.db"
    database = Database(path)
    keys = KeyManager(database)
    keys.create_vault("very-secret-password")
    keys.lock()
    database.close()

    connection_database = Database(path)
    connection_database.connect()
    meta = connection_database.load_meta()
    encoded = bytearray(__import__("base64").b64decode(meta["verifier_ciphertext"]))
    encoded[0] ^= 0x01
    connection_database.set_meta(
        "verifier_ciphertext", __import__("base64").b64encode(bytes(encoded)).decode()
    )
    connection_database.close()

    reopened = Database(path)
    reopened.connect()
    with pytest.raises((InvalidMasterPasswordError, VaultCorruptedError)):
        KeyManager(reopened).unlock("very-secret-password")
    reopened.close()


def test_inspect_rejects_plain_other_database(tmp_path) -> None:
    path = tmp_path / "not-a-vault.db"
    import sqlite3

    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE sample(value TEXT)")
    connection.commit()
    connection.close()
    info = Database.inspect_vault(path)
    assert not info.valid
