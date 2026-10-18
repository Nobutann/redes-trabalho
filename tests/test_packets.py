import unittest

from src.protocol import (
    InvalidPacketError,
    Mode,
    PacketType,
    Strategy,
    build_ack,
    build_data,
    build_hello,
    build_hello_ack,
    build_ready,
    calculate_checksum,
    parse_packet,
    verify_checksum,
)


def _with_checksum(data: bytes, offset: int) -> bytes:
    data = data[:offset] + b"\x00\x00" + data[offset + 2:]
    checksum = calculate_checksum(data).to_bytes(2, byteorder="big")
    return data[:offset] + checksum + data[offset + 2:]


class DataPacketTests(unittest.TestCase):
    def test_rede_layout_and_parse(self):
        expected = bytes.fromhex("AA 04 12 34 00 04 AD 38 52 45 44 45")
        packet = build_data(seq=0x1234, last=0, payload=b"REDE")

        self.assertEqual(packet, expected)
        self.assertEqual(len(packet), 12)
        self.assertEqual(packet[2:4], b"\x12\x34")
        self.assertEqual(packet[4:6], b"\x00\x04")
        self.assertEqual(packet[6:8], b"\xad\x38")
        self.assertEqual(packet[8:], b"REDE")
        self.assertTrue(verify_checksum(packet))
        self.assertEqual(parse_packet(expected), {
            "type": PacketType.DATA,
            "seq": 0x1234,
            "last": 0,
            "length": 4,
            "checksum": 0xAD38,
            "payload": b"REDE",
        })

    def test_final_single_character(self):
        expected = bytes.fromhex("AA 04 00 00 01 01 13 FA 41")
        packet = build_data(seq=0, last=1, payload=b"A")

        self.assertEqual(packet, expected)
        self.assertEqual(len(packet), 9)
        self.assertEqual(packet[5], 1)
        self.assertTrue(verify_checksum(packet))
        self.assertEqual(parse_packet(expected), {
            "type": PacketType.DATA,
            "seq": 0,
            "last": 1,
            "length": 1,
            "checksum": 0x13FA,
            "payload": b"A",
        })

    def test_final_accented_fragment(self):
        payload = "AÇÃO".encode("utf-8")
        expected = bytes.fromhex("AA 04 00 00 01 06 08 1F 41 C3 87 C3 83 4F")
        packet = build_data(seq=0, last=1, payload=payload)

        self.assertEqual(len("AÇÃO"), 4)
        self.assertEqual(len(payload), 6)
        self.assertEqual(len(packet), 14)
        self.assertEqual(packet, expected)
        self.assertEqual(parse_packet(expected), {
            "type": PacketType.DATA,
            "seq": 0,
            "last": 1,
            "length": 6,
            "checksum": 0x081F,
            "payload": payload,
        })

    def test_final_four_code_points(self):
        expected = bytes.fromhex("AA 04 00 00 01 04 BE 6C 52 45 44 45")
        packet = build_data(seq=0, last=1, payload=b"REDE")

        self.assertEqual(packet, expected)
        self.assertEqual(parse_packet(packet)["last"], 1)
        self.assertEqual(parse_packet(packet)["payload"], b"REDE")

    def test_maximum_payload_size(self):
        payload = ("\U0001F600" * 4).encode("utf-8")
        packet = build_data(seq=0, last=0, payload=payload)

        self.assertEqual(len(payload), 16)
        self.assertEqual(len(packet), 24)
        self.assertEqual(packet[5], 16)
        self.assertEqual(parse_packet(packet)["payload"], payload)

    def test_code_points_without_normalization(self):
        text = "A\u0301BC"
        payload = text.encode("utf-8")
        packet = build_data(seq=0, last=0, payload=payload)

        self.assertEqual(len(text), 4)
        self.assertEqual(len(payload), 5)
        self.assertEqual(parse_packet(packet)["payload"], payload)

    def test_sequence_boundaries(self):
        for seq, raw_seq in ((0, b"\x00\x00"), (16383, b"\x3f\xff")):
            with self.subTest(seq=seq):
                packet = build_data(seq=seq, last=1, payload=b"A")
                self.assertEqual(packet[2:4], raw_seq)
                self.assertEqual(parse_packet(packet)["seq"], seq)

    def test_invalid_sequence(self):
        for seq in (-1, 16384, 65535, 1.5):
            with self.subTest(seq=seq, operation="build"):
                with self.assertRaisesRegex(ValueError, "seq"):
                    build_data(seq=seq, last=1, payload=b"A")

        for raw_seq in (b"\x40\x00", b"\xff\xff"):
            with self.subTest(seq=raw_seq, operation="parse"):
                packet = _with_checksum(b"\xaa\x04" + raw_seq + b"\x01\x01\x00\x00A", 6)
                self.assertTrue(verify_checksum(packet))
                with self.assertRaisesRegex(ValueError, "seq"):
                    parse_packet(packet)

    def test_invalid_last(self):
        for last in (-1, 2, 255, 1.0):
            with self.subTest(last=last, operation="build"):
                with self.assertRaisesRegex(ValueError, "last"):
                    build_data(seq=0, last=last, payload=b"REDE")

        for last in (2, 255):
            with self.subTest(last=last, operation="parse"):
                packet = _with_checksum(b"\xaa\x04\x00\x00" + bytes([last, 4, 0, 0]) + b"REDE", 6)
                self.assertTrue(verify_checksum(packet))
                with self.assertRaisesRegex(ValueError, "last"):
                    parse_packet(packet)

    def test_invalid_fragment_lengths(self):
        cases = (
            (1, b""),
            (1, b"A" * 17),
            (0, b"A"),
            (0, b"ABC"),
            (0, b"ABCDE"),
            (1, b"ABCDE"),
            (1, "A\u0301BCD".encode("utf-8")),
        )
        for last, payload in cases:
            with self.subTest(last=last, payload=payload):
                with self.assertRaises(ValueError):
                    build_data(seq=0, last=last, payload=payload)

                packet = _with_checksum(
                    b"\xaa\x04\x00\x00" + bytes([last, len(payload), 0, 0]) + payload, 6
                )
                self.assertTrue(verify_checksum(packet))
                with self.assertRaises(ValueError):
                    parse_packet(packet)

    def test_invalid_utf8(self):
        for payload in (b"\xff", b"\xc3", b"\xc0\xaf", b"\xed\xa0\x80"):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ValueError, "UTF-8"):
                    build_data(seq=0, last=1, payload=payload)

                packet = _with_checksum(
                    b"\xaa\x04\x00\x00" + bytes([1, len(payload), 0, 0]) + payload, 6
                )
                self.assertTrue(verify_checksum(packet))
                with self.assertRaisesRegex(ValueError, "UTF-8"):
                    parse_packet(packet)

    def test_incorrect_packet_lengths(self):
        valid = bytes.fromhex("AA 04 12 34 00 04 AD 38 52 45 44 45")
        packets = [valid[:size] for size in range(len(valid))]
        packets.extend((valid + b"\x00", valid + b"\x00" * 13))
        for packet in packets:
            with self.subTest(size=len(packet)):
                if len(packet) >= 8:
                    packet = _with_checksum(packet, 6)
                    self.assertTrue(verify_checksum(packet))
                with self.assertRaises(ValueError):
                    parse_packet(packet)

    def test_len_mismatch(self):
        valid = bytes.fromhex("AA 04 12 34 00 04 AD 38 52 45 44 45")
        for length in (0, 1, 3, 5, 16, 17, 255):
            with self.subTest(length=length):
                packet = _with_checksum(valid[:5] + bytes([length]) + valid[6:], 6)
                self.assertTrue(verify_checksum(packet))
                with self.assertRaisesRegex(ValueError, "LEN"):
                    parse_packet(packet)

    def test_rejects_changed_bit(self):
        valid = bytes.fromhex("AA 04 12 34 00 04 AD 38 52 45 44 45")
        for offset in (2, 4, 6, 11):
            with self.subTest(offset=offset):
                packet = valid[:offset] + bytes([valid[offset] ^ 1]) + valid[offset + 1:]
                with self.assertRaisesRegex(ValueError, "Checksum"):
                    parse_packet(packet)


