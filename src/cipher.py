"""Cifra de César sobre letras ASCII; os demais caracteres permanecem iguais."""

ALPHABET_SIZE = 26


def validate_key(key: int) -> None:
    if not isinstance(key, int) or not (1 <= key <= ALPHABET_SIZE - 1):
        raise ValueError(f"key deve estar entre 1 e {ALPHABET_SIZE - 1} (recebido {key})")


def _shift(text: str, offset: int) -> str:
    result = []
    for char in text:
        if "A" <= char <= "Z":
            start = ord("A")
        elif "a" <= char <= "z":
            start = ord("a")
        else:
            result.append(char)
            continue
        result.append(chr((ord(char) - start + offset) % ALPHABET_SIZE + start))
    return "".join(result)


def encrypt(text: str, key: int) -> str:
    validate_key(key)
    return _shift(text, key)


def decrypt(text: str, key: int) -> str:
    validate_key(key)
    return _shift(text, -key)
