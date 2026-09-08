"""Servidor UDP para a fase de handshake (CP1)."""

import argparse
import socket

from protocol import (
    DEFAULT_PORT,
    Mode,
    PacketType,
    Strategy,
    build_hello_ack,
    parse_packet,
)

WINDOW = 5
BUFSIZE = 1024


def run_server(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("0.0.0.0", port))
        print(f"[SERVER] Ouvindo em 0.0.0.0:{port}")

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

        await_ready(sock, addr, mode, strategy, max_text)
        return


def await_ready(
    sock: socket.socket,
    expected_addr: tuple[str, int],
    mode: Mode,
    strategy: Strategy,
    max_text: int,
) -> None:
    sock.settimeout(5.0)
    while True:
        try:
            data, addr = sock.recvfrom(BUFSIZE)
        except TimeoutError:
            print(f"[SERVER] Timeout: READY não recebido de {expected_addr}")
            sock.settimeout(None)
            return

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
        sock.settimeout(None)
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Servidor UDP para handshake (CP1)")
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