class AckPacketTests(unittest.TestCase):
    def test_layout_and_parse(self):
        expected = bytes.fromhex("AA 05 12 34 43 C6")
        packet = build_ack(seq=0x1234)

        self.assertEqual(packet, expected)
        self.assertEqual(len(packet), 6)
        self.assertEqual(packet[2:4], b"\x12\x34")
        self.assertEqual(packet[4:6], b"\x43\xc6")
        self.assertTrue(verify_checksum(packet))
        self.assertEqual(parse_packet(expected), {
            "type": PacketType.ACK,
            "seq": 0x1234,
            "checksum": 0x43C6,
        })

    def test_sequence_boundaries(self):
        for seq, expected in (
            (0, "AA 05 00 00 55 FA"),
            (16383, "AA 05 3F FF 15 FB"),
        ):
            with self.subTest(seq=seq):
                packet = build_ack(seq=seq)
                self.assertEqual(packet, bytes.fromhex(expected))
                self.assertEqual(parse_packet(packet)["seq"], seq)

    def test_invalid_sequence(self):
        for seq in (-1, 16384, 65535, 1.5):
            with self.subTest(seq=seq, operation="build"):
                with self.assertRaisesRegex(ValueError, "seq"):
                    build_ack(seq=seq)

        for raw_seq in (b"\x40\x00", b"\xff\xff"):
            with self.subTest(seq=raw_seq, operation="parse"):
                packet = _with_checksum(b"\xaa\x05" + raw_seq + b"\x00\x00", 4)
                self.assertTrue(verify_checksum(packet))
                with self.assertRaisesRegex(ValueError, "seq"):
                    parse_packet(packet)

    def test_incorrect_packet_lengths(self):
        valid = bytes.fromhex("AA 05 12 34 43 C6")
        packets = [valid[:size] for size in range(len(valid))]
        packets.append(valid + b"\x00")
        for packet in packets:
            with self.subTest(size=len(packet)):
                if len(packet) >= 6:
                    packet = _with_checksum(packet, 4)
                    self.assertTrue(verify_checksum(packet))
                with self.assertRaises(ValueError):
                    parse_packet(packet)

    def test_rejects_changed_bit(self):
        valid = bytes.fromhex("AA 05 12 34 43 C6")
        for offset in (2, 4):
            with self.subTest(offset=offset):
                packet = valid[:offset] + bytes([valid[offset] ^ 1]) + valid[offset + 1:]
                with self.assertRaisesRegex(ValueError, "Checksum"):
                    parse_packet(packet)


