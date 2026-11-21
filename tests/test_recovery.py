import io
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from src import cipher, protocol

with patch.dict(sys.modules, {"protocol": protocol}):
    from src import faults

with patch.dict(sys.modules, {"protocol": protocol, "cipher": cipher, "faults": faults}):
    from src import client

ADDRESS = ("127.0.0.1", 40000)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class ReliableSenderTests(unittest.TestCase):
    """Eventos numéricos avançam o relógio e simulam o fim da espera por resposta."""

    def setUp(self):
        self.sock = Mock()
        self.clock = FakeClock()
        self.output = io.StringIO()

    def run_sender(self, text, window, cumulative, events, rules=None):
        self.packets = protocol.prepare_data_packets(text, 30)
        sender = client.ReliableSender(
            self.sock, ADDRESS, self.packets, window, cumulative,
            faults.FaultInjector(rules or {}),
        )
        pending = iter(events)

        def reply(bufsize):
            event = next(pending)
            if isinstance(event, float):
                self.clock.now = event
                raise TimeoutError
            return event, ADDRESS

        self.sock.recvfrom.side_effect = reply
        with redirect_stdout(self.output), patch.object(client, "monotonic", self.clock):
            sender.run()
        with self.assertRaises(StopIteration):
            next(pending)

    def sent_packets(self):
        return [item.args[0] for item in self.sock.sendto.call_args_list]

    def sent_sequences(self):
        return [protocol.parse_packet(packet)["seq"] for packet in self.sent_packets()]

    def test_gbn_timeout_resends_every_pending_packet_from_base(self):
        self.run_sender("ABCDEFGHIJKLMNOPQRST", 3, True, [
            protocol.build_ack(0),
            5.0,
            protocol.build_ack(3),
            protocol.build_ack(4),
        ])
        self.assertEqual(self.sent_sequences(), [0, 1, 2, 3, 1, 2, 3, 4])
        self.assertIn("DATA retransmitido por timeout (seq=1, tentativa=2)", self.output.getvalue())

    def test_gbn_ack_restarts_timer_for_new_base(self):
        self.run_sender("ABCDEFGH", 2, True, [
            4.0,
            protocol.build_ack(0),
            5.0,
            8.9,
            9.0,
            protocol.build_ack(1),
        ])
        self.assertEqual(self.sent_sequences(), [0, 1, 1])

    def test_sr_timeout_resends_only_expired_packet(self):
        self.run_sender("ABCDEFGHIJ", 3, False, [
            protocol.build_ack(0),
            protocol.build_ack(2),
            5.0,
            protocol.build_ack(1),
        ])
        self.assertEqual(self.sent_sequences(), [0, 1, 2, 1])

    def test_sr_nak_resends_requested_packet_once_until_answered(self):
        self.run_sender("ABCDEFGHIJ", 3, False, [
            protocol.build_nak(1),
            protocol.build_nak(1),
            protocol.build_ack(0),
            protocol.build_ack(1),
            protocol.build_ack(2),
        ])
        self.assertEqual(self.sent_sequences(), [0, 1, 2, 1])
        self.assertIn("NAK 1 ignorado: reenvio já realizado", self.output.getvalue())

    def test_gbn_nak_resends_window_from_base(self):
        self.run_sender("ABCDEFGHIJ", 3, True, [
            protocol.build_ack(0),
            protocol.build_nak(1),
            protocol.build_nak(1),
            protocol.build_ack(2),
        ])
        self.assertEqual(self.sent_sequences(), [0, 1, 2, 1, 2])

    def test_nak_outside_pending_range_is_ignored(self):
        self.run_sender("ABCDEFGHIJ", 3, False, [
            protocol.build_nak(5),
            protocol.build_ack(1),
            protocol.build_nak(1),
            protocol.build_ack(0),
            protocol.build_ack(2),
        ])
        self.assertEqual(self.sent_sequences(), [0, 1, 2])

    def test_gives_up_after_three_retransmissions(self):
        with self.assertRaises(SystemExit) as error:
            self.run_sender("A", 1, False, [5.0, 10.0, 15.0, 20.0])
        self.assertEqual(error.exception.code, 1)
        self.assertEqual(self.sent_sequences(), [0, 0, 0, 0])
        self.assertIn("Falha: DATA 0 sem confirmação após 3 retransmissões", self.output.getvalue())

    def test_lost_data_counts_as_attempt(self):
        rules = {(protocol.PacketType.DATA, 0, 1): faults.LOSE}
        self.run_sender("A", 1, False, [5.0, protocol.build_ack(0)], rules)
        self.assertEqual(self.sent_sequences(), [0])
        self.assertIn("tentativa=2", self.output.getvalue())

    def test_corrupted_data_keeps_original_for_retransmission(self):
        rules = {(protocol.PacketType.DATA, 0, 1): faults.CORRUPT}
        self.run_sender("A", 1, False, [protocol.build_nak(0), protocol.build_ack(0)], rules)
        corrupted, original = self.sent_packets()
        with self.assertRaises(protocol.ChecksumError):
            protocol.parse_packet(corrupted)
        self.assertEqual(original, self.packets[0])

    def test_lost_or_corrupted_reply_is_recovered_by_timeout(self):
        for kind, action in ((protocol.PacketType.ACK, faults.LOSE),
                             (protocol.PacketType.ACK, faults.CORRUPT)):
            with self.subTest(action=action):
                self.sock.reset_mock()
                self.clock.now = 0.0
                rules = {(kind, 0, 1): action}
                self.run_sender("A", 1, False, [
                    protocol.build_ack(0), 5.0, protocol.build_ack(0),
                ], rules)
                self.assertEqual(self.sent_sequences(), [0, 0])

    def test_lost_nak_does_not_trigger_retransmission(self):
        rules = {(protocol.PacketType.NAK, 0, 1): faults.LOSE}
        self.run_sender("A", 1, False, [protocol.build_nak(0), protocol.build_ack(0)], rules)
        self.assertEqual(self.sent_sequences(), [0])

    def test_pending_replies_are_processed_before_expired_timer(self):
        self.sock.recvfrom.side_effect = [BlockingIOError]
        self.clock.now = 6.0
        with patch.object(client, "monotonic", self.clock):
            with self.assertRaises(TimeoutError):
                client.receive_reply(self.sock, ADDRESS, 5.0, faults.FaultInjector())
        self.assertEqual(self.sock.settimeout.call_args.args, (0,))


if __name__ == "__main__":
    unittest.main()
