from __future__ import annotations

import pytest

from app.exceptions import GeneratorError
from app.services.generator import (
    DIGITS,
    LOWERCASE,
    MAX_LENGTH,
    MIN_LENGTH,
    SYMBOLS,
    UPPERCASE,
    GeneratorOptions,
    estimate_strength,
    generate_password,
)


@pytest.mark.parametrize("length", [8, 9, 16, 20, 32, 48, 64])
def test_generated_length_and_classes(length: int) -> None:
    password = generate_password(GeneratorOptions(length=length))
    assert len(password) == length
    assert any(char in UPPERCASE for char in password)
    assert any(char in LOWERCASE for char in password)
    assert any(char in DIGITS for char in password)
    assert any(char in SYMBOLS for char in password)


def test_only_selected_classes_are_used() -> None:
    options = GeneratorOptions(length=32, uppercase=False, lowercase=True, digits=False, symbols=False)
    password = generate_password(options)
    assert password.isalpha()
    assert password.islower()


def test_invalid_length_and_empty_alphabet() -> None:
    for length in (MIN_LENGTH - 1, MAX_LENGTH + 1):
        with pytest.raises(GeneratorError):
            generate_password(GeneratorOptions(length=length))
    with pytest.raises(GeneratorError):
        generate_password(
            GeneratorOptions(length=20, uppercase=False, lowercase=False, digits=False, symbols=False)
        )


def test_passwords_are_not_repeated() -> None:
    passwords = {generate_password(GeneratorOptions(length=24)) for _ in range(200)}
    assert len(passwords) == 200


def test_strength_grows_with_length() -> None:
    short = estimate_strength("Ab3!")
    medium = estimate_strength("Ab3!xY7@kL9#")
    strong = estimate_strength(generate_password(GeneratorOptions(length=32)))
    assert short.score <= medium.score < strong.score
    assert strong.entropy_bits > 90
    assert 0 <= short.percent <= 100


def test_empty_password_strength() -> None:
    result = estimate_strength("")
    assert result.score == 0
    assert result.entropy_bits == 0
