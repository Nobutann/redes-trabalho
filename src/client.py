"""
client.py — UDP client for the CP1 handshake phase.

Sends HELLO, waits for HELLO_ACK, then confirms with READY.
"""

import argparse
import socket
import sys

from protocol import (
    Mode,
    PacketType,
    Strategy,
    build_hello,
    build_ready,
    parse_packet,
)
from server import DEFAULT_PORT

_BUFSIZE: int = 1024
_TIMEOUT: float = 5.0


def run_client(host: str, port: int, mode: Mode, strategy: Strategy, max_text: int) -> None:
    server_addr = (host, port)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(_TIMEOUT)

        hello = build_hello(mode, strategy, max_text)
        sock.sendto(hello, server_addr)
        print(
            f"[CLIENT] HELLO sent to {host}:{port}\n"
            f"         mode     : {mode.name}\n"
            f"         strategy : {strategy.name}\n"
            f"         max_text : {max_text}"
        )

        try:
            data, _ = sock.recvfrom(_BUFSIZE)
        except TimeoutError:
            print(f"[CLIENT] ERROR: no response from {host}:{port} after {_TIMEOUT:.0f}s — aborting")
            sys.exit(1)

        try:
            pkt = parse_packet(data)
        except Exception as exc:
            print(f"[CLIENT] ERROR: malformed response: {exc} — aborting")
            sys.exit(1)

        if pkt["type"] is not PacketType.HELLO_ACK:
            print(f"[CLIENT] ERROR: expected HELLO_ACK, got {pkt['type'].name} — aborting")
            sys.exit(1)

        window: int = pkt["window"]
        print(f"[CLIENT] HELLO_ACK received (window={window})")

        ready = build_ready()
        sock.sendto(ready, server_addr)

        print(
            f"[CLIENT] Handshake complete\n"
            f"         server   : {host}:{port}\n"
            f"         mode     : {mode.name}\n"
            f"         strategy : {strategy.name}\n"
            f"         max_text : {max_text}\n"
            f"         window   : {window}"
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CP1 UDP handshake client")
    parser.add_argument("--host", default="127.0.0.1", help="Server IP address (default: 127.0.0.1)")
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Server UDP port (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--mode",
        choices=["individual", "batch"],
        default="individual",
        help="Transfer mode (default: individual)",
    )
    parser.add_argument(
        "--strategy",
        choices=["gbn", "sr"],
        default="gbn",
        help="Error-recovery strategy — only meaningful in batch mode (default: gbn)",
    )
    parser.add_argument(
        "--max-text",
        type=int,
        default=30,
        dest="max_text",
        help="Maximum text size in bytes, must be >= 30 (default: 30)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.max_text < 30:
        print(f"[CLIENT] ERROR: --max-text must be >= 30 (got {args.max_text})")
        sys.exit(1)

    mode = Mode.INDIVIDUAL if args.mode == "individual" else Mode.BATCH
    strategy = Strategy.GBN if args.strategy == "gbn" else Strategy.SR

    run_client(args.host, args.port, mode, strategy, args.max_text)
