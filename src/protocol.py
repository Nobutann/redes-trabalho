"""
protocol.py — Handshake packet definitions for Trabalho I.

Provides constants, enumerations, build functions, and a generic parsing
function for the three handshake message types used in Checkpoint 1:

    HELLO      (client -> server)  -- 7 bytes
    HELLO_ACK  (server -> client)  -- 3 bytes
    READY      (client -> server)  -- 2 bytes

Wire format uses network byte order (big-endian) throughout.
All multi-byte fields are packed / unpacked with Python's ``struct`` module.
"""

import struct
from enum import IntEnum

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAGIC: int = 0xAA
"""Single-byte magic number that identifies every packet in this protocol."""

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class PacketType(IntEnum):
    """TYPE field values for the common 2-byte header."""

    HELLO = 0x01
    HELLO_ACK = 0x02
    READY = 0x03


class Mode(IntEnum):
    """Operating mode negotiated during the handshake (HELLO -> MODE field)."""

    INDIVIDUAL = 0
    BATCH = 1


class Strategy(IntEnum):
    """Reliability strategy chosen by the client (HELLO -> STRATEGY field).

    Ignored by the server when MODE is INDIVIDUAL, but always present on
    the wire.
    """

    GBN = 0   # Go-Back-N
    SR = 1    # Selective Repeat


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class InvalidPacketError(ValueError):
    """Raised when a received buffer does not start with the expected MAGIC."""


# ---------------------------------------------------------------------------
# Struct format strings
# ---------------------------------------------------------------------------
#   !  -> network byte order (big-endian)
#   B  -> unsigned char  (1 byte)
#   H  -> unsigned short (2 bytes)

_FMT_HEADER = "!BB"          # MAGIC (B) + TYPE (B)
_FMT_HELLO_BODY = "!BBHB"   # MODE (B) + STRATEGY (B) + MAX_TEXT (H) + RESERVED (B)
_FMT_HELLO_ACK_BODY = "!B"  # WINDOW (B)

_HEADER_SIZE = struct.calcsize(_FMT_HEADER)                   # 2 bytes
_HELLO_BODY_SIZE = struct.calcsize(_FMT_HELLO_BODY)           # 5 bytes
_HELLO_ACK_BODY_SIZE = struct.calcsize(_FMT_HELLO_ACK_BODY)  # 1 byte

# ---------------------------------------------------------------------------
# Build functions
# ---------------------------------------------------------------------------


def build_hello(mode: Mode, strategy: Strategy, max_text: int) -> bytes:
    """Build a HELLO packet to be sent from the client to the server.

    Wire layout (7 bytes total):
        Byte 0     -- MAGIC  (0xAA)
        Byte 1     -- TYPE   (0x01 = HELLO)
        Byte 2     -- MODE   (0 = INDIVIDUAL, 1 = BATCH)
        Byte 3     -- STRATEGY (0 = GBN, 1 = SR)
        Bytes 4-5  -- MAX_TEXT (unsigned short, big-endian)
        Byte 6     -- RESERVED (0x00)

    Args:
        mode:      The operating mode chosen by the client.
        strategy:  The reliability strategy chosen by the client.
        max_text:  Maximum total text length (in characters) the client will
                   send.  Must be >= 30.

    Returns:
        A 7-byte bytes object ready to be passed to socket.sendto().

    Raises:
        ValueError: If ``max_text`` is less than 30.
    """
    if max_text < 30:
        raise ValueError(f"max_text must be >= 30 (got {max_text})")

    header = struct.pack(_FMT_HEADER, MAGIC, PacketType.HELLO)
    body = struct.pack(_FMT_HELLO_BODY, int(mode), int(strategy), max_text, 0x00)
    return header + body


def build_hello_ack(window: int) -> bytes:
    """Build a HELLO_ACK packet to be sent from the server to the client.

    Wire layout (3 bytes total):
        Byte 0 -- MAGIC  (0xAA)
        Byte 1 -- TYPE   (0x02 = HELLO_ACK)
        Byte 2 -- WINDOW (1-5, chosen by the server)

    Args:
        window: Window size to advertise to the client.  Must be in [1, 5].

    Returns:
        A 3-byte bytes object ready to be passed to socket.sendto().

    Raises:
        ValueError: If ``window`` is outside the range 1-5.
    """
    if not (1 <= window <= 5):
        raise ValueError(
            f"window must be between 1 and 5 inclusive (got {window})"
        )

    header = struct.pack(_FMT_HEADER, MAGIC, PacketType.HELLO_ACK)
    body = struct.pack(_FMT_HELLO_ACK_BODY, window)
    return header + body


def build_ready() -> bytes:
    """Build a READY packet to be sent from the client to the server.

    This is the final message of the three-way handshake: the client
    acknowledges the server's HELLO_ACK and signals that it is ready to
    begin data transfer.

    Wire layout (2 bytes total):
        Byte 0 -- MAGIC (0xAA)
        Byte 1 -- TYPE  (0x03 = READY)

    Returns:
        A 2-byte bytes object ready to be passed to socket.sendto().
    """
    return struct.pack(_FMT_HEADER, MAGIC, PacketType.READY)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_packet(data: bytes) -> dict:
    """Parse a raw UDP payload and return its fields as a dictionary.

    The function first reads and validates the 2-byte common header
    (MAGIC + TYPE), then dispatches to the appropriate body parser based on
    the TYPE field.

    Returned dict keys (always present):
        "type" (PacketType) -- the message type.

    Additional keys for HELLO packets:
        "mode"      (Mode)
        "strategy"  (Strategy)
        "max_text"  (int)
        "reserved"  (int)  -- should be 0x00; included for completeness /
                              future extension detection.

    Additional keys for HELLO_ACK packets:
        "window" (int)

    READY packets carry no body, so no additional keys are present.

    Args:
        data: Raw bytes received from the socket.

    Returns:
        A dict with the parsed fields as described above.

    Raises:
        InvalidPacketError: If the first byte is not MAGIC (0xAA).
        ValueError: If the TYPE field is unrecognised, the buffer is too
                    short for the declared type, or a field value is out of
                    the allowed range.
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

    # PacketType.READY -- no body
    return {"type": pkt_type}


# ---------------------------------------------------------------------------
# Manual round-trip verification
# ---------------------------------------------------------------------------

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
