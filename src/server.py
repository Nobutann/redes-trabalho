"""Servidor UDP com handshake e recepção individual de texto."""

import argparse
import socket
from time import monotonic

from protocol import (
    DEFAULT_PORT,
    Mode,
    PacketType,
    Strategy,
    build_ack,
    build_hello_ack,
    parse_packet,
)

WINDOW = 5
BUFSIZE = 1024
TIMEOUT = 5.0


def run_server(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("0.0.0.0", port))
        print(f"[SERVER] Ouvindo em 0.0.0.0:{sock.getsockname()[1]}")

        while True:
            await_hello(sock)


def await_hello(sock: socket.socket) -> None:
    while True:
        data, addr = sock.recvfrom(BUFSIZE)

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

        ack = build_hello_ack(WINDOW)
        sock.sendto(ack, addr)
        print(f"[SERVER] HELLO_ACK enviado (window={WINDOW})")

        if await_ready(sock, addr, mode, strategy, max_text) and mode is Mode.INDIVIDUAL:
            receive_individual(sock, addr, max_text)
        return


def await_ready(
    sock: socket.socket,
    expected_addr: tuple[str, int],
    mode: Mode,
    strategy: Strategy,
    max_text: int,
) -> bool:
    deadline = monotonic() + TIMEOUT
    try:
        while True:
            try:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError
                sock.settimeout(remaining)
                data, addr = sock.recvfrom(BUFSIZE)
            except TimeoutError:
                print(f"[SERVER] Timeout: READY não recebido de {expected_addr}; handshake interrompido")
                return False

            if addr != expected_addr:
                print(f"[SERVER] Pacote de endereço inesperado {addr} ignorado")
                continue

            try:
                pkt = parse_packet(data)
            except ValueError as exc:
                print(f"[SERVER] Pacote malformado recebido de {addr}: {exc}")
                continue

            if pkt["type"] is not PacketType.READY:
                print(f"[SERVER] Esperado READY, recebido {pkt['type'].name}")
                continue

            print(f"[SERVER] Handshake concluído com {expected_addr[0]}:{expected_addr[1]}")
            print(f"  modo: {mode.name}, estratégia: {strategy.name}, max_text: {max_text}, window: {WINDOW}")
            return True
    finally:
        sock.settimeout(None)


def receive_individual(sock: socket.socket, expected_addr: tuple[str, int], max_text: int) -> None:
    fragments = []
    text_length = 0
    expected_seq = 0
    deadline = monotonic() + TIMEOUT
    try:
        while True:
            try:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError
                sock.settimeout(remaining)
                data, addr = sock.recvfrom(BUFSIZE)
            except TimeoutError:
                print(f"[SERVER] Timeout: DATA {expected_seq} não recebido de {expected_addr}; sessão encerrada")
                return

            if addr != expected_addr:
                print(f"[SERVER] Pacote de endereço inesperado {addr} ignorado")
                continue

            try:
                pkt = parse_packet(data)
            except ValueError as exc:
                print(f"[SERVER] Pacote malformado recebido de {addr}: {exc}")
                continue

            if pkt["type"] is not PacketType.DATA:
                print(f"[SERVER] Esperado DATA, recebido {pkt['type'].name}")
                continue

            seq = pkt["seq"]
            print(f"[SERVER] DATA recebido (seq={seq}, LAST={pkt['last']}, "
                  f"LEN={pkt['length']}, checksum=0x{pkt['checksum']:04X})")
            if seq != expected_seq:
                print(f"[SERVER] Sequência inesperada: esperado {expected_seq}, recebido {seq}")
                continue

            fragment = pkt["payload"].decode("utf-8")
            if text_length + len(fragment) > max_text:
                print(f"[SERVER] Limite de {max_text} caracteres excedido; DATA {seq} ignorado")
                continue

            fragments.append(fragment)
            text_length += len(fragment)
            sock.sendto(build_ack(seq), expected_addr)
            if pkt["last"] == 1:
                print(f"[SERVER] Mensagem reconstruída: {''.join(fragments)}")
                return

            expected_seq += 1
            deadline = monotonic() + TIMEOUT
    finally:
        sock.settimeout(None)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Servidor UDP para handshake e transferência individual")
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Porta UDP para bind (padrão: {DEFAULT_PORT})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_server(args.port)
