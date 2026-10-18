import unittest

from src.protocol import PacketType, parse_packet, prepare_data_packets, verify_checksum


class TextPreparationTests(unittest.TestCase):
    def assert_prepared_packets(self, text, expected_fragments, max_text=30):
        packets = prepare_data_packets(text, max_text)
        self.assertEqual(len(packets), len(expected_fragments))
        payloads = []
        for packet, (seq, last, fragment) in zip(packets, expected_fragments):
            with self.subTest(seq=seq):
                fields = parse_packet(packet)
                payload = fragment.encode("utf-8")
                self.assertIs(fields["type"], PacketType.DATA)
                self.assertEqual(fields["seq"], seq)
                self.assertEqual(fields["last"], last)
                self.assertEqual(fields["payload"], payload)
                self.assertEqual(fields["length"], len(payload))
                self.assertTrue(verify_checksum(packet))
                payloads.append(fields["payload"])
        self.assertEqual(b"".join(payloads).decode("utf-8"), text)
        return packets

    def test_message_lengths(self):
        cases = (
            ("A", [(0, 1, "A")]),
            ("REDE", [(0, 1, "REDE")]),
            ("REDES", [(0, 0, "REDE"), (1, 1, "S")]),
            ("ABCDEFGH", [(0, 0, "ABCD"), (1, 1, "EFGH")]),
            ("ABCDEFGHIJKLMNOPQRSTUVWXYZ1234", [
                (0, 0, "ABCD"),
                (1, 0, "EFGH"),
                (2, 0, "IJKL"),
                (3, 0, "MNOP"),
                (4, 0, "QRST"),
                (5, 0, "UVWX"),
                (6, 0, "YZ12"),
                (7, 1, "34"),
            ]),
        )
        for text, expected in cases:
            with self.subTest(length=len(text)):
                self.assert_prepared_packets(text, expected)

    def test_rede_local(self):
        packets = self.assert_prepared_packets("REDE LOCAL", [
            (0, 0, "REDE"),
            (1, 0, " LOC"),
            (2, 1, "AL"),
        ])
        self.assertEqual(packets, [
            bytes.fromhex("AA 04 00 00 00 04 BF 6C 52 45 44 45"),
            bytes.fromhex("AA 04 00 01 00 04 E6 66 20 4C 4F 43"),
            bytes.fromhex("AA 04 00 02 01 02 13 AB 41 4C"),
        ])

    def test_preserves_whitespace(self):
        self.assert_prepared_packets(" \tA\n B  ", [(0, 0, " \tA\n"), (1, 1, " B  ")])
        self.assert_prepared_packets("     ", [(0, 0, "    "), (1, 1, " ")])

    def test_accented_characters(self):
        self.assert_prepared_packets("AÇÃOé", [(0, 0, "AÇÃO"), (1, 1, "é")])

    def test_four_byte_characters(self):
        self.assert_prepared_packets("😀🚀🌍🧠A", [(0, 0, "😀🚀🌍🧠"), (1, 1, "A")])

    def test_preserves_combining_characters(self):
        self.assert_prepared_packets("ABCA\u0301", [(0, 0, "ABCA"), (1, 1, "\u0301")])

    def test_limit_counts_code_points_instead_of_bytes(self):
        self.assert_prepared_packets("😀" * 30, [
            (0, 0, "😀😀😀😀"),
            (1, 0, "😀😀😀😀"),
            (2, 0, "😀😀😀😀"),
            (3, 0, "😀😀😀😀"),
            (4, 0, "😀😀😀😀"),
            (5, 0, "😀😀😀😀"),
            (6, 0, "😀😀😀😀"),
            (7, 1, "😀😀"),
        ])

    def test_empty_text(self):
        with self.assertRaisesRegex(ValueError, "vazio"):
            prepare_data_packets("", 30)

    def test_text_exceeds_limit(self):
        for text, max_text in (("A" * 31, 30), ("😀" * 31, 30), ("A" * 32, 31)):
            with self.subTest(max_text=max_text, text=text):
                with self.assertRaisesRegex(ValueError, f"no máximo {max_text} caracteres"):
                    prepare_data_packets(text, max_text)

    def test_max_text_boundaries(self):
        for max_text in (30, 31, 65535):
            with self.subTest(max_text=max_text):
                self.assert_prepared_packets("A", [(0, 1, "A")], max_text)

    def test_invalid_max_text(self):
        for max_text in (-1, 0, 29, 65536, 100000, 30.5):
            with self.subTest(max_text=max_text):
                with self.assertRaisesRegex(ValueError, "max_text.*30.*65535"):
                    prepare_data_packets("A", max_text)

    def test_maximum_message(self):
        text = "A" * 65535
        packets = prepare_data_packets(text, 65535)
        self.assertEqual(len(packets), 16384)
        fields = [parse_packet(packet) for packet in packets]
        self.assertEqual([packet["seq"] for packet in fields], list(range(16384)))
        self.assertEqual([packet["last"] for packet in fields], [0] * 16383 + [1])
        self.assertEqual(fields[0]["payload"], b"AAAA")
        self.assertEqual(fields[-1]["payload"], b"AAA")
        self.assertTrue(all(verify_checksum(packet) for packet in packets))
        self.assertEqual(b"".join(packet["payload"] for packet in fields).decode("utf-8"), text)


if __name__ == "__main__":
    unittest.main()
