import io
import runpy
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

    def test_text_prepares_data_without_sending_it(self):
        with patch.object(protocol, "build_data", wraps=protocol.build_data) as build_data:
            self.run_cli("--text", "REDE LOCAL")
        self.assert_handshake_only()
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
            self.run_cli("--text", text)
        prepare_packets.assert_called_once_with(text, 30)
        self.assert_handshake_only()
        self.assertIn("[CLIENT] Pacotes DATA preparados: 2", self.output.getvalue())

    def test_configured_limit_and_handshake_options(self):
        self.run_cli("--host", "192.0.2.1", "--port", "50001", "--mode", "batch",
                     "--strategy", "sr", "--max-text", "31", "--text", "A" * 31)
        self.assert_handshake_only(protocol.Mode.BATCH, protocol.Strategy.SR, 31,
                                   ("192.0.2.1", 50001))
        self.assertIn("[CLIENT] Pacotes DATA preparados: 8", self.output.getvalue())

    def test_maximum_configured_limit(self):
        self.run_cli("--max-text", "65535", "--text", "A")
        self.assert_handshake_only(max_text=65535)
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
        self.assertIn("sem envio por sockets", help_text)
        self.assertNotIn("em bytes", help_text)


if __name__ == "__main__":
    unittest.main()
