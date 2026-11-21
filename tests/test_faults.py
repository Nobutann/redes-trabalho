import io
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from src import protocol

with patch.dict(sys.modules, {"protocol": protocol}):
    from src import faults

DATA = protocol.PacketType.DATA
ACK = protocol.PacketType.ACK
NAK = protocol.PacketType.NAK


class ParseFaultRulesTests(unittest.TestCase):
    def test_parses_rules_case_insensitively(self):
        rules = faults.parse_fault_rules(["DATA:1:1:perder", "ack:0:2:CORROMPER", "NAK:3:1:perder"])
        self.assertEqual(rules, {
            (DATA, 1, 1): faults.LOSE,
            (ACK, 0, 2): faults.CORRUPT,
            (NAK, 3, 1): faults.LOSE,
        })

    def test_rejects_invalid_rules(self):
        for spec in ("DATA:1:1", "HELLO:0:1:perder", "DATA:0:1:atrasar", "DATA:x:1:perder",
                     "DATA:-1:1:perder", "DATA:0:0:perder"):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                faults.parse_fault_rules([spec])

    def test_rejects_conflicting_rules_for_the_same_event(self):
        with self.assertRaisesRegex(ValueError, "conflitantes"):
            faults.parse_fault_rules(["DATA:1:1:perder", "DATA:1:1:corromper"])


class FaultInjectorTests(unittest.TestCase):
    def apply(self, injector, kind, seq, packet):
        with redirect_stdout(io.StringIO()):
            return injector.apply(kind, seq, packet)

    def test_rule_affects_only_the_given_occurrence(self):
        packet = protocol.build_data(1, 1, b"A")
        injector = faults.FaultInjector({(DATA, 1, 2): faults.LOSE})
        self.assertEqual(self.apply(injector, DATA, 1, packet), packet)
        self.assertIsNone(self.apply(injector, DATA, 1, packet))
        self.assertEqual(self.apply(injector, DATA, 1, packet), packet)
        self.assertEqual(self.apply(injector, DATA, 0, packet), packet)

    def test_corrupted_data_changes_first_payload_byte(self):
        packet = protocol.build_data(0, 1, b"A")
        corrupted = self.apply(faults.FaultInjector({(DATA, 0, 1): faults.CORRUPT}), DATA, 0, packet)
        self.assertEqual(corrupted, packet[:-1] + b"@")
        with self.assertRaises(protocol.ChecksumError):
            protocol.parse_packet(corrupted)

    def test_corrupted_reply_changes_checksum_byte(self):
        for kind, packet in ((ACK, protocol.build_ack(2)), (NAK, protocol.build_nak(2))):
            with self.subTest(kind=kind):
                corrupted = self.apply(faults.FaultInjector({(kind, 2, 1): faults.CORRUPT}), kind, 2, packet)
                self.assertEqual(corrupted[:-1], packet[:-1])
                self.assertEqual(corrupted[-1], packet[-1] ^ 0x01)
                with self.assertRaises(protocol.ChecksumError):
                    protocol.parse_packet(corrupted)


if __name__ == "__main__":
    unittest.main()
