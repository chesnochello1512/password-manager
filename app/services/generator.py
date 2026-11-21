"""Cryptographically secure password generation and strength estimation."""

from __future__ import annotations

import math
import re
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

_COMMON_PASSWORDS = frozenset(
    {
        "123456",
        "1234567",
        "12345678",
        "123456789",
        "1234567890",
        "111111",
        "000000",
        "654321",
        "abc123",
        "admin",
        "admin123",
        "letmein",
        "welcome",
        "monkey",
        "dragon",
        "football",
        "baseball",
        "master",
        "iloveyou",
        "password",
        "password1",
        "password12",
        "password123",
        "passw0rd",
        "qwerty",
        "qwerty123",
        "qwertyuiop",
        "asdfghjkl",
        "zxcvbnm",
        "пароль",
        "йцукен",
        "фывапролдж",
    }
)

_KEYBOARD_ROWS = (
    "qwertyuiop",
    "asdfghjkl",
    "zxcvbnm",
    "1234567890",
    "йцукенгшщзхъ",
    "фывапролджэ",
    "ячсмитьбю",
)

_LEET_TABLE = str.maketrans(
    {
        "@": "a",
        "0": "o",
        "1": "l",
        "3": "e",
        "4": "a",
        "5": "s",
        "7": "t",
        "8": "b",
        "$": "s",
        "!": "i",
    }
)
_REPEATED_RUN = re.compile(r"(.)\1{2,}")
_REPEATED_BLOCK = re.compile(r"(.{2,4})\1+")
_DATE_LIKE = re.compile(r"(?:(?:19|20)\d{2}|\d{2}[./-]\d{2}[./-]\d{2,4})")


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
    warning: str = ""
    generated: bool = False


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


def _alphabet_size(password: str) -> int:
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
    return max(alphabet_size, 2)


def _normalized(password: str) -> str:
    return password.casefold().translate(_LEET_TABLE)


def _looks_like_common_password(password: str) -> bool:
    normalized = _normalized(password)
    for candidate in (password.casefold(), normalized):
        if candidate in _COMMON_PASSWORDS:
            return True
        if any(len(word) >= 5 and word in candidate for word in _COMMON_PASSWORDS):
            return True
    return False


def _has_sequence(password: str) -> bool:
    lower = password.casefold()
    for row in _KEYBOARD_ROWS:
        for index in range(len(row) - 2):
            chunk = row[index : index + 3]
            if chunk in lower or chunk[::-1] in lower:
                return True

    run = 1
    for previous, current in zip(password, password[1:], strict=False):
        if abs(ord(current) - ord(previous)) == 1:
            run += 1
            if run >= 3:
                return True
        else:
            run = 1
    return False


def _manual_warning(password: str) -> str:
    if _looks_like_common_password(password):
        return "похож на популярный пароль"
    if _REPEATED_RUN.search(password) or _REPEATED_BLOCK.search(password):
        return "повторяющиеся символы или блоки"
    if _has_sequence(password):
        return "предсказуемая последовательность"
    if _DATE_LIKE.search(password):
        return "похож на дату или число"
    if len(password) < 12:
        return "короткий пароль — лучше длинная уникальная фраза"
    return ""


def _manual_entropy(password: str, alphabet_size: int) -> float:
    entropy = len(password) * math.log2(alphabet_size)
    unique = len(set(password))
    if unique <= 2:
        entropy = min(entropy, 8 + unique * 4)
    if _REPEATED_RUN.search(password):
        entropy = min(entropy, 12 + unique * 3)
    if _REPEATED_BLOCK.search(password):
        entropy = min(entropy, 18 + unique)
    if _looks_like_common_password(password):
        entropy = min(entropy, 8.0)
    if _has_sequence(password):
        entropy = min(entropy, 24.0)
    if _DATE_LIKE.search(password):
        entropy = min(entropy, 22.0)

    classes = sum(
        (
            any(char in UPPERCASE for char in password),
            any(char in LOWERCASE for char in password),
            any(char in DIGITS for char in password),
            any(char in SYMBOLS for char in password),
        )
    )
    if classes == 1 and len(password) < 16:
        entropy = min(entropy, 30.0)
    if len(password) < 8:
        entropy = min(entropy, len(password) * 4.0)
    return max(entropy, 0.0)


def estimate_strength(password: str, *, generated: bool = False) -> StrengthResult:
    """Estimate password strength.

    Generated passwords are judged by the generator's uniform-random model.  For
    human-chosen passwords that model is far too optimistic, so repeats,
    keyboard/number sequences, dates and popular passwords are detected and cap
    the estimate.  The exact bit count is only meaningful for generated values;
    the UI hides it for manual input.
    """

    if not password:
        return StrengthResult(score=0, label="Пустой пароль", entropy_bits=0.0, percent=0)

    alphabet_size = _alphabet_size(password)
    if generated:
        entropy = len(password) * math.log2(alphabet_size)
        warning = ""
    else:
        entropy = _manual_entropy(password, alphabet_size)
        warning = _manual_warning(password)

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
        warning=warning,
        generated=generated,
    )
