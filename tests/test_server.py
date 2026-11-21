import io
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, call, patch

from src import cipher, protocol

with patch.dict(sys.modules, {"protocol": protocol, "cipher": cipher}):
    from src import server


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.sock = Mock()
        self.address = ("127.0.0.1", 40000)
        self.output = io.StringIO()

    def receive(self, packets, max_text=30, key=None):
        self.sock.recvfrom.side_effect = packets
        with redirect_stdout(self.output):
            result = server.receive_message(
                self.sock, self.address, max_text, protocol.Mode.INDIVIDUAL, protocol.Strategy.GBN, 5, key,
            )
        self.assertEqual(self.sock.settimeout.call_args, call(None))
        return result

    def sent(self):
        return [item.args[0] for item in self.sock.sendto.call_args_list]

    def test_reconstructs_text_and_sends_acks(self):
        for text in ("A", "REDE", "REDES", "ABCDEFGH", "REDE LOCAL", " AÇÃO 😀 Á  "):
            with self.subTest(text=text):
                self.sock.reset_mock()
                self.output.seek(0)
                self.output.truncate()
                packets = protocol.prepare_data_packets(text, 30)
                self.receive([(packet, self.address) for packet in packets])
                self.assertEqual(self.sent(), [protocol.build_ack(seq) for seq in range(len(packets))])
                self.assertIn(f"[SERVER] Mensagem reconstruída: {text}\n", self.output.getvalue())

    def test_corrupted_data_receives_nak_for_first_missing_sequence(self):
        first = protocol.build_data(0, 0, b"REDE")
        last = protocol.build_data(1, 1, b"S")
        self.receive([
            (first[:-1] + b"X", self.address),
            (first, self.address),
            (last[:-1] + b"X", self.address),
            (last, self.address),
        ])
        self.assertEqual(self.sent(), [
            protocol.build_nak(0), protocol.build_ack(0), protocol.build_nak(1), protocol.build_ack(1),
        ])
        self.assertIn("Checksum de DATA inválido; NAK 1 enviado", self.output.getvalue())

    def test_duplicates_are_acknowledged_again_without_changing_text(self):
        packets = protocol.prepare_data_packets("REDE LOCAL", 30)
        self.receive([(packets[index], self.address) for index in (0, 0, 1, 0, 2)])
        self.assertEqual(self.sent(), [protocol.build_ack(seq) for seq in (0, 0, 1, 0, 2)])
        self.assertIn("[SERVER] Mensagem reconstruída: REDE LOCAL\n", self.output.getvalue())

    def test_ignores_other_origins_invalid_packets_and_gaps(self):
        packets = protocol.prepare_data_packets("REDE LOCAL", 30)
        self.receive([
            (packets[0], ("127.0.0.1", 40001)),
            (b"\xaa", self.address),
            (protocol.build_ack(0), self.address),
            (packets[2], self.address),
            (packets[0], self.address),
            (protocol.build_data(0, 0, b"FAIL"), self.address),
            (packets[1], self.address),
            (packets[2], self.address),
        ])
        self.assertEqual(self.sent(), [protocol.build_ack(seq) for seq in range(3)])

    def test_max_text_counts_characters_and_rejects_excess_before_ack(self):
        packets = protocol.prepare_data_packets("😀" * 32, 32)
        self.receive([(packet, self.address) for packet in packets] + [TimeoutError])
        self.assertEqual(self.sock.sendto.call_count, 7)
        self.assertIn("Limite de 30 caracteres excedido", self.output.getvalue())
        self.assertIn("Timeout: DATA 7", self.output.getvalue())
        self.assertNotIn("Mensagem reconstruída", self.output.getvalue())

    def test_gap_with_last_does_not_complete_message(self):
        result = self.receive([
            (protocol.build_data(0, 0, b"REDE"), self.address),
            (protocol.build_data(2, 1, b"AL"), self.address),
            TimeoutError,
        ])
        self.assertIsNone(result)
        self.sock.sendto.assert_called_once_with(protocol.build_ack(0), self.address)
        self.assertIn("Timeout: DATA 1", self.output.getvalue())

    def test_session_timeout_allows_every_client_attempt(self):
        with patch.object(server, "monotonic", side_effect=[10.0, 30.0, 35.1]):
            self.receive([(protocol.build_ready(), self.address)])
        self.sock.recvfrom.assert_called_once()
        self.assertIn("Timeout: DATA 0", self.output.getvalue())

    def test_duplicates_do_not_extend_session_timeout(self):
        packet = protocol.build_data(0, 0, b"REDE")
        with patch.object(server, "monotonic", side_effect=[10.0, 10.1, 10.2, 35.1, 35.2]):
            self.receive([(packet, self.address), (packet, self.address)])
        self.assertEqual(self.sock.recvfrom.call_count, 2)
        self.assertIn("Timeout: DATA 1", self.output.getvalue())

    def test_completed_session_is_returned_for_retention(self):
        packets = protocol.prepare_data_packets("REDE LOCAL", 30)
        completed = self.receive([(packet, self.address) for packet in packets])
        self.assertEqual(completed.addr, self.address)
        self.assertEqual(completed.ack_for(packets[1]), 1)
        self.assertIsNone(completed.ack_for(protocol.build_data(1, 0, b"FAIL")))

    def test_decrypts_message_with_configured_key(self):
        packets = protocol.prepare_data_packets(cipher.encrypt("REDE LOCAL", 3), 30)
        self.receive([(packet, self.address) for packet in packets], key=3)
        self.assertIn("[SERVER] Texto cifrado recebido: UHGH ORFDO\n", self.output.getvalue())
        self.assertIn("[SERVER] Mensagem reconstruída: REDE LOCAL\n", self.output.getvalue())


