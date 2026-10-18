import queue
import socket
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

from src.protocol import (
    Mode,
    PacketType,
    Strategy,
    build_ack,
    build_data,
    build_hello,
    build_hello_ack,
    build_ready,
    parse_packet,
)


ROOT = Path(__file__).resolve().parents[1]
WAIT = 3.0


def stop_process(process):
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=WAIT)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=WAIT)


class TransferIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.lines = []
        self.output = queue.Queue()
        self.server = subprocess.Popen(
            [sys.executable, "-u", "-c",
             "import server; server.TIMEOUT = 1.0; server.run_server(0)"],
            cwd=ROOT / "src", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        self.addCleanup(self.stop_server)
        self.reader = threading.Thread(target=self.read_output, daemon=True)
        self.reader.start()
        line = self.wait_for_line("[SERVER] Ouvindo em 0.0.0.0:")
        self.address = ("127.0.0.1", int(line.rsplit(":", 1)[1]))

    def read_output(self):
        for line in self.server.stdout:
            self.output.put(line.rstrip("\n"))

    def stop_server(self):
        stop_process(self.server)
        self.reader.join(timeout=WAIT)
        self.server.stdout.close()
        self.assertFalse(self.reader.is_alive(), "Leitor da saída do servidor não encerrou")

    def wait_for_line(self, prefix):
        deadline = time.monotonic() + WAIT
        while time.monotonic() < deadline:
            try:
                line = self.output.get(timeout=max(0.001, deadline - time.monotonic()))
            except queue.Empty:
                break
            self.lines.append(line)
            if line.startswith(prefix):
                return line
        self.fail(f"Saída não recebida: {prefix!r}; registros: {self.lines!r}")

    def run_client(self, *args):
        result = subprocess.run(
            [sys.executable, str(ROOT / "src" / "client.py"),
             "--host", "localhost", "--port", str(self.address[1]), *args],
            cwd=ROOT, capture_output=True, text=True, timeout=WAIT,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def open_session(self, sock):
        sock.settimeout(WAIT)
        sock.sendto(build_hello(Mode.INDIVIDUAL, Strategy.GBN, 30), self.address)
        data, origin = sock.recvfrom(1024)
        self.assertEqual(origin, self.address)
        self.assertIs(parse_packet(data)["type"], PacketType.HELLO_ACK)
        sock.sendto(build_ready(), self.address)
        self.wait_for_line("[SERVER] Handshake concluído")

    def assert_message(self, text):
        line = self.wait_for_line("[SERVER] Mensagem reconstruída:")
        self.assertEqual(line, f"[SERVER] Mensagem reconstruída: {text}")

    def test_exact_text_and_sequential_sessions(self):
        cases = (
            ("A", "gbn", 1),
            ("REDE", "sr", 1),
            ("REDES", "gbn", 2),
            ("ABCDEFGH", "sr", 2),
            ("REDE LOCAL", "gbn", 3),
            (" AÇÃO 😀 A\u0301  ", "sr", 3),
            ("ABCDEFGHIJKLMNOPQRSTUVWXYZ1234", "gbn", 8),
        )
        for text, strategy, count in cases:
            with self.subTest(text=text, strategy=strategy):
                output = self.run_client("--strategy", strategy, "--text", text)
                self.assert_message(text)
                self.assertEqual(output.count("[CLIENT] ACK recebido"), count)
                self.assertIn(f"ACK recebido (seq={count - 1}, checksum=", output)
                self.assertGreater(output.index("Transferência concluída"), output.rindex("ACK recebido"))

    def test_new_session_after_handshake_without_text(self):
        output = self.run_client()
        self.assertNotIn("DATA enviado", output)
        self.assertNotIn("Transferência concluída", output)
        self.wait_for_line("[SERVER] Handshake concluído")
        self.wait_for_line("[SERVER] Timeout: DATA 0")
        with self.assertRaises(queue.Empty):
            self.output.get(timeout=1.25)
        self.assertIsNone(self.server.poll())
        self.run_client("--text", "Após espera 😀")
        self.assert_message("Após espera 😀")

    def test_batch_only_prepares_and_allows_next_session(self):
        output = self.run_client("--mode", "batch", "--strategy", "sr", "--text", "REDE LOCAL")
        self.assertIn("Pacotes DATA preparados: 3", output)
        self.assertNotIn("DATA enviado", output)
        self.assertNotIn("Transferência concluída", output)
        self.wait_for_line("[SERVER] Handshake concluído")
        self.run_client("--text", "A")
        self.assert_message("A")

    def test_new_session_after_incomplete_handshake(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(WAIT)
            sock.sendto(build_hello(Mode.INDIVIDUAL, Strategy.GBN, 30), self.address)
            self.assertIs(parse_packet(sock.recvfrom(1024)[0])["type"], PacketType.HELLO_ACK)
            sock.sendto(build_data(0, 1, b"A"), self.address)
            self.wait_for_line("[SERVER] Esperado READY, recebido DATA")
            self.wait_for_line("[SERVER] Timeout: READY")
        self.assertFalse(any("Mensagem reconstruída" in line for line in self.lines))
        self.assertFalse(any("[SERVER] DATA recebido" in line for line in self.lines))
        self.run_client("--text", "REDE LOCAL")
        self.assert_message("REDE LOCAL")

    def test_last_with_a_gap_times_out_and_discards_session(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            self.open_session(sock)
            sock.sendto(build_data(0, 0, b"REDE"), self.address)
            self.assertEqual(sock.recvfrom(1024)[0], build_ack(0))
            sock.sendto(build_data(2, 1, b"AL"), self.address)
            self.wait_for_line("[SERVER] Sequência inesperada: esperado 1, recebido 2")
            sock.settimeout(0.1)
            with self.assertRaises(TimeoutError):
                sock.recvfrom(1024)
            self.wait_for_line("[SERVER] Timeout: DATA 1")
        self.assertFalse(any("Mensagem reconstruída" in line for line in self.lines))
        self.run_client("--text", "Nova sessão")
        self.assert_message("Nova sessão")

    def test_max_text_is_enforced_without_ack_for_excess(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            self.open_session(sock)
            for seq in range(7):
                sock.sendto(build_data(seq, 0, "😀😀😀😀".encode("utf-8")), self.address)
                self.assertEqual(sock.recvfrom(1024)[0], build_ack(seq))
            sock.sendto(build_data(7, 1, b"ABCD"), self.address)
            self.wait_for_line("[SERVER] Limite de 30 caracteres excedido")
            sock.settimeout(0.1)
            with self.assertRaises(TimeoutError):
                sock.recvfrom(1024)
            self.wait_for_line("[SERVER] Timeout: DATA 7")
        self.assertFalse(any("Mensagem reconstruída" in line for line in self.lines))
        self.run_client("--text", "😀" * 30)
        self.assert_message("😀" * 30)


class ClientUDPIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(self.sock.close)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(WAIT)

    def start_client(self, timeout=5.0):
        port = self.sock.getsockname()[1]
        self.client = subprocess.Popen(
            [sys.executable, "-u", "-c",
             f"import client; client.TIMEOUT = {timeout}; "
             f"client.run_client('localhost', {port}, client.Mode.INDIVIDUAL, "
             "client.Strategy.GBN, 30, 'REDES')"],
            cwd=ROOT / "src", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        self.addCleanup(self.stop_client)
        data, self.address = self.sock.recvfrom(1024)
        self.assertIs(parse_packet(data)["type"], PacketType.HELLO)
        self.sock.sendto(build_hello_ack(5), self.address)
        self.assertEqual(self.sock.recvfrom(1024), (build_ready(), self.address))
        self.assertEqual(self.sock.recvfrom(1024), (build_data(0, 0, b"REDE"), self.address))

    def stop_client(self):
        stop_process(self.client)
        self.client.stdout.close()

    def assert_no_next_data(self):
        self.sock.settimeout(0.1)
        with self.assertRaises(TimeoutError):
            self.sock.recvfrom(1024)
        self.sock.settimeout(WAIT)

    def test_next_data_requires_valid_ack_from_expected_origin(self):
        self.start_client()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as other:
            other.sendto(build_ack(0), self.address)
        self.assert_no_next_data()
        for invalid in (build_ack(1), build_ready(), build_ack(0)[:-1] + b"\x00"):
            self.sock.sendto(invalid, self.address)
            self.assert_no_next_data()
        self.sock.sendto(build_ack(0), self.address)
        self.assertEqual(self.sock.recvfrom(1024), (build_data(1, 1, b"S"), self.address))
        self.assertIsNone(self.client.poll())
        self.sock.sendto(build_ack(1), self.address)
        output, _ = self.client.communicate(timeout=WAIT)
        self.assertEqual(self.client.returncode, 0, output)
        self.assertIn("Transferência concluída", output)
        self.assert_no_next_data()

    def test_absent_ack_exits_with_error_without_retransmission(self):
        self.start_client(timeout=0.3)
        output, _ = self.client.communicate(timeout=WAIT)
        self.assertEqual(self.client.returncode, 1, output)
        self.assertIn("Timeout: ACK 0 não recebido", output)
        self.assertNotIn("Transferência concluída", output)
        self.assert_no_next_data()


if __name__ == "__main__":
    unittest.main()
