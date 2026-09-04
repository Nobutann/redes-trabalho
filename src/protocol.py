"""
protocol.py — Handshake packet encoding/decoding for Trabalho I (CP1).

Three message types, all with a 2-byte common header (MAGIC + TYPE):
    HELLO      client -> server  7 bytes
    HELLO_ACK  server -> client  3 bytes
    READY      client -> server  2 bytes

All multi-byte fields use network byte order (big-endian, struct prefix ``!``).
"""

import struct
from enum import IntEnum


MAGIC: int = 0xAA


class PacketType(IntEnum):
    HELLO = 0x01
    HELLO_ACK = 0x02
    READY = 0x03


class Mode(IntEnum):
    INDIVIDUAL = 0
    BATCH = 1


class Strategy(IntEnum):
    """Always present on the wire; ignored by the server when MODE is INDIVIDUAL."""

    GBN = 0   # Go-Back-N
    SR = 1    # Selective Repeat


class InvalidPacketError(ValueError):
    """Raised when the MAGIC byte does not match."""


# struct format strings  (!= big-endian, B= unsigned byte, H= unsigned short)
_FMT_HEADER = "!BB"
_FMT_HELLO_BODY = "!BBHB"
_FMT_HELLO_ACK_BODY = "!B"

_HEADER_SIZE = struct.calcsize(_FMT_HEADER)
_HELLO_BODY_SIZE = struct.calcsize(_FMT_HELLO_BODY)
_HELLO_ACK_BODY_SIZE = struct.calcsize(_FMT_HELLO_ACK_BODY)


def build_hello(mode: Mode, strategy: Strategy, max_text: int) -> bytes:
    """
    Wire layout: MAGIC TYPE MODE STRATEGY MAX_TEXT(2) RESERVED = 7 bytes.
    MAX_TEXT must be >= 30 (protocol minimum).
    """
    if max_text < 30:
        raise ValueError(f"max_text must be >= 30 (got {max_text})")

    header = struct.pack(_FMT_HEADER, MAGIC, PacketType.HELLO)
    body = struct.pack(_FMT_HELLO_BODY, int(mode), int(strategy), max_text, 0x00)
    return header + body


def build_hello_ack(window: int) -> bytes:
    """window must be in [1, 5] (server-determined, protocol constraint)."""
    if not (1 <= window <= 5):
        raise ValueError(
            f"window must be between 1 and 5 inclusive (got {window})"
        )

    header = struct.pack(_FMT_HEADER, MAGIC, PacketType.HELLO_ACK)
    body = struct.pack(_FMT_HELLO_ACK_BODY, window)
    return header + body


def build_ready() -> bytes:
    """Final handshake message — header only, no body."""
    return struct.pack(_FMT_HEADER, MAGIC, PacketType.READY)


