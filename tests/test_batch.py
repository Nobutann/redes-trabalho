import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import Mock, call, patch

from src import protocol

with patch.dict(sys.modules, {"protocol": protocol}):
    from src import client, server


TEXT = "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234"


class BatchClientTests(unittest.TestCase):
    def setUp(self):
        self.sock = Mock()
        self.address = ("127.0.0.1", 40000)
        self.packets = protocol.prepare_data_packets(TEXT, 30)
        self.output = io.StringIO()

    def send(self, strategy, window, replies):
        responses = iter(replies)

        def reply(bufsize):
            sent_count, packet, origin = next(responses)
            sent = [item.args[0] for item in self.sock.sendto.call_args_list]
            self.assertEqual(sent, self.packets[:sent_count])
            self.assertNotIn("Transferência concluída", self.output.getvalue())
            return packet, origin

        self.sock.recvfrom.side_effect = reply
        with redirect_stdout(self.output):
            client.send_batch(self.sock, self.address, self.packets, strategy, window)
        with self.assertRaises(StopIteration):
            next(responses)
        self.assertEqual(self.sock.sendto.call_args_list, [
            call(packet, self.address) for packet in self.packets
        ])
        self.assertIn("Transferência concluída", self.output.getvalue())

    def test_fill_and_slide_windows_one_to_five(self):
        expected_counts = {
            1: [1, 2, 3, 4, 5, 6, 7, 8],
            2: [2, 3, 4, 5, 6, 7, 8, 8],
            3: [3, 4, 5, 6, 7, 8, 8, 8],
            4: [4, 5, 6, 7, 8, 8, 8, 8],
            5: [5, 6, 7, 8, 8, 8, 8, 8],
        }
        for strategy in (protocol.Strategy.GBN, protocol.Strategy.SR):
            for window, counts in expected_counts.items():
                with self.subTest(strategy=strategy, window=window):
                    self.sock.reset_mock()
                    self.send(strategy, window, [
                        (count, protocol.build_ack(seq), self.address)
                        for seq, count in enumerate(counts)
                    ])
                    self.output.seek(0)
                    self.output.truncate()

    def test_messages_smaller_than_and_equal_to_window(self):
        for strategy in (protocol.Strategy.GBN, protocol.Strategy.SR):
            for text, counts in (("A", [1]), ("REDES", [2, 2]),
                                 ("ABCDEFGHIJKLMNOPQRST", [5, 5, 5, 5, 5])):
                with self.subTest(strategy=strategy, text=text):
                    self.sock.reset_mock()
                    self.packets = protocol.prepare_data_packets(text, 30)
                    self.send(strategy, 5, [
                        (count, protocol.build_ack(seq), self.address)
                        for seq, count in enumerate(counts)
                    ])
                    self.output.seek(0)
                    self.output.truncate()

    def test_gbn_cumulative_ack_frees_space_immediately(self):
        self.send(protocol.Strategy.GBN, 5, [
            (5, protocol.build_ack(2), self.address),
            (8, protocol.build_ack(0), self.address),
            (8, protocol.build_ack(2), self.address),
            (8, protocol.build_ack(7), self.address),
        ])

    def test_sr_out_of_order_acks_cannot_skip_gaps(self):
        self.send(protocol.Strategy.SR, 5, [
            (5, protocol.build_ack(2), self.address),
            (5, protocol.build_ack(2), self.address),
            (5, protocol.build_ack(4), self.address),
            (5, protocol.build_ack(0), self.address),
            (6, protocol.build_ack(5), self.address),
            (6, protocol.build_ack(1), self.address),
            (8, protocol.build_ack(7), self.address),
            (8, protocol.build_ack(3), self.address),
            (8, protocol.build_ack(1), self.address),
            (8, protocol.build_ack(6), self.address),
        ])

    def test_invalid_and_unsent_acks_do_not_free_space(self):
        for strategy in (protocol.Strategy.GBN, protocol.Strategy.SR):
            with self.subTest(strategy=strategy):
                self.sock.reset_mock()
                self.send(strategy, 5, [
                    (5, protocol.build_ack(0), ("127.0.0.1", 40001)),
                    (5, protocol.build_ack(0)[:-1] + b"\x00", self.address),
                    (5, protocol.build_ready(), self.address),
                    (5, protocol.build_ack(5), self.address),
                    (5, protocol.build_ack(7), self.address),
                    (5, protocol.build_ack(0), self.address),
                    (6, protocol.build_ack(0), self.address),
                    (6, protocol.build_ack(1), self.address),
                    (7, protocol.build_ack(2), self.address),
                    (8, protocol.build_ack(3), self.address),
                    (8, protocol.build_ack(4), self.address),
                    (8, protocol.build_ack(5), self.address),
                    (8, protocol.build_ack(6), self.address),
                    (8, protocol.build_ack(7), self.address),
                ])
                self.output.seek(0)
                self.output.truncate()

    def test_repeated_acks_do_not_extend_wait_or_retransmit(self):
        for strategy, sent_count in ((protocol.Strategy.GBN, 8), (protocol.Strategy.SR, 5)):
            with self.subTest(strategy=strategy):
                self.sock.reset_mock()
                self.sock.recvfrom.side_effect = [
                    (protocol.build_ack(2), self.address),
                    (protocol.build_ack(2), self.address),
                ]
                with (
                    redirect_stdout(self.output),
                    patch.object(client, "monotonic", side_effect=[10.0, 10.1, 10.2, 10.3, 15.3]),
                ):
                    with self.assertRaises(SystemExit) as error:
                        client.send_batch(self.sock, self.address, self.packets, strategy, 5)
                self.assertEqual(error.exception.code, 1)
                self.assertEqual(self.sock.recvfrom.call_count, 2)
                self.assertEqual([item.args[0] for item in self.sock.sendto.call_args_list],
                                 self.packets[:sent_count])
                self.assertNotIn("Transferência concluída", self.output.getvalue())


