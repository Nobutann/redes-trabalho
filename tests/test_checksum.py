import unittest

from src.protocol import calculate_checksum, verify_checksum


class ChecksumTests(unittest.TestCase):
    def test_even_length(self):
        self.assertEqual(calculate_checksum(bytes.fromhex("00 01")), 0xFFFE)

    def test_odd_length(self):
        self.assertEqual(calculate_checksum(bytes.fromhex("01 02 03")), 0xFBFD)

    def test_carry_folding(self):
        self.assertEqual(calculate_checksum(bytes.fromhex("FF FF 00 01")), 0xFFFE)

    def test_repeated_carry_folding(self):
        self.assertEqual(calculate_checksum(bytes.fromhex("FF FF FF FF 00 01")), 0xFFFE)

    def test_verify_correctly_placed_checksum(self):
        vectors = (
            ("00 01 00 00", 0xFFFE, "00 01 FF FE"),
            ("01 02 00 00 03", 0xFBFD, "01 02 FB FD 03"),
        )
        for raw_data, expected_checksum, raw_received in vectors:
            with self.subTest(data=raw_data):
                data = bytes.fromhex(raw_data)
                expected_received = bytes.fromhex(raw_received)
                self.assertTrue(verify_checksum(expected_received))

                checksum = calculate_checksum(data)
                self.assertEqual(checksum, expected_checksum)
                received = data[:2] + checksum.to_bytes(2, byteorder="big") + data[4:]
                self.assertEqual(received, expected_received)
                self.assertEqual(calculate_checksum(received), 0x0000)
                self.assertTrue(verify_checksum(received))

    def test_verify_rejects_changed_bit(self):
        for raw_received in ("00 01 FF FE", "01 02 FB FD 03"):
            with self.subTest(data=raw_received):
                received = bytes.fromhex(raw_received)
                changed = bytes([received[0] ^ 0x01]) + received[1:]
                self.assertFalse(verify_checksum(changed))

    def test_input_unchanged(self):
        data = bytes.fromhex("01 02 FB FD 03")
        original = bytes.fromhex("01 02 FB FD 03")

        calculate_checksum(data)
        self.assertEqual(data, original)
        self.assertEqual(len(data), 5)

        verify_checksum(data)
        self.assertEqual(data, original)
        self.assertEqual(len(data), 5)

    def test_empty_input(self):
        self.assertEqual(calculate_checksum(b""), 0xFFFF)
        self.assertFalse(verify_checksum(b""))


if __name__ == "__main__":
    unittest.main()
