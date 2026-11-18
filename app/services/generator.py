"""Cryptographically secure password generation and strength estimation."""

from __future__ import annotations

import math
import secrets
import string
from dataclasses import dataclass

from app.exceptions import GeneratorError

UPPERCASE = string.ascii_uppercase
LOWERCASE = string.ascii_lowercase
DIGITS = string.digits
SYMBOLS = "!@#$%^&*()-_=+[]{};:,.?/|~"

MIN_LENGTH = 8
MAX_LENGTH = 64


@dataclass(frozen=True, slots=True)
class GeneratorOptions:
    length: int = 20
    uppercase: bool = True
    lowercase: bool = True
    digits: bool = True
    symbols: bool = True

    def validate(self) -> None:
        if not isinstance(self.length, int) or not MIN_LENGTH <= self.length <= MAX_LENGTH:
            raise GeneratorError(f"Длина пароля должна быть от {MIN_LENGTH} до {MAX_LENGTH}.")
        if not any((self.uppercase, self.lowercase, self.digits, self.symbols)):
            raise GeneratorError("Выберите хотя бы один набор символов.")


@dataclass(frozen=True, slots=True)
class StrengthResult:
    score: int
    label: str
    entropy_bits: float
    percent: int


def _pools(options: GeneratorOptions) -> list[str]:
    pools: list[str] = []
    if options.uppercase:
        pools.append(UPPERCASE)
    if options.lowercase:
        pools.append(LOWERCASE)
    if options.digits:
        pools.append(DIGITS)
    if options.symbols:
        pools.append(SYMBOLS)
    return pools


def generate_password(options: GeneratorOptions) -> str:
    options.validate()
    pools = _pools(options)
    alphabet = "".join(pools)
    required = [secrets.choice(pool) for pool in pools]
    remaining = [secrets.choice(alphabet) for _ in range(options.length - len(required))]
    characters = required + remaining
    secrets.SystemRandom().shuffle(characters)
    return "".join(characters)


def estimate_strength(password: str) -> StrengthResult:
    if not password:
        return StrengthResult(score=0, label="Пустой пароль", entropy_bits=0.0, percent=0)

    alphabet_size = 0
    if any(char in UPPERCASE for char in password):
        alphabet_size += len(UPPERCASE)
    if any(char in LOWERCASE for char in password):
        alphabet_size += len(LOWERCASE)
    if any(char in DIGITS for char in password):
        alphabet_size += len(DIGITS)
    if any(char in SYMBOLS for char in password):
        alphabet_size += len(SYMBOLS)
    alphabet_size += sum(
        1
        for char in set(password)
        if not char.isascii() or (not char.isalnum() and char not in SYMBOLS)
    )
    alphabet_size = max(alphabet_size, 2)

    entropy = len(password) * math.log2(alphabet_size)
    if entropy >= 90:
        score, label = 4, "Очень надёжный"
    elif entropy >= 70:
        score, label = 3, "Надёжный"
    elif entropy >= 50:
        score, label = 2, "Средний"
    elif entropy >= 30:
        score, label = 1, "Слабый"
    else:
        score, label = 0, "Очень слабый"

    percent = max(4, min(100, round(entropy / 100 * 100)))
    return StrengthResult(
        score=score,
        label=label,
        entropy_bits=round(entropy, 1),
        percent=percent,
    )