class BatchServerTests(unittest.TestCase):
    def setUp(self):
        self.sock = Mock()
        self.address = ("127.0.0.1", 40000)
        self.output = io.StringIO()

    def receive(self, strategy, window, packets, max_text=30):
        self.sock.recvfrom.side_effect = packets
        with redirect_stdout(self.output):
            server.receive_batch(self.sock, self.address, max_text, strategy, window)
        self.assertEqual(self.sock.settimeout.call_args, call(None))

    def test_in_order_messages_with_all_windows_and_strategies(self):
        for strategy in (protocol.Strategy.GBN, protocol.Strategy.SR):
            for window in range(1, 6):
                with self.subTest(strategy=strategy, window=window):
                    self.sock.reset_mock()
                    self.output.seek(0)
                    self.output.truncate()
                    packets = protocol.prepare_data_packets(TEXT, 30)
                    self.receive(strategy, window, [(packet, self.address) for packet in packets])
                    self.assertEqual(self.sock.sendto.call_args_list, [
                        call(protocol.build_ack(seq), self.address) for seq in range(8)
                    ])
                    self.assertIn(f"Mensagem reconstruída: {TEXT}\n", self.output.getvalue())

    def test_sr_stores_last_before_preceding_fragments_without_completing(self):
        packets = protocol.prepare_data_packets("REDE LOCAL", 30)
        replies = iter([(0, packets[2]), (1, packets[2]), (1, packets[1]), (2, packets[0])])

        def reply(bufsize):
            ack_count, packet = next(replies)
            self.assertEqual(self.sock.sendto.call_count, ack_count)
            self.assertNotIn("Mensagem reconstruída", self.output.getvalue())
            return packet, self.address

        self.receive(protocol.Strategy.SR, 3, reply)
        self.assertEqual(self.sock.sendto.call_args_list, [
            call(protocol.build_ack(2), self.address),
            call(protocol.build_ack(1), self.address),
            call(protocol.build_ack(0), self.address),
        ])
        self.assertIn("Mensagem reconstruída: REDE LOCAL\n", self.output.getvalue())

    def test_sr_accepts_data_only_inside_receive_window(self):
        packets = protocol.prepare_data_packets("REDE LOCAL", 30)
        self.receive(protocol.Strategy.SR, 2, [
            (packets[2], self.address),
            (packets[1], self.address),
            (packets[2], self.address),
            (packets[0], self.address),
            (packets[2], self.address),
        ])
        self.assertEqual(self.sock.sendto.call_args_list, [
            call(protocol.build_ack(1), self.address),
            call(protocol.build_ack(0), self.address),
            call(protocol.build_ack(2), self.address),
        ])
        self.assertIn("Mensagem reconstruída: REDE LOCAL\n", self.output.getvalue())

    def test_sr_conflicting_last_does_not_discard_accepted_data(self):
        packets = protocol.prepare_data_packets("REDE LOCAL", 30)
        cases = (
            ([packets[2], protocol.build_data(3, 0, b"FAIL"),
              protocol.build_data(1, 1, b"X"), packets[0], packets[1]], [2, 0, 1]),
            ([packets[1], protocol.build_data(0, 1, b"X"), packets[0], packets[2]], [1, 0, 2]),
        )
        for packets_received, ack_sequences in cases:
            with self.subTest(ack_sequences=ack_sequences):
                self.sock.reset_mock()
                self.output.seek(0)
                self.output.truncate()
                self.receive(protocol.Strategy.SR, 5, [
                    (packet, self.address) for packet in packets_received
                ])
                self.assertEqual(self.sock.sendto.call_args_list, [
                    call(protocol.build_ack(seq), self.address) for seq in ack_sequences
                ])
                self.assertIn("Mensagem reconstruída: REDE LOCAL\n", self.output.getvalue())

    def test_gbn_confirms_only_contiguous_received_data(self):
        packets = protocol.prepare_data_packets("REDE LOCAL", 30)
        self.receive(protocol.Strategy.GBN, 3, [
            (packets[1], self.address),
            (packets[0], self.address),
            (packets[0], self.address),
            (packets[2], self.address),
            (packets[1], self.address),
            (packets[2], self.address),
        ])
        self.assertEqual(self.sock.sendto.call_args_list, [
            call(protocol.build_ack(seq), self.address) for seq in (0, 1, 2)
        ])
        self.assertIn("Mensagem reconstruída: REDE LOCAL\n", self.output.getvalue())

    def test_sr_duplicate_does_not_change_character_count_or_text(self):
        text = " AÇÃO 😀 A\u0301  "
        packets = protocol.prepare_data_packets(text, 30)
        self.receive(protocol.Strategy.SR, 3, [
            (packets[1], self.address),
            (protocol.build_data(1, 0, b"FAIL"), self.address),
            (packets[2], self.address),
            (packets[0], self.address),
        ], max_text=30)
        self.assertEqual(self.sock.sendto.call_count, 3)
        self.assertIn(f"Mensagem reconstruída: {text}\n", self.output.getvalue())

        self.sock.reset_mock()
        self.output.seek(0)
        self.output.truncate()
        packets = protocol.prepare_data_packets("😀" * 30, 30)
        self.receive(protocol.Strategy.SR, 5, [
            (packets[index], self.address) for index in (4, 4, 0, 1, 2, 3, 5, 6, 7)
        ])
        self.assertEqual(self.sock.sendto.call_count, 8)
        self.assertIn(f"Mensagem reconstruída: {'😀' * 30}\n", self.output.getvalue())

    def test_excess_is_not_stored_or_acknowledged(self):
        packets = protocol.prepare_data_packets("😀" * 32, 32)
        self.receive(protocol.Strategy.SR, 5, [(packet, self.address) for packet in packets] + [
            (protocol.build_data(7, 1, b"AB"), self.address),
        ])
        self.assertEqual(self.sock.sendto.call_count, 8)
        self.assertIn("Limite de 30 caracteres excedido", self.output.getvalue())
        self.assertIn(f"Mensagem reconstruída: {'😀' * 28}AB\n", self.output.getvalue())

    def test_incomplete_last_times_out_and_restores_socket(self):
        self.receive(protocol.Strategy.SR, 3, [
            (protocol.build_data(2, 1, b"AL"), self.address),
            TimeoutError,
        ])
        self.sock.sendto.assert_called_once_with(protocol.build_ack(2), self.address)
        self.assertNotIn("Mensagem reconstruída", self.output.getvalue())
        self.assertIn("Timeout: DATA 0", self.output.getvalue())

    def test_duplicates_do_not_extend_inactivity_timeout(self):
        packet = protocol.build_data(1, 0, b"REDE")
        with patch.object(server, "monotonic", side_effect=[10.0, 10.1, 10.2, 10.3, 15.3]):
            self.receive(protocol.Strategy.SR, 3, [(packet, self.address), (packet, self.address)])
        self.sock.sendto.assert_called_once_with(protocol.build_ack(1), self.address)
        self.assertEqual(self.sock.recvfrom.call_count, 2)
        self.assertNotIn("Mensagem reconstruída", self.output.getvalue())

    def test_invalid_data_does_not_confirm_or_complete(self):
        packet = protocol.build_data(0, 1, b"A")
        for strategy in (protocol.Strategy.GBN, protocol.Strategy.SR):
            with self.subTest(strategy=strategy):
                self.sock.reset_mock()
                self.receive(strategy, 3, [
                    (packet, ("127.0.0.1", 40001)),
                    (packet[:-1] + b"B", self.address),
                    (protocol.build_ack(0), self.address),
                    TimeoutError,
                ])
                self.sock.sendto.assert_not_called()
                self.assertNotIn("Mensagem reconstruída", self.output.getvalue())


