"""Servidor UDP com handshake, recepção confiável e respostas a duplicatas."""

import argparse
import socket
from dataclasses import dataclass, field
from time import monotonic

from cipher import decrypt
from protocol import (
    DEFAULT_PORT,
    ChecksumError,
    Mode,
    PacketType,
    Strategy,
    build_ack,
    build_hello_ack,
    build_nak,
    parse_packet,
    validate_window,
)

WINDOW = 5
BUFSIZE = 1024
TIMEOUT = 5.0
SESSION_TIMEOUT = 25.0
RETENTION_TIME = 25.0


@dataclass
class CompletedSession:
    """Sessão concluída mantida para reenviar ACKs de duplicatas."""

    addr: tuple[str, int]
    received: dict[int, bytes]
    cumulative: bool
    last_seq: int
    expires_at: float = field(default_factory=lambda: monotonic() + RETENTION_TIME)

    def ack_for(self, data: bytes) -> int | None:
        """Retorna o ACK a reenviar se ``data`` for cópia exata de um DATA aceito."""
        seq = int.from_bytes(data[2:4], byteorder="big")
        if self.received.get(seq) != data:
            return None
        return self.last_seq if self.cumulative else seq


def run_server(port: int, window: int = WINDOW, key: int | None = None) -> None:
    validate_window(window)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("0.0.0.0", port))
        print(f"[SERVER] Ouvindo em 0.0.0.0:{sock.getsockname()[1]}")

        completed = None
        while True:
            completed = await_hello(sock, window, completed, key)


def await_hello(
    sock: socket.socket,
    window: int = WINDOW,
    completed: CompletedSession | None = None,
    key: int | None = None,
) -> CompletedSession | None:
    while True:
        data, addr = sock.recvfrom(BUFSIZE)

        if completed is not None and monotonic() >= completed.expires_at:
            completed = None
        if completed is not None and addr == completed.addr:
            ack_seq = completed.ack_for(data)
            if ack_seq is not None:
                sock.sendto(build_ack(ack_seq), addr)
                print(f"[SERVER] Duplicata de sessão concluída; ACK {ack_seq} reenviado")
            continue

        try:
            pkt = parse_packet(data)
        except ValueError as exc:
            print(f"[SERVER] Pacote malformado recebido de {addr}: {exc}")
            continue

        if pkt["type"] is not PacketType.HELLO:
            print(f"[SERVER] Esperado HELLO, recebido {pkt['type'].name} de {addr}")
            continue

        mode = pkt["mode"]
        strategy = pkt["strategy"]
        max_text = pkt["max_text"]

        print(f"[SERVER] HELLO recebido de {addr[0]}:{addr[1]}")
        print(f"  modo: {mode.name}, estratégia: {strategy.name}, max_text: {max_text}")

        ack = build_hello_ack(window)
        sock.sendto(ack, addr)
        print(f"[SERVER] HELLO_ACK enviado (window={window})")

        if not await_ready(sock, addr, mode, strategy, max_text, window):
            return completed
        return receive_message(sock, addr, max_text, mode, strategy, window, key)


def await_ready(
    sock: socket.socket,
    expected_addr: tuple[str, int],
    mode: Mode,
    strategy: Strategy,
    max_text: int,
    window: int = WINDOW,
) -> bool:
    deadline = monotonic() + TIMEOUT
    try:
        while True:
            try:
                data = receive_from(sock, expected_addr, deadline)
            except TimeoutError:
                print(f"[SERVER] Timeout: READY não recebido de {expected_addr}; handshake interrompido")
                return False
            if data is None:
                continue

            try:
                pkt = parse_packet(data)
            except ValueError as exc:
                print(f"[SERVER] Pacote malformado recebido de {expected_addr}: {exc}")
                continue

            if pkt["type"] is not PacketType.READY:
                print(f"[SERVER] Esperado READY, recebido {pkt['type'].name}")
                continue

            print(f"[SERVER] Handshake concluído com {expected_addr[0]}:{expected_addr[1]}")
            print(f"  modo: {mode.name}, estratégia: {strategy.name}, max_text: {max_text}, window: {window}")
            return True
    finally:
        sock.settimeout(None)


def receive_from(sock: socket.socket, expected_addr: tuple[str, int], deadline: float) -> bytes | None:
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError
    sock.settimeout(remaining)
    data, addr = sock.recvfrom(BUFSIZE)
    if addr != expected_addr:
        print(f"[SERVER] Pacote de endereço inesperado {addr} ignorado")
        return None
    return data


