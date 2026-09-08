"""Cliente UDP para a fase de handshake (CP1)."""

import argparse
import socket
import sys

from protocol import (
    DEFAULT_PORT,
    Mode,
    PacketType,
    Strategy,
    build_hello,
    build_ready,
    parse_packet,
)

BUFSIZE = 1024
TIMEOUT = 5.0


def run_client(host: str, port: int, mode: Mode, strategy: Strategy, max_text: int) -> None:
    server_addr = (host, port)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(TIMEOUT)

        hello = build_hello(mode, strategy, max_text)
        sock.sendto(hello, server_addr)
        print(f"[CLIENT] HELLO enviado para {host}:{port}")
        print(f"  modo: {mode.name}, estratégia: {strategy.name}, max_text: {max_text}")

        try:
            data, _ = sock.recvfrom(BUFSIZE)
        except TimeoutError:
            print(f"[CLIENT] Timeout: sem resposta de {host}:{port} após {TIMEOUT:.0f}s")
            sys.exit(1)

        try:
            pkt = parse_packet(data)
        except ValueError as exc:
            print(f"[CLIENT] Erro: resposta malformada de {host}:{port}: {exc}")
            sys.exit(1)

        if pkt["type"] is not PacketType.HELLO_ACK:
            print(f"[CLIENT] Erro: esperado HELLO_ACK, recebido {pkt['type'].name}")
            sys.exit(1)

        window = pkt["window"]
        print(f"[CLIENT] HELLO_ACK recebido (window={window})")

        ready = build_ready()
        sock.sendto(ready, server_addr)

        print(f"[CLIENT] Handshake concluído com {host}:{port}")
        print(f"  modo: {mode.name}, estratégia: {strategy.name}, max_text: {max_text}, window: {window}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cliente UDP para handshake (CP1)")
    parser.add_argument("--host", default="127.0.0.1", help="Endereço IP do servidor (padrão: 127.0.0.1)")
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Porta UDP do servidor (padrão: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--mode",
        choices=["individual", "batch"],
        default="individual",
        help="Modo de transferência (padrão: individual)",
    )
    parser.add_argument(
        "--strategy",
        choices=["gbn", "sr"],
        default="gbn",
        help="Estratégia de recuperação de erros no modo batch (padrão: gbn)",
    )
    parser.add_argument(
        "--max-text",
        type=int,
        default=30,
        dest="max_text",
        help="Tamanho máximo do texto em bytes, >= 30 (padrão: 30)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.max_text < 30:
        print(f"[CLIENT] Erro: --max-text deve ser >= 30 (recebido: {args.max_text})")
        sys.exit(1)

    mode = Mode.INDIVIDUAL if args.mode == "individual" else Mode.BATCH
    strategy = Strategy.GBN if args.strategy == "gbn" else Strategy.SR

    run_client(args.host, args.port, mode, strategy, args.max_text)
