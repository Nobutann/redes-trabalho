"""Simulação determinística de perdas e corrupções no lado do cliente."""

from collections import Counter

from protocol import DATA_HEADER_SIZE, PacketType

LOSE = "perder"
CORRUPT = "corromper"
FAULT_TYPES = {"DATA": PacketType.DATA, "ACK": PacketType.ACK, "NAK": PacketType.NAK}

FaultRules = dict[tuple[PacketType, int, int], str]


def parse_fault_rules(specs: list[str]) -> FaultRules:
    """Converte regras no formato TIPO:SEQ:OCORRÊNCIA:AÇÃO."""
    rules = {}
    for spec in specs:
        parts = spec.split(":")
        if len(parts) != 4:
            raise ValueError(f"Regra de falha inválida: {spec!r}; use TIPO:SEQ:OCORRÊNCIA:AÇÃO")
        kind, action = parts[0].upper(), parts[3].lower()
        if kind not in FAULT_TYPES:
            raise ValueError(f"Tipo de falha inválido em {spec!r}; use DATA, ACK ou NAK")
        if action not in (LOSE, CORRUPT):
            raise ValueError(f"Ação de falha inválida em {spec!r}; use {LOSE} ou {CORRUPT}")
        try:
            seq, occurrence = int(parts[1]), int(parts[2])
        except ValueError:
            raise ValueError(f"Sequência e ocorrência devem ser inteiros em {spec!r}") from None
        if seq < 0 or occurrence < 1:
            raise ValueError(f"Sequência deve ser >= 0 e ocorrência >= 1 em {spec!r}")

        key = (FAULT_TYPES[kind], seq, occurrence)
        if key in rules:
            raise ValueError(f"Regras conflitantes para {kind} {seq}, ocorrência {occurrence}")
        rules[key] = action
    return rules


class FaultInjector:
    def __init__(self, rules: FaultRules | None = None):
        self.rules = rules or {}
        self.occurrences = Counter()

    def apply(self, kind: PacketType, seq: int, packet: bytes) -> bytes | None:
        """Retorna o pacote original, uma cópia corrompida ou None quando ele deve ser perdido."""
        self.occurrences[kind, seq] += 1
        occurrence = self.occurrences[kind, seq]
        action = self.rules.get((kind, seq, occurrence))
        if action is None:
            return packet

        print(f"[FAULT] {action} {kind.name} {seq} (ocorrência {occurrence})")
        if action == LOSE:
            return None
        # DATA tem o primeiro byte do payload alterado; ACK e NAK, o último byte do checksum.
        index = DATA_HEADER_SIZE if kind is PacketType.DATA else len(packet) - 1
        corrupted = bytearray(packet)
        corrupted[index] ^= 0x01
        return bytes(corrupted)