class ServerWindowTests(unittest.TestCase):
    def test_invalid_configuration_opens_no_socket(self):
        for window in (-1, 0, 6, 1.5):
            with self.subTest(window=window), patch("socket.socket") as factory:
                with self.assertRaisesRegex(ValueError, "window"):
                    server.run_server(0, window)
                factory.assert_not_called()

    def test_cli_default_and_allowed_values(self):
        cases = [([], 5)] + [(["--window", str(value)], value) for value in range(1, 6)]
        for args, expected in cases:
            with self.subTest(args=args), patch.object(sys, "argv", ["server.py", *args]):
                self.assertEqual(server.parse_args().window, expected)

    def test_cli_rejects_invalid_values(self):
        for value in ("0", "6", "1.5", "abc"):
            with (
                self.subTest(value=value),
                patch.object(sys, "argv", ["server.py", "--window", value]),
                redirect_stderr(io.StringIO()),
                patch("socket.socket") as factory,
            ):
                with self.assertRaises(SystemExit) as error:
                    server.parse_args()
                self.assertEqual(error.exception.code, 2)
                factory.assert_not_called()

    def test_server_default_window_is_preserved(self):
        with (
            patch("socket.socket") as factory,
            patch.object(server, "await_hello", side_effect=RuntimeError("stop")) as hello,
            redirect_stdout(io.StringIO()),
        ):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                server.run_server(0)
        hello.assert_called_once_with(factory.return_value.__enter__.return_value, 5)


if __name__ == "__main__":
    unittest.main()
