import io
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, call, patch

from src import protocol

with patch.dict(sys.modules, {"protocol": protocol}):
    from src import server


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.sock = Mock()
        self.address = ("127.0.0.1", 40000)
        self.output = io.StringIO()

    def receive(self, packets, max_text=30):
        self.sock.recvfrom.side_effect = packets
        with redirect_stdout(self.output):
            server.receive_individual(self.sock, self.address, max_text)
        self.assertEqual(self.sock.settimeout.call_args, call(None))

    def test_reconstructs_text_and_sends_acks(self):
        for text in ("A", "REDE", "REDES", "ABCDEFGH", "REDE LOCAL", " AÇÃO 😀 A\u0301  "):
            with self.subTest(text=text):
                self.sock.reset_mock()
                self.output.seek(0)
                self.output.truncate()
                packets = protocol.prepare_data_packets(text, 30)
                self.receive([(packet, self.address) for packet in packets])
                self.assertEqual(self.sock.sendto.call_args_list, [
                    call(protocol.build_ack(seq), self.address) for seq in range(len(packets))
                ])
                self.assertIn(f"[SERVER] Mensagem reconstruída: {text}\n", self.output.getvalue())

    def test_rejects_other_origins_invalid_packets_duplicates_and_gaps(self):
        first = protocol.build_data(0, 0, b"REDE")
        second = protocol.build_data(1, 0, b" LOC")
        last = protocol.build_data(2, 1, b"AL")
        corrupt = first[:-1] + b"\x00"
        replies = iter([
            (0, first, ("127.0.0.1", 40001)),
            (0, corrupt, self.address),
            (0, protocol.build_ack(0), self.address),
            (0, last, self.address),
            (0, first, self.address),
            (1, first, self.address),
            (1, last, self.address),
            (1, second, self.address),
            (2, last, self.address),
        ])

        def reply(bufsize):
            ack_count, packet, origin = next(replies)
            self.assertEqual(self.sock.sendto.call_count, ack_count)
            self.assertNotIn("Mensagem reconstruída", self.output.getvalue())
            return packet, origin

        self.receive(reply)
        self.assertEqual(self.sock.sendto.call_args_list, [
            call(protocol.build_ack(0), self.address),
            call(protocol.build_ack(1), self.address),
            call(protocol.build_ack(2), self.address),
        ])
        self.assertIn("[SERVER] Mensagem reconstruída: REDE LOCAL\n", self.output.getvalue())
        self.assertIn("seq=0, LAST=0, LEN=4, checksum=0xBF6C", self.output.getvalue())

    def test_max_text_counts_characters_and_rejects_excess_before_ack(self):
        packets = protocol.prepare_data_packets("😀" * 32, 32)
        self.receive([(packet, self.address) for packet in packets] + [TimeoutError])
        self.assertEqual(self.sock.sendto.call_count, 7)
        self.assertIn("Limite de 30 caracteres excedido", self.output.getvalue())
        self.assertIn("Timeout: DATA 7", self.output.getvalue())
        self.assertNotIn("Mensagem reconstruída", self.output.getvalue())

    def test_gap_with_last_does_not_complete_message(self):
        self.receive([
            (protocol.build_data(0, 0, b"REDE"), self.address),
            (protocol.build_data(2, 1, b"AL"), self.address),
            TimeoutError,
        ])
        self.sock.sendto.assert_called_once_with(protocol.build_ack(0), self.address)
        self.assertIn("Timeout: DATA 1", self.output.getvalue())
        self.assertNotIn("Mensagem reconstruída", self.output.getvalue())

    def test_rejected_excess_does_not_change_accepted_text(self):
        prefix = protocol.prepare_data_packets("😀" * 32, 32)[:7]
        self.receive([(packet, self.address) for packet in prefix] + [
            (protocol.build_data(7, 1, b"ABCD"), self.address),
            (protocol.build_data(7, 1, b"AB"), self.address),
        ])
        self.assertEqual(self.sock.sendto.call_count, 8)
        self.assertEqual(self.sock.sendto.call_args, call(protocol.build_ack(7), self.address))
        self.assertIn(f"[SERVER] Mensagem reconstruída: {'😀' * 28}AB\n", self.output.getvalue())

    def test_no_data_times_out_without_ack(self):
        self.receive([TimeoutError])
        self.sock.sendto.assert_not_called()
        self.assertIn("sessão encerrada", self.output.getvalue())
        self.assertNotIn("Mensagem reconstruída", self.output.getvalue())

    def test_invalid_packets_do_not_extend_inactivity_timeout(self):
        with patch.object(server, "monotonic", side_effect=[10.0, 10.1, 15.1]):
            self.receive([(protocol.build_ready(), self.address)])
        self.sock.recvfrom.assert_called_once()
        self.sock.sendto.assert_not_called()
        self.assertIn("Timeout: DATA 0", self.output.getvalue())

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
        with redirect_stdout(self.output), patch.object(server, "receive_individual") as receive:
            server.await_hello(self.sock)
        receive.assert_not_called()
        self.sock.sendto.assert_called_once_with(protocol.build_hello_ack(5), self.address)
        self.assertEqual(self.sock.settimeout.call_args, call(None))
        self.assertIn("handshake interrompido", self.output.getvalue())
        self.assertNotIn("Handshake concluído", self.output.getvalue())

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

    def test_batch_does_not_start_transfer(self):
        self.sock.recvfrom.side_effect = [
            (protocol.build_hello(protocol.Mode.BATCH, protocol.Strategy.SR, 30), self.address),
            (protocol.build_ready(), self.address),
        ]
        with redirect_stdout(self.output), patch.object(server, "receive_individual") as receive:
            server.await_hello(self.sock)
        receive.assert_not_called()
        self.sock.sendto.assert_called_once_with(protocol.build_hello_ack(5), self.address)


if __name__ == "__main__":
    unittest.main()