class HandshakeTests(unittest.TestCase):
    def setUp(self):
        self.sock = Mock()
        self.address = ("127.0.0.1", 40000)
        self.output = io.StringIO()

    def test_ready_reports_success_and_restores_timeout(self):
        self.sock.recvfrom.side_effect = [
            (protocol.build_ready(), ("127.0.0.1", 40001)),
            (b"invalid", self.address),
            (protocol.build_ack(0), self.address),
            (protocol.build_ready(), self.address),
        ]
        with redirect_stdout(self.output):
            completed = server.await_ready(
                self.sock, self.address, protocol.Mode.INDIVIDUAL, protocol.Strategy.GBN, 30,
            )
        self.assertTrue(completed)
        self.assertEqual(self.sock.settimeout.call_args, call(None))
        self.assertIn("Handshake concluído", self.output.getvalue())

    def test_ready_timeout_does_not_start_transfer(self):
        self.sock.recvfrom.side_effect = [
            (protocol.build_hello(protocol.Mode.INDIVIDUAL, protocol.Strategy.GBN, 30), self.address),
            TimeoutError,
        ]
        with redirect_stdout(self.output), patch.object(server, "receive_message") as receive:
            server.await_hello(self.sock)
        receive.assert_not_called()
        self.sock.sendto.assert_called_once_with(protocol.build_hello_ack(5), self.address)
        self.assertEqual(self.sock.settimeout.call_args, call(None))
        self.assertIn("handshake interrompido", self.output.getvalue())

    def test_ready_wait_has_a_fixed_timeout(self):
        self.sock.recvfrom.return_value = (protocol.build_ack(0), self.address)
        with (
            redirect_stdout(self.output),
            patch.object(server, "monotonic", side_effect=[10.0, 10.1, 15.1]),
        ):
            completed = server.await_ready(
                self.sock, self.address, protocol.Mode.INDIVIDUAL, protocol.Strategy.GBN, 30,
            )
        self.assertFalse(completed)
        self.sock.recvfrom.assert_called_once()
        self.assertEqual(self.sock.settimeout.call_args, call(None))

    def test_batch_starts_after_ready_with_session_parameters(self):
        self.sock.recvfrom.side_effect = [
            (protocol.build_hello(protocol.Mode.BATCH, protocol.Strategy.SR, 30), self.address),
            (protocol.build_ready(), self.address),
        ]
        with redirect_stdout(self.output), patch.object(server, "receive_message") as receive:
            server.await_hello(self.sock, window=3, key=7)
        receive.assert_called_once_with(
            self.sock, self.address, 30, protocol.Mode.BATCH, protocol.Strategy.SR, 3, 7,
        )
        self.sock.sendto.assert_called_once_with(protocol.build_hello_ack(3), self.address)
        self.assertIn("window: 3", self.output.getvalue())


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.sock = Mock()
        self.address = ("127.0.0.1", 40000)
        self.packets = protocol.prepare_data_packets("REDE LOCAL", 30)
        self.output = io.StringIO()

    def completed(self, cumulative, expires_at=100.0):
        received = dict(enumerate(self.packets))
        return server.CompletedSession(self.address, received, cumulative, 2, expires_at)

    def wait_hello(self, completed, packets):
        self.sock.recvfrom.side_effect = packets
        with (
            redirect_stdout(self.output),
            patch.object(server, "monotonic", return_value=50.0),
            patch.object(server, "await_ready", return_value=False),
        ):
            with self.assertRaises(StopIteration):
                server.await_hello(self.sock, completed=completed)

    def test_duplicates_receive_ack_again_after_completion(self):
        for cumulative, expected in ((False, 1), (True, 2)):
            with self.subTest(cumulative=cumulative):
                self.sock.reset_mock()
                self.wait_hello(self.completed(cumulative), [(self.packets[1], self.address)])
                self.sock.sendto.assert_called_once_with(protocol.build_ack(expected), self.address)

    def test_retained_origin_cannot_start_new_session(self):
        hello = protocol.build_hello(protocol.Mode.INDIVIDUAL, protocol.Strategy.GBN, 30)
        self.wait_hello(self.completed(False), [
            (hello, self.address), (protocol.build_data(1, 0, b"FAIL"), self.address),
        ])
        self.sock.sendto.assert_not_called()

    def test_other_client_can_start_during_retention(self):
        other = ("127.0.0.1", 40001)
        hello = protocol.build_hello(protocol.Mode.INDIVIDUAL, protocol.Strategy.GBN, 30)
        self.sock.recvfrom.side_effect = [(hello, other)]
        completed = self.completed(False)
        with (
            redirect_stdout(self.output),
            patch.object(server, "monotonic", return_value=50.0),
            patch.object(server, "await_ready", return_value=False),
        ):
            self.assertIs(server.await_hello(self.sock, completed=completed), completed)
        self.sock.sendto.assert_called_once_with(protocol.build_hello_ack(5), other)

    def test_expired_retention_is_discarded(self):
        hello = protocol.build_hello(protocol.Mode.INDIVIDUAL, protocol.Strategy.GBN, 30)
        self.sock.recvfrom.side_effect = [(self.packets[1], self.address), (hello, self.address)]
        with (
            redirect_stdout(self.output),
            patch.object(server, "monotonic", return_value=150.0),
            patch.object(server, "await_ready", return_value=False),
        ):
            self.assertIsNone(server.await_hello(self.sock, completed=self.completed(False)))
        self.sock.sendto.assert_called_once_with(protocol.build_hello_ack(5), self.address)


if __name__ == "__main__":
    unittest.main()
