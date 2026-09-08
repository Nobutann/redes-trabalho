"""Definições e parsing dos pacotes de handshake do protocolo."""

import struct
from enum import IntEnum

MAGIC = 0xAA
DEFAULT_PORT = 50000


class PacketType(IntEnum):
    HELLO = 0x01
    HELLO_ACK = 0x02
    READY = 0x03


class Mode(IntEnum):
    INDIVIDUAL = 0
    BATCH = 1


class Strategy(IntEnum):
    GBN = 0
    SR = 1


class InvalidPacketError(ValueError):
    """Lançada quando o byte MAGIC não confere."""


FMT_HEADER = "!BB"
FMT_HELLO_BODY = "!BBHB"
FMT_HELLO_ACK_BODY = "!B"

HEADER_SIZE = struct.calcsize(FMT_HEADER)
HELLO_BODY_SIZE = struct.calcsize(FMT_HELLO_BODY)
HELLO_ACK_BODY_SIZE = struct.calcsize(FMT_HELLO_ACK_BODY)


def build_hello(mode: Mode, strategy: Strategy, max_text: int) -> bytes:
    """Monta o pacote HELLO (7 bytes)."""
    if max_text < 30:
        raise ValueError(f"max_text deve ser >= 30 (recebido {max_text})")

    header = struct.pack(FMT_HEADER, MAGIC, PacketType.HELLO)
    body = struct.pack(FMT_HELLO_BODY, int(mode), int(strategy), max_text, 0x00)
    return header + body


def build_hello_ack(window: int) -> bytes:
    """Monta o pacote HELLO_ACK com o tamanho da janela (3 bytes)."""
    if not (1 <= window <= 5):
        raise ValueError(f"window deve estar entre 1 e 5 (recebido {window})")

    header = struct.pack(FMT_HEADER, MAGIC, PacketType.HELLO_ACK)
    body = struct.pack(FMT_HELLO_ACK_BODY, window)
    return header + body


def build_ready() -> bytes:
    """Monta o pacote READY (2 bytes)."""
    return struct.pack(FMT_HEADER, MAGIC, PacketType.READY)


def parse_packet(data: bytes) -> dict:
    """Decodifica e valida um pacote recebido."""
    if len(data) < HEADER_SIZE:
        raise ValueError(f"Pacote muito curto: esperado pelo menos {HEADER_SIZE} bytes, recebido {len(data)}")

    magic, raw_type = struct.unpack_from(FMT_HEADER, data, offset=0)

    if magic != MAGIC:
        raise InvalidPacketError(f"MAGIC inválido: esperado 0x{MAGIC:02X}, recebido 0x{magic:02X}")

    try:
        pkt_type = PacketType(raw_type)
    except ValueError:
        raise ValueError(f"Tipo de pacote desconhecido: 0x{raw_type:02X}") from None

    offset = HEADER_SIZE

    if pkt_type is PacketType.HELLO:
        min_size = HEADER_SIZE + HELLO_BODY_SIZE
        if len(data) < min_size:
            raise ValueError(f"Pacote HELLO muito curto: esperado {min_size} bytes, recebido {len(data)}")
        mode_raw, strategy_raw, max_text, reserved = struct.unpack_from(
            FMT_HELLO_BODY, data, offset=offset
        )
        if max_text < 30:
            raise ValueError(f"max_text deve ser >= 30 (recebido {max_text})")
        return {
            "type": pkt_type,
            "mode": Mode(mode_raw),
            "strategy": Strategy(strategy_raw),
            "max_text": max_text,
            "reserved": reserved,
        }

    if pkt_type is PacketType.HELLO_ACK:
        min_size = HEADER_SIZE + HELLO_ACK_BODY_SIZE
        if len(data) < min_size:
            raise ValueError(f"Pacote HELLO_ACK muito curto: esperado {min_size} bytes, recebido {len(data)}")
        (window,) = struct.unpack_from(FMT_HELLO_ACK_BODY, data, offset=offset)
        if not (1 <= window <= 5):
            raise ValueError(f"window deve estar entre 1 e 5 (recebido {window})")
        return {
            "type": pkt_type,
            "window": window,
        }

    return {"type": pkt_type}


if __name__ == "__main__":
    # Teste rápido de montagem e decodificação dos pacotes de handshake
    hello = build_hello(Mode.BATCH, Strategy.SR, max_text=100)
    parsed_hello = parse_packet(hello)
    assert parsed_hello["type"] is PacketType.HELLO
    assert parsed_hello["mode"] is Mode.BATCH
    assert parsed_hello["strategy"] is Strategy.SR
    assert parsed_hello["max_text"] == 100

    hello_ack = build_hello_ack(window=5)
    parsed_ack = parse_packet(hello_ack)
    assert parsed_ack["type"] is PacketType.HELLO_ACK
    assert parsed_ack["window"] == 5

    ready = build_ready()
    parsed_ready = parse_packet(ready)
    assert parsed_ready["type"] is PacketType.READY

    print("Testes do protocolo concluídos com sucesso.")