class PacketCompatibilityTests(unittest.TestCase):
    def test_hello_max_text_boundaries(self):
        for max_text, expected in (
            (30, "AA 01 00 00 00 1E 00"),
            (65535, "AA 01 00 00 FF FF 00"),
        ):
            with self.subTest(max_text=max_text):
                packet = build_hello(Mode.INDIVIDUAL, Strategy.GBN, max_text)
                self.assertEqual(packet, bytes.fromhex(expected))
                self.assertEqual(parse_packet(packet)["max_text"], max_text)

    def test_hello_invalid_max_text(self):
        for max_text in (-1, 0, 29, 65536, 100000, 30.5):
            with self.subTest(max_text=max_text):
                with self.assertRaisesRegex(ValueError, "max_text.*30.*65535"):
                    build_hello(Mode.INDIVIDUAL, Strategy.GBN, max_text)

        with self.assertRaisesRegex(ValueError, "max_text"):
            parse_packet(bytes.fromhex("AA 01 00 00 00 1D 00"))

    def test_handshake_layout_and_parse(self):
        cases = (
            (build_hello(Mode.BATCH, Strategy.SR, max_text=100), "AA 01 01 01 00 64 00", {
                "type": PacketType.HELLO,
                "mode": Mode.BATCH,
                "strategy": Strategy.SR,
                "max_text": 100,
                "reserved": 0,
            }),
            (build_hello_ack(window=5), "AA 02 05", {"type": PacketType.HELLO_ACK, "window": 5}),
            (build_ready(), "AA 03", {"type": PacketType.READY}),
        )
        for packet, expected, fields in cases:
            with self.subTest(packet=expected):
                self.assertEqual(packet, bytes.fromhex(expected))
                self.assertEqual(parse_packet(packet), fields)

    def test_invalid_magic(self):
        for packet, checksum_offset in (
            (bytes.fromhex("AA 04 00 00 01 01 13 FA 41"), 6),
            (bytes.fromhex("AA 05 00 00 55 FA"), 4),
        ):
            with self.subTest(packet_type=packet[1]):
                invalid = _with_checksum(b"\x00" + packet[1:], checksum_offset)
                self.assertTrue(verify_checksum(invalid))
                with self.assertRaises(InvalidPacketError):
                    parse_packet(invalid)

    def test_unknown_type(self):
        for packet, checksum_offset in (
            (bytes.fromhex("AA 04 00 00 01 01 13 FA 41"), 6),
            (bytes.fromhex("AA 05 00 00 55 FA"), 4),
        ):
            with self.subTest(packet_type=packet[1]):
                invalid = _with_checksum(packet[:1] + b"\x06" + packet[2:], checksum_offset)
                self.assertTrue(verify_checksum(invalid))
                with self.assertRaisesRegex(ValueError, "Tipo de pacote desconhecido"):
                    parse_packet(invalid)


if __name__ == "__main__":
    unittest.main()