def parse_packet(data: bytes) -> dict:
    """
    Validate MAGIC, dispatch on TYPE, and return a dict of decoded fields.

    Always includes "type" (PacketType). HELLO adds "mode", "strategy",
    "max_text", "reserved". HELLO_ACK adds "window". READY has no extra keys.

    Raises InvalidPacketError on bad MAGIC; ValueError on unknown type,
    truncated buffer, or out-of-range field values.
    """
    if len(data) < _HEADER_SIZE:
        raise ValueError(
            f"Packet too short: expected at least {_HEADER_SIZE} bytes, "
            f"got {len(data)}"
        )

    magic, raw_type = struct.unpack_from(_FMT_HEADER, data, offset=0)

    if magic != MAGIC:
        raise InvalidPacketError(
            f"Invalid magic byte: expected 0x{MAGIC:02X}, got 0x{magic:02X}"
        )

    try:
        pkt_type = PacketType(raw_type)
    except ValueError:
        raise ValueError(f"Unknown packet type: 0x{raw_type:02X}")

    offset = _HEADER_SIZE

    if pkt_type is PacketType.HELLO:
        min_size = _HEADER_SIZE + _HELLO_BODY_SIZE
        if len(data) < min_size:
            raise ValueError(
                f"HELLO packet too short: expected {min_size} bytes, "
                f"got {len(data)}"
            )
        mode_raw, strategy_raw, max_text, reserved = struct.unpack_from(
            _FMT_HELLO_BODY, data, offset=offset
        )
        if max_text < 30:
            raise ValueError(f"HELLO.max_text must be >= 30 (got {max_text})")
        return {
            "type": pkt_type,
            "mode": Mode(mode_raw),
            "strategy": Strategy(strategy_raw),
            "max_text": max_text,
            "reserved": reserved,
        }

    if pkt_type is PacketType.HELLO_ACK:
        min_size = _HEADER_SIZE + _HELLO_ACK_BODY_SIZE
        if len(data) < min_size:
            raise ValueError(
                f"HELLO_ACK packet too short: expected {min_size} bytes, "
                f"got {len(data)}"
            )
        (window,) = struct.unpack_from(_FMT_HELLO_ACK_BODY, data, offset=offset)
        if not (1 <= window <= 5):
            raise ValueError(
                f"HELLO_ACK.window must be between 1 and 5 (got {window})"
            )
        return {
            "type": pkt_type,
            "window": window,
        }

    # READY has no body
    return {"type": pkt_type}


if __name__ == "__main__":
    print("=== HELLO round-trip ===")
    hello_bytes = build_hello(Mode.BATCH, Strategy.SR, max_text=100)
    print(f"  Raw bytes ({len(hello_bytes)}): {hello_bytes.hex(' ').upper()}")
    parsed_hello = parse_packet(hello_bytes)
    print(f"  Parsed: {parsed_hello}")
    assert parsed_hello["type"] is PacketType.HELLO
    assert parsed_hello["mode"] is Mode.BATCH
    assert parsed_hello["strategy"] is Strategy.SR
    assert parsed_hello["max_text"] == 100
    assert parsed_hello["reserved"] == 0x00
    print("  OK All assertions passed.\n")

    print("=== HELLO_ACK round-trip ===")
    hello_ack_bytes = build_hello_ack(window=5)
    print(f"  Raw bytes ({len(hello_ack_bytes)}): {hello_ack_bytes.hex(' ').upper()}")
    parsed_hello_ack = parse_packet(hello_ack_bytes)
    print(f"  Parsed: {parsed_hello_ack}")
    assert parsed_hello_ack["type"] is PacketType.HELLO_ACK
    assert parsed_hello_ack["window"] == 5
    print("  OK All assertions passed.\n")

    print("=== READY round-trip ===")
    ready_bytes = build_ready()
    print(f"  Raw bytes ({len(ready_bytes)}): {ready_bytes.hex(' ').upper()}")
    parsed_ready = parse_packet(ready_bytes)
    print(f"  Parsed: {parsed_ready}")
    assert parsed_ready["type"] is PacketType.READY
    print("  OK All assertions passed.\n")

    print("=== Validation: invalid MAGIC ===")
    bad_magic = b"\xFF\x01\x00\x00\x00\x1E\x00"
    try:
        parse_packet(bad_magic)
        assert False, "Should have raised InvalidPacketError"
    except InvalidPacketError as exc:
        print(f"  OK Correctly raised InvalidPacketError: {exc}\n")

    print("=== Validation: max_text < 30 ===")
    try:
        build_hello(Mode.INDIVIDUAL, Strategy.GBN, max_text=10)
        assert False, "Should have raised ValueError"
    except ValueError as exc:
        print(f"  OK Correctly raised ValueError: {exc}\n")

    print("=== Validation: window out of range ===")
    try:
        build_hello_ack(window=0)
        assert False, "Should have raised ValueError"
    except ValueError as exc:
        print(f"  OK Correctly raised ValueError: {exc}\n")

    print("All checks passed -- protocol.py is working correctly.")
