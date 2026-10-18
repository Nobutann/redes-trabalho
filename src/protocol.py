"""Definições do protocolo, checksum, montagem e parsing dos pacotes."""

from enum import IntEnum

MAGIC = 0xAA
DEFAULT_PORT = 50000


class PacketType(IntEnum):
    HELLO = 0x01
    HELLO_ACK = 0x02
    READY = 0x03
    DATA = 0x04
    ACK = 0x05


class Mode(IntEnum):
    INDIVIDUAL = 0
    BATCH = 1


class Strategy(IntEnum):
    GBN = 0
    SR = 1


class InvalidPacketError(ValueError):
    """Lançada quando o byte MAGIC não confere."""


HEADER_SIZE = 2
HELLO_BODY_SIZE = 5
HELLO_ACK_BODY_SIZE = 1
DATA_HEADER_SIZE = 8
ACK_SIZE = 6
MAX_SEQUENCE = 16383
MAX_PAYLOAD_SIZE = 16


def calculate_checksum(data: bytes) -> int:
    total = 0
    for offset in range(0, len(data), 2):
        word = data[offset] << 8
        if offset + 1 < len(data):
            word |= data[offset + 1]
        total += word

    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)

    return (~total) & 0xFFFF


def verify_checksum(data: bytes) -> bool:
    return calculate_checksum(data) == 0x0000


def _validate_max_text(max_text: int) -> None:
    if not isinstance(max_text, int) or not (30 <= max_text <= 65535):
        raise ValueError(f"max_text deve estar entre 30 e 65535 caracteres (recebido {max_text})")


def build_hello(mode: Mode, strategy: Strategy, max_text: int) -> bytes:
    """Monta o pacote HELLO (7 bytes)."""
    _validate_max_text(max_text)

    header = bytes([MAGIC, PacketType.HELLO])
    body = bytes([int(mode), int(strategy)]) + max_text.to_bytes(2, byteorder="big") + bytes([0x00])
    return header + body


def build_hello_ack(window: int) -> bytes:
    """Monta o pacote HELLO_ACK com o tamanho da janela (3 bytes)."""
    if not (1 <= window <= 5):
        raise ValueError(f"window deve estar entre 1 e 5 (recebido {window})")

    header = bytes([MAGIC, PacketType.HELLO_ACK])
    body = bytes([window])
    return header + body


def build_ready() -> bytes:
    """Monta o pacote READY (2 bytes)."""
    return bytes([MAGIC, PacketType.READY])


def _validate_sequence(seq: int) -> None:
    if not isinstance(seq, int) or not (0 <= seq <= MAX_SEQUENCE):
        raise ValueError(f"seq deve estar entre 0 e {MAX_SEQUENCE} (recebido {seq})")


def _validate_data(seq: int, last: int, payload: bytes) -> None:
    _validate_sequence(seq)
    if not isinstance(last, int) or last not in (0, 1):
        raise ValueError(f"last deve ser 0 ou 1 (recebido {last})")
    if not (1 <= len(payload) <= MAX_PAYLOAD_SIZE):
        raise ValueError(f"Payload de DATA deve ter entre 1 e {MAX_PAYLOAD_SIZE} bytes")
    try:
        code_points = len(payload.decode("utf-8"))
    except UnicodeDecodeError:
        raise ValueError("Payload de DATA deve conter UTF-8 válido") from None
    if not (1 <= code_points <= 4):
        raise ValueError("Payload de DATA deve conter de 1 a 4 pontos de código Unicode")
    if last == 0 and code_points != 4:
        raise ValueError("Fragmento não final deve conter exatamente 4 pontos de código Unicode")


def build_data(seq: int, last: int, payload: bytes) -> bytes:
    _validate_data(seq, last, payload)
    header = (
        bytes([MAGIC, PacketType.DATA])
        + seq.to_bytes(2, byteorder="big")
        + bytes([last, len(payload)])
    )
    packet = header + b"\x00\x00" + payload
    checksum = calculate_checksum(packet)
    return header + checksum.to_bytes(2, byteorder="big") + payload


def prepare_data_packets(text: str, max_text: int) -> list[bytes]:
    _validate_max_text(max_text)
    text_length = len(text)
    if text_length == 0:
        raise ValueError("Texto não pode ser vazio")
    if text_length > max_text:
        raise ValueError(f"Texto deve ter no máximo {max_text} caracteres (recebido {text_length})")

    packets = []
    for seq, offset in enumerate(range(0, text_length, 4)):
        fragment = text[offset : offset + 4]
        packets.append(build_data(
            seq=seq,
            last=int(offset + 4 >= text_length),
            payload=fragment.encode("utf-8"),
        ))
    return packets


def build_ack(seq: int) -> bytes:
    _validate_sequence(seq)
    header = bytes([MAGIC, PacketType.ACK]) + seq.to_bytes(2, byteorder="big")
    packet = header + b"\x00\x00"
    checksum = calculate_checksum(packet)
    return header + checksum.to_bytes(2, byteorder="big")


def parse_packet(data: bytes) -> dict:
    """Decodifica e valida um pacote recebido."""
    if len(data) < HEADER_SIZE:
        raise ValueError(f"Pacote muito curto: esperado pelo menos {HEADER_SIZE} bytes, recebido {len(data)}")

    magic = data[0]
    raw_type = data[1]

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
        mode_raw = data[offset]
        strategy_raw = data[offset + 1]
        max_text = int.from_bytes(data[offset + 2 : offset + 4], byteorder="big")
        reserved = data[offset + 4]
        _validate_max_text(max_text)
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
        window = data[offset]
        if not (1 <= window <= 5):
            raise ValueError(f"window deve estar entre 1 e 5 (recebido {window})")
        return {
            "type": pkt_type,
            "window": window,
        }

    if pkt_type is PacketType.DATA:
        if not (DATA_HEADER_SIZE + 1 <= len(data) <= DATA_HEADER_SIZE + MAX_PAYLOAD_SIZE):
            raise ValueError("Pacote DATA deve ter entre 9 e 24 bytes")
        length = data[5]
        if len(data) != DATA_HEADER_SIZE + length:
            raise ValueError("LEN de DATA não corresponde ao tamanho do payload recebido")
        if not verify_checksum(data):
            raise ValueError("Checksum de DATA inválido")

        seq = int.from_bytes(data[2:4], byteorder="big")
        last = data[4]
        payload = data[DATA_HEADER_SIZE:]
        _validate_data(seq, last, payload)
        return {
            "type": pkt_type,
            "seq": seq,
            "last": last,
            "length": length,
            "checksum": int.from_bytes(data[6:8], byteorder="big"),
            "payload": payload,
        }

    if pkt_type is PacketType.ACK:
        if len(data) != ACK_SIZE:
            raise ValueError(f"Pacote ACK deve ter exatamente {ACK_SIZE} bytes")
        if not verify_checksum(data):
            raise ValueError("Checksum de ACK inválido")

        seq = int.from_bytes(data[2:4], byteorder="big")
        _validate_sequence(seq)
        return {
            "type": pkt_type,
            "seq": seq,
            "checksum": int.from_bytes(data[4:6], byteorder="big"),
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
