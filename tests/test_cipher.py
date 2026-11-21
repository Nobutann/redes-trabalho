import unittest

from src import cipher


class CaesarCipherTests(unittest.TestCase):
    def test_known_value(self):
        self.assertEqual(cipher.encrypt("REDE LOCAL", 3), "UHGH ORFDO")
        self.assertEqual(cipher.decrypt("UHGH ORFDO", 3), "REDE LOCAL")

    def test_wraps_around_and_preserves_case(self):
        self.assertEqual(cipher.encrypt("XYZ xyz", 3), "ABC abc")

    def test_keeps_other_characters_and_length(self):
        text = "Ação 123, ok? 😀"
        encrypted = cipher.encrypt(text, 13)
        self.assertEqual(encrypted, "Nçãb 123, bx? 😀")
        self.assertEqual(len(encrypted), len(text))

    def test_round_trip_for_every_key(self):
        text = "The quick brown fox jumps over the lazy dog"
        for key in range(1, 26):
            with self.subTest(key=key):
                self.assertEqual(cipher.decrypt(cipher.encrypt(text, key), key), text)

    def test_rejects_invalid_keys(self):
        for key in (0, 26, -1, 1.5):
            with self.subTest(key=key), self.assertRaises(ValueError):
                cipher.encrypt("A", key)


if __name__ == "__main__":
    unittest.main()
