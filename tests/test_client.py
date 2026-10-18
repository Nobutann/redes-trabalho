import io
import runpy
import socket
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import call, patch

from src import protocol


CLIENT_PATH = Path(__file__).resolve().parents[1] / "src" / "client.py"


class ClientTests(unittest.TestCase):
    def setUp(self):
        socket_patch = patch("socket.socket")
        self.socket_factory = socket_patch.start()
        self.addCleanup(socket_patch.stop)
        self.sock = self.socket_factory.return_value.__enter__.return_value
        self.sock.recvfrom.return_value = (protocol.build_hello_ack(5), ("127.0.0.1", 50000))
        self.output = io.StringIO()

    def run_cli(self, *args):
        with (
            patch.object(sys, "argv", [str(CLIENT_PATH), *args]),
            patch.dict(sys.modules, {"protocol": protocol}),
            redirect_stdout(self.output),
        ):
            runpy.run_path(str(CLIENT_PATH), run_name="__main__")

    def assert_handshake_only(
        self,
        mode=protocol.Mode.INDIVIDUAL,
        strategy=protocol.Strategy.GBN,
        max_text=30,
        address=("127.0.0.1", 50000),
    ):
        self.assertEqual(self.sock.sendto.call_args_list, [
            call(protocol.build_hello(mode, strategy, max_text), address),
            call(protocol.build_ready(), address),
        ])
        self.sock.recvfrom.assert_called_once()
        self.assertIn("[CLIENT] Handshake concluído", self.output.getvalue())

    def test_without_text_preserves_handshake(self):
        self.run_cli()
        self.assert_handshake_only()
        self.assertNotIn("preparados", self.output.getvalue())

    def test_batch_prepares_data_without_sending_it(self):
        with patch.object(protocol, "build_data", wraps=protocol.build_data) as build_data:
            self.run_cli("--mode", "batch", "--text", "REDE LOCAL")
        self.assert_handshake_only(mode=protocol.Mode.BATCH)
        self.assertEqual(build_data.call_args_list, [
            call(seq=0, last=0, payload=b"REDE"),
            call(seq=1, last=0, payload=b" LOC"),
            call(seq=2, last=1, payload=b"AL"),
        ])
        self.assertIn("[CLIENT] Pacotes DATA preparados: 3", self.output.getvalue())
        self.assertNotIn("texto enviado", self.output.getvalue().lower())
        self.assertNotIn("entregue", self.output.getvalue().lower())

    def test_cli_preserves_unicode_and_whitespace(self):
        text = " A\u0301😀  "
        with patch.object(protocol, "prepare_data_packets",
                          wraps=protocol.prepare_data_packets) as prepare_packets:
            self.run_cli("--mode", "batch", "--text", text)
        prepare_packets.assert_called_once_with(text, 30)
        self.assert_handshake_only(mode=protocol.Mode.BATCH)
        self.assertIn("[CLIENT] Pacotes DATA preparados: 2", self.output.getvalue())

    def test_configured_limit_and_handshake_options(self):
        self.sock.recvfrom.return_value = (protocol.build_hello_ack(5), ("192.0.2.1", 50001))
        self.run_cli("--host", "192.0.2.1", "--port", "50001", "--mode", "batch",
                     "--strategy", "sr", "--max-text", "31", "--text", "A" * 31)
        self.assert_handshake_only(protocol.Mode.BATCH, protocol.Strategy.SR, 31,
                                   ("192.0.2.1", 50001))
        self.assertIn("[CLIENT] Pacotes DATA preparados: 8", self.output.getvalue())

    def test_maximum_configured_limit(self):
        self.run_cli("--mode", "batch", "--max-text", "65535", "--text", "A")
        self.assert_handshake_only(mode=protocol.Mode.BATCH, max_text=65535)
        self.assertIn("[CLIENT] Pacotes DATA preparados: 1", self.output.getvalue())

    def test_invalid_input_opens_no_socket(self):
        cases = (
            (["--text", ""], "vazio"),
            (["--text", "A" * 31], "no máximo 30 caracteres"),
            (["--text", "😀" * 31], "no máximo 30 caracteres"),
            (["--max-text", "29"], "max_text"),
            (["--max-text", "65536"], "max_text"),
            (["--max-text", "65536", "--text", "A"], "max_text"),
        )
        for args, message in cases:
            with self.subTest(args=args):
                self.output.seek(0)
                self.output.truncate()
                with self.assertRaises(SystemExit) as error:
                    self.run_cli(*args)
                self.assertEqual(error.exception.code, 1)
                self.socket_factory.assert_not_called()
                self.assertIn("[CLIENT] Erro:", self.output.getvalue())
                self.assertIn(message, self.output.getvalue())
                self.assertNotIn("HELLO enviado", self.output.getvalue())

    def test_help_describes_characters_and_preparation(self):
        with self.assertRaises(SystemExit) as result:
            self.run_cli("--help")
        self.assertEqual(result.exception.code, 0)
        self.socket_factory.assert_not_called()
        help_text = " ".join(self.output.getvalue().split())
        self.assertIn("--text", help_text)
        self.assertIn("em caracteres, de 30 a 65535", help_text)
        self.assertIn("transferir no modo individual", help_text)
        self.assertIn("em batch, apenas prepara pacotes DATA", help_text)
        self.assertNotIn("em bytes", help_text)

    def test_individual_waits_for_valid_ack_before_next_data(self):
        address = ("127.0.0.1", 50000)
        invalid_ack = protocol.build_ack(0)[:-1] + b"\x00"
        replies = iter([
            (1, protocol.build_hello_ack(5), address),
            (3, protocol.build_ack(0), ("127.0.0.1", 50001)),
            (3, protocol.build_ack(1), address),
            (3, protocol.build_ready(), address),
            (3, invalid_ack, address),
            (3, protocol.build_ack(0), address),
            (4, protocol.build_ack(0), address),
            (4, protocol.build_ack(1), address),
            (5, protocol.build_ack(2), address),
        ])

        def reply(bufsize):
            send_count, data, origin = next(replies)
            self.assertEqual(self.sock.sendto.call_count, send_count)
            self.assertNotIn("Transferência concluída", self.output.getvalue())
            return data, origin

        self.sock.recvfrom.side_effect = reply
        self.run_cli("--text", "REDE LOCAL")
        self.socket_factory.assert_called_once_with(socket.AF_INET, socket.SOCK_DGRAM)
        self.assertEqual(self.sock.sendto.call_args_list, [
            call(protocol.build_hello(protocol.Mode.INDIVIDUAL, protocol.Strategy.GBN, 30), address),
            call(protocol.build_ready(), address),
            call(protocol.build_data(0, 0, b"REDE"), address),
            call(protocol.build_data(1, 0, b" LOC"), address),
            call(protocol.build_data(2, 1, b"AL"), address),
        ])
        self.assertIn("[CLIENT] ACK recebido (seq=2, checksum=0x55F8)", self.output.getvalue())
        self.assertIn("[CLIENT] Transferência concluída", self.output.getvalue())

    def test_individual_strategy_does_not_change_transfer(self):
        address = ("127.0.0.1", 50000)
        for strategy in ("gbn", "sr"):
            with self.subTest(strategy=strategy):
                self.sock.reset_mock()
                self.output.seek(0)
                self.output.truncate()
                self.sock.recvfrom.side_effect = [
                    (protocol.build_hello_ack(5), address),
                    (protocol.build_ack(0), address),
                ]
                self.run_cli("--strategy", strategy, "--text", "AÇÃO")
                self.assertEqual(self.sock.sendto.call_count, 3)
                self.assertEqual(self.sock.sendto.call_args, call(
                    protocol.build_data(0, 1, "AÇÃO".encode("utf-8")), address,
                ))
                self.assertIn("[CLIENT] Transferência concluída", self.output.getvalue())

    def test_localhost_is_resolved_for_source_validation(self):
        address = ("127.0.0.1", 50000)
        self.sock.recvfrom.side_effect = [
            (protocol.build_hello_ack(5), address),
            (protocol.build_ack(0), address),
        ]
        with patch("socket.gethostbyname", return_value="127.0.0.1") as resolve:
            self.run_cli("--host", "localhost", "--text", "A")
        resolve.assert_called_once_with("localhost")
        self.assertEqual(self.sock.sendto.call_args, call(protocol.build_data(0, 1, b"A"), address))
        self.assertIn("[CLIENT] Transferência concluída", self.output.getvalue())

    def test_ack_timeout_exits_without_retransmission(self):
        self.sock.recvfrom.side_effect = [self.sock.recvfrom.return_value, TimeoutError]
        with self.assertRaises(SystemExit) as error:
            self.run_cli("--text", "REDES")
        self.assertEqual(error.exception.code, 1)
        self.assertEqual(self.sock.sendto.call_count, 3)
        self.assertIn("[CLIENT] Timeout: ACK 0 não recebido", self.output.getvalue())
        self.assertNotIn("Transferência concluída", self.output.getvalue())
        self.socket_factory.return_value.__exit__.assert_called_once()

    def test_invalid_packets_do_not_extend_ack_wait(self):
        self.sock.recvfrom.side_effect = [
            self.sock.recvfrom.return_value,
            (protocol.build_ack(1), ("127.0.0.1", 50000)),
        ]
        with patch("time.monotonic", side_effect=[10.0, 10.1, 15.1]):
            with self.assertRaises(SystemExit) as error:
                self.run_cli("--text", "REDES")
        self.assertEqual(error.exception.code, 1)
        self.assertEqual(self.sock.recvfrom.call_count, 2)
        self.assertEqual(self.sock.sendto.call_count, 3)
        self.assertNotIn("Transferência concluída", self.output.getvalue())

    def test_incomplete_handshake_sends_no_data(self):
        cases = (
            TimeoutError,
            (b"invalid", ("127.0.0.1", 50000)),
            (protocol.build_ready(), ("127.0.0.1", 50000)),
            (protocol.build_hello_ack(5), ("127.0.0.1", 50001)),
        )
        for response in cases:
            with self.subTest(response=response):
                self.sock.reset_mock()
                self.output.seek(0)
                self.output.truncate()
                self.sock.recvfrom.side_effect = [response]
                with self.assertRaises(SystemExit) as error:
                    self.run_cli("--text", "A")
                self.assertEqual(error.exception.code, 1)
                self.sock.sendto.assert_called_once()
                self.assertNotIn("Handshake concluído", self.output.getvalue())
                self.assertNotIn("Transferência concluída", self.output.getvalue())


if __name__ == "__main__":
    unittest.main()
