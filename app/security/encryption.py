"""Cryptographic primitives: Argon2id key derivation and AES-256-GCM.

The module contains no application state.  Keys are handled as ``bytearray``
so they can be wiped when the vault is locked.
"""

from __future__ import annotations

import ctypes
import hmac
import os
from collections.abc import Mapping
from dataclasses import dataclass

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app import config
from app.exceptions import DecryptionError, ValidationError


@dataclass(frozen=True, slots=True)
class KdfParams:
    memory_kib: int
    time_cost: int
    parallelism: int
    hash_len: int = config.ARGON2_HASH_LEN

    def validate(self) -> None:
        if not 8 * 1024 <= self.memory_kib <= 256 * 1024:
            raise ValidationError("Некорректный параметр памяти Argon2id.")
        if not 1 <= self.time_cost <= 10:
            raise ValidationError("Некорректный параметр времени Argon2id.")
        if not 1 <= self.parallelism <= 8:
            raise ValidationError("Некорректный параметр параллельности Argon2id.")
        if not 16 <= self.hash_len <= 64:
            raise ValidationError("Некорректная длина ключа.")

    def to_meta(self) -> dict[str, str]:
        return {
            "kdf_algorithm": "argon2id",
            "kdf_memory_kib": str(self.memory_kib),
            "kdf_time_cost": str(self.time_cost),
            "kdf_parallelism": str(self.parallelism),
            "kdf_hash_len": str(self.hash_len),
        }

    @classmethod
    def from_meta(cls, meta: Mapping[str, str]) -> KdfParams:
        if meta.get("kdf_algorithm") != "argon2id":
            raise ValidationError("Неподдерживаемый алгоритм получения ключа.")
        try:
            params = cls(
                memory_kib=int(meta["kdf_memory_kib"]),
                time_cost=int(meta["kdf_time_cost"]),
                parallelism=int(meta["kdf_parallelism"]),
                hash_len=int(meta.get("kdf_hash_len", config.ARGON2_HASH_LEN)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError("Повреждены параметры Argon2id в хранилище.") from exc
        params.validate()
        return params


def default_kdf_params() -> KdfParams:
    return KdfParams(
        memory_kib=config.ARGON2_MEMORY_KIB,
        time_cost=config.ARGON2_TIME_COST,
        parallelism=config.ARGON2_PARALLELISM,
        hash_len=config.ARGON2_HASH_LEN,
    )


def random_bytes(length: int) -> bytes:
    return os.urandom(length)


def derive_key(password: bytes, salt: bytes, params: KdfParams) -> bytearray:
    """Derive a 256-bit key from the master password using Argon2id."""

    if not isinstance(password, bytes | bytearray):
        raise TypeError("Master password must be bytes.")
    if len(salt) < 8:
        raise ValidationError("Соль ключа слишком короткая.")
    params.validate()
    secret = bytes(password)
    raw = hash_secret_raw(
        secret=secret,
        salt=salt,
        time_cost=params.time_cost,
        memory_cost=params.memory_kib,
        parallelism=params.parallelism,
        hash_len=params.hash_len,
        type=Type.ID,
    )
    key = bytearray(raw)
    # Best-effort wipe of intermediate immutable buffers.
    del raw
    del secret
    return key


def encrypt_bytes(key: bytes | bytearray, plaintext: bytes, aad: bytes = b"") -> tuple[bytes, bytes]:
    """Encrypt with a fresh random 96-bit nonce; returns ``(nonce, ciphertext+tag)``."""

    if len(key) != config.KEY_SIZE:
        raise ValueError("AES-256 requires a 32-byte key.")
    nonce = random_bytes(config.NONCE_SIZE)
    ciphertext = AESGCM(bytes(key)).encrypt(nonce, plaintext, aad)
    return nonce, ciphertext


def decrypt_bytes(
    key: bytes | bytearray,
    nonce: bytes,
    ciphertext: bytes,
    aad: bytes = b"",
) -> bytes:
    if len(key) != config.KEY_SIZE:
        raise ValueError("AES-256 requires a 32-byte key.")
    if len(nonce) != config.NONCE_SIZE:
        raise DecryptionError("Повреждён nonce зашифрованных данных.")
    if len(ciphertext) < config.AUTH_TAG_SIZE:
        raise DecryptionError("Повреждены зашифрованные данные.")
    try:
        return AESGCM(bytes(key)).decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise DecryptionError("Данные повреждены или ключ неверен.") from exc
    except (ValueError, TypeError) as exc:
        raise DecryptionError("Не удалось расшифровать данные.") from exc


def build_aad(vault_id: str, purpose: str, identifier: str = "", version: int = config.VAULT_FORMAT_VERSION) -> bytes:
    """Bind ciphertext to the vault, its purpose and, for records, to the row id."""

    parts = ["pm", f"v{version}", vault_id, purpose]
    if identifier:
        parts.append(identifier)
    return ":".join(parts).encode("utf-8")


def constant_time_equals(left: bytes, right: bytes) -> bool:
    return hmac.compare_digest(left, right)


def zeroize(buffer: bytearray | None) -> None:
    """Overwrite a mutable buffer with zeroes."""

    if not buffer:
        return
    try:
        length = len(buffer)
        ctypes.memset((ctypes.c_char * length).from_buffer(buffer), 0, length)
    except (TypeError, ValueError):
        for index in range(len(buffer)):
            buffer[index] = 0