def receive_message(
    sock: socket.socket,
    client_addr: tuple[str, int],
    max_text: int,
    mode: Mode,
    strategy: Strategy,
    window: int,
    key: int | None = None,
) -> CompletedSession | None:
    """Recebe os fragmentos de uma mensagem e retorna a sessão concluída, ou None no timeout.

    Em GBN os ACKs são cumulativos e só a próxima sequência é aceita. Em SR, fragmentos
    dentro da janela são aceitos fora de ordem. O modo individual se comporta como SR
    com janela 1.
    """
    cumulative = mode is Mode.BATCH and strategy is Strategy.GBN
    receive_window = window if mode is Mode.BATCH and strategy is Strategy.SR else 1
    received = {}
    fragments = {}
    text_length = 0
    base = 0
    last_seq = None

    def send_ack(seq: int) -> None:
        sock.sendto(build_ack(seq), client_addr)
        print(f"[SERVER] ACK {seq} enviado")

    deadline = monotonic() + SESSION_TIMEOUT
    try:
        while True:
            try:
                data = receive_from(sock, client_addr, deadline)
            except TimeoutError:
                print(f"[SERVER] Timeout: DATA {base} não recebido de {client_addr}; sessão encerrada")
                return None
            if data is None:
                continue

            try:
                pkt = parse_packet(data)
            except ChecksumError as exc:
                if data[1] == PacketType.DATA:
                    print(f"[SERVER] {exc}; NAK {base} enviado")
                    sock.sendto(build_nak(base), client_addr)
                continue
            except ValueError as exc:
                print(f"[SERVER] Pacote malformado recebido de {client_addr}: {exc}")
                continue
            if pkt["type"] is not PacketType.DATA:
                print(f"[SERVER] Esperado DATA, recebido {pkt['type'].name}")
                continue

            seq = pkt["seq"]
            print(f"[SERVER] DATA recebido (seq={seq}, LAST={pkt['last']}, "
                  f"LEN={pkt['length']}, checksum=0x{pkt['checksum']:04X})")

            if received.get(seq) == data:
                print(f"[SERVER] DATA {seq} duplicado")
                send_ack(base - 1 if cumulative else seq)
                continue
            if not (base <= seq < base + receive_window) or seq in received:
                print(f"[SERVER] DATA {seq} fora da janela ou já recebido descartado (base={base})")
                if cumulative and base > 0:
                    send_ack(base - 1)
                continue
            if last_seq is not None and (seq > last_seq or pkt["last"] == 1):
                print(f"[SERVER] DATA {seq} incompatível com LAST {last_seq} descartado")
                continue
            if pkt["last"] == 1 and any(stored > seq for stored in received):
                print(f"[SERVER] LAST {seq} anterior a fragmento já recebido descartado")
                continue

            fragment = pkt["payload"].decode("utf-8")
            if text_length + len(fragment) > max_text:
                print(f"[SERVER] Limite de {max_text} caracteres excedido; DATA {seq} descartado")
                continue

            received[seq] = data
            fragments[seq] = fragment
            text_length += len(fragment)
            if pkt["last"] == 1:
                last_seq = seq
            while base in received:
                base += 1
            send_ack(base - 1 if cumulative else seq)

            if last_seq is not None and base > last_seq:
                show_message("".join(fragments[index] for index in range(last_seq + 1)), key)
                return CompletedSession(client_addr, received, cumulative, last_seq)
            deadline = monotonic() + SESSION_TIMEOUT
    finally:
        sock.settimeout(None)


def show_message(text: str, key: int | None) -> None:
    if key is None:
        print(f"[SERVER] Mensagem reconstruída: {text}")
        return
    print(f"[SERVER] Texto cifrado recebido: {text}")
    print(f"[SERVER] Mensagem reconstruída: {decrypt(text, key)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Servidor UDP para transferência individual ou em batch")
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Porta UDP para bind (padrão: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--window",
        type=int,
        choices=range(1, 6),
        default=WINDOW,
        help=f"Janela de recepção, de 1 a 5 (padrão: {WINDOW})",
    )
    parser.add_argument(
        "--key",
        type=int,
        choices=range(1, 26),
        metavar="1-25",
        help="Chave da cifra de César; deve ser a mesma configurada no cliente",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_server(args.port, args.window, args.key)
