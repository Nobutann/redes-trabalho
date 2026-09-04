"""
server.py — UDP server for the CP1 handshake phase.

Listens for HELLO, replies with HELLO_ACK, waits for READY, then loops.
"""

import argparse
import socket

from protocol import (
    PacketType,
    build_hello_ack,
    parse_packet,
)

DEFAULT_PORT: int = 50000

# Window size is fixed for CP1; dynamic negotiation is deferred to a later checkpoint.
_WINDOW: int = 5

_BUFSIZE: int = 1024


def run_server(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("0.0.0.0", port))
        print(f"[SERVER] Listening on 0.0.0.0:{port}")

        while True:
            _await_hello(sock)


def _await_hello(sock: socket.socket) -> None:
    while True:
        data, addr = sock.recvfrom(_BUFSIZE)

        try:
            pkt = parse_packet(data)
        except Exception as exc:
            print(f"[SERVER] WARNING: malformed packet from {addr}: {exc}")
            continue

        if pkt["type"] is not PacketType.HELLO:
            print(f"[SERVER] WARNING: expected HELLO, got {pkt['type'].name} from {addr} — ignoring")
            continue

        mode = pkt["mode"]
        strategy = pkt["strategy"]
        max_text = pkt["max_text"]

        print(
            f"[SERVER] HELLO received from {addr[0]}:{addr[1]}\n"
            f"         mode     : {mode.name}\n"
            f"         strategy : {strategy.name}\n"
            f"         max_text : {max_text}"
        )

        ack = build_hello_ack(_WINDOW)
        sock.sendto(ack, addr)
        print(f"[SERVER] HELLO_ACK sent (window={_WINDOW})")

        _await_ready(sock, addr, mode, strategy, max_text)
        return


def _await_ready(
    sock: socket.socket,
    expected_addr: tuple[str, int],
    mode,
    strategy,
    max_text: int,
) -> None:
    while True:
        data, addr = sock.recvfrom(_BUFSIZE)

        if addr != expected_addr:
            print(f"[SERVER] WARNING: packet from unexpected address {addr}, ignoring")
            continue

        try:
            pkt = parse_packet(data)
        except Exception as exc:
            print(f"[SERVER] WARNING: malformed packet from {addr}: {exc}")
            continue

        if pkt["type"] is not PacketType.READY:
            print(f"[SERVER] WARNING: expected READY, got {pkt['type'].name} — ignoring")
            continue

        print(
            f"[SERVER] Handshake complete\n"
            f"         client   : {expected_addr[0]}:{expected_addr[1]}\n"
            f"         mode     : {mode.name}\n"
            f"         strategy : {strategy.name}\n"
            f"         max_text : {max_text}\n"
            f"         window   : {_WINDOW}"
        )
        return


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CP1 UDP handshake server")
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"UDP port to bind (default: {DEFAULT_PORT})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_server(args.port)
