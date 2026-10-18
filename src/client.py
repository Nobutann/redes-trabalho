"""Cliente UDP com handshake e transferência individual ou em batch."""

import argparse
import socket
import sys
from time import monotonic

from protocol import (
    DEFAULT_PORT,
    Mode,
    PacketType,
    Strategy,
    build_hello,
    build_ready,
    parse_packet,
    prepare_data_packets,
)

BUFSIZE = 1024
TIMEOUT = 5.0


def run_client(
    host: str,
    port: int,
    mode: Mode,
    strategy: Strategy,
    max_text: int,
    text: str | None = None,
) -> None:
    hello = build_hello(mode, strategy, max_text)
    data_packets = prepare_data_packets(text, max_text) if text is not None else None
    server_addr = (socket.gethostbyname(host), port)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(TIMEOUT)

        sock.sendto(hello, server_addr)
        print(f"[CLIENT] HELLO enviado para {host}:{port}")
        print(f"  modo: {mode.name}, estratégia: {strategy.name}, max_text: {max_text}")

        try:
            data, addr = sock.recvfrom(BUFSIZE)
        except TimeoutError:
            print(f"[CLIENT] Timeout: sem resposta de {host}:{port} após {TIMEOUT:.0f}s")
            sys.exit(1)

        if addr != server_addr:
            print(f"[CLIENT] Erro: resposta de endereço inesperado {addr}")
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

        if data_packets is not None:
            print(f"[CLIENT] Pacotes DATA preparados: {len(data_packets)}")
            if mode is Mode.INDIVIDUAL:
                send_individual(sock, server_addr, data_packets)
            else:
                send_batch(sock, server_addr, data_packets, strategy, window)


def send_individual(sock: socket.socket, server_addr: tuple[str, int], packets: list[bytes]) -> None:
    for seq, packet in enumerate(packets):
        sock.sendto(packet, server_addr)
        print(f"[CLIENT] DATA enviado (seq={seq})")
        await_ack(sock, server_addr, seq)
    print("[CLIENT] Transferência concluída: todos os fragmentos confirmados")


def await_ack(sock: socket.socket, server_addr: tuple[str, int], expected_seq: int) -> None:
    deadline = monotonic() + TIMEOUT
    while True:
        try:
            pkt = receive_ack(sock, server_addr, deadline)
        except TimeoutError:
            print(f"[CLIENT] Timeout: ACK {expected_seq} não recebido após {TIMEOUT:.0f}s")
            sys.exit(1)

        if pkt is None:
            continue
        if pkt["seq"] != expected_seq:
            print(f"[CLIENT] Sequência inesperada: esperado {expected_seq}, recebido {pkt['seq']}")
            continue
        return


def receive_ack(sock: socket.socket, server_addr: tuple[str, int], deadline: float) -> dict | None:
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError
    sock.settimeout(remaining)
    data, addr = sock.recvfrom(BUFSIZE)
    if addr != server_addr:
        print(f"[CLIENT] Pacote de endereço inesperado {addr} ignorado")
        return None
    try:
        pkt = parse_packet(data)
    except ValueError as exc:
        print(f"[CLIENT] Pacote malformado recebido: {exc}")
        return None
    if pkt["type"] is not PacketType.ACK:
        print(f"[CLIENT] Esperado ACK, recebido {pkt['type'].name}")
        return None
    print(f"[CLIENT] ACK recebido (seq={pkt['seq']}, checksum=0x{pkt['checksum']:04X})")
    return pkt


def send_batch(
    sock: socket.socket,
    server_addr: tuple[str, int],
    packets: list[bytes],
    strategy: Strategy,
    window: int,
) -> None:
    base = 0
    next_seq = 0
    confirmed = set()
    deadline = monotonic() + TIMEOUT
    while base < len(packets):
        while next_seq < min(base + window, len(packets)):
            sock.sendto(packets[next_seq], server_addr)
            print(f"[CLIENT] DATA enviado (seq={next_seq})")
            next_seq += 1

        try:
            pkt = receive_ack(sock, server_addr, deadline)
        except TimeoutError:
            print(f"[CLIENT] Timeout: sem novas confirmações após {TIMEOUT:.0f}s (base={base})")
            sys.exit(1)
        if pkt is None:
            continue

        seq = pkt["seq"]
        if not (base <= seq < next_seq) or seq in confirmed:
            print(f"[CLIENT] ACK {seq} sem nova confirmação ignorado")
            continue

        previous_base = base
        if strategy is Strategy.GBN:
            base = seq + 1
        else:
            confirmed.add(seq)
            while base in confirmed:
                confirmed.remove(base)
                base += 1
        if base != previous_base:
            print(f"[CLIENT] Janela avançou (base={base}, window={window})")
        deadline = monotonic() + TIMEOUT
    print("[CLIENT] Transferência concluída: todos os fragmentos confirmados")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cliente UDP para transferência individual ou em batch")
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
        help="Estratégia de confirmação no modo batch (padrão: gbn)",
    )
    parser.add_argument(
        "--max-text",
        type=int,
        default=30,
        dest="max_text",
        help="Tamanho máximo do texto em caracteres, de 30 a 65535 (padrão: 30)",
    )
    parser.add_argument(
        "--text",
        help="Texto para transferir no modo individual ou em batch",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    mode = Mode.INDIVIDUAL if args.mode == "individual" else Mode.BATCH
    strategy = Strategy.GBN if args.strategy == "gbn" else Strategy.SR

    try:
        run_client(args.host, args.port, mode, strategy, args.max_text, args.text)
    except ValueError as exc:
        print(f"[CLIENT] Erro: {exc}")
        sys.exit(1)
