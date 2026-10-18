"""Servidor UDP com handshake e recepção individual ou em batch."""

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
    validate_window,
)

WINDOW = 5
BUFSIZE = 1024
TIMEOUT = 5.0


def run_server(port: int, window: int = WINDOW) -> None:
    validate_window(window)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("0.0.0.0", port))
        print(f"[SERVER] Ouvindo em 0.0.0.0:{sock.getsockname()[1]}")

        while True:
            await_hello(sock, window)


def await_hello(sock: socket.socket, window: int = WINDOW) -> None:
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

        ack = build_hello_ack(window)
        sock.sendto(ack, addr)
        print(f"[SERVER] HELLO_ACK enviado (window={window})")

        if await_ready(sock, addr, mode, strategy, max_text, window):
            if mode is Mode.INDIVIDUAL:
                receive_individual(sock, addr, max_text)
            else:
                receive_batch(sock, addr, max_text, strategy, window)
        return


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
            print(f"  modo: {mode.name}, estratégia: {strategy.name}, max_text: {max_text}, window: {window}")
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
                pkt = receive_data(sock, expected_addr, deadline)
            except TimeoutError:
                print(f"[SERVER] Timeout: DATA {expected_seq} não recebido de {expected_addr}; sessão encerrada")
                return

            if pkt is None:
                continue

            seq = pkt["seq"]
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


def receive_data(sock: socket.socket, expected_addr: tuple[str, int], deadline: float) -> dict | None:
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError
    sock.settimeout(remaining)
    data, addr = sock.recvfrom(BUFSIZE)
    if addr != expected_addr:
        print(f"[SERVER] Pacote de endereço inesperado {addr} ignorado")
        return None
    try:
        pkt = parse_packet(data)
    except ValueError as exc:
        print(f"[SERVER] Pacote malformado recebido de {addr}: {exc}")
        return None
    if pkt["type"] is not PacketType.DATA:
        print(f"[SERVER] Esperado DATA, recebido {pkt['type'].name}")
        return None
    print(f"[SERVER] DATA recebido (seq={pkt['seq']}, LAST={pkt['last']}, "
          f"LEN={pkt['length']}, checksum=0x{pkt['checksum']:04X})")
    return pkt


def receive_batch(
    sock: socket.socket,
    expected_addr: tuple[str, int],
    max_text: int,
    strategy: Strategy,
    window: int,
) -> None:
    if strategy is Strategy.GBN:
        # Confirmar cada sequência contígua aceita também produz ACKs cumulativos.
        receive_individual(sock, expected_addr, max_text)
        return

    fragments = {}
    text_length = 0
    base = 0
    last_seq = None
    deadline = monotonic() + TIMEOUT
    try:
        while True:
            try:
                pkt = receive_data(sock, expected_addr, deadline)
            except TimeoutError:
                print(f"[SERVER] Timeout: DATA {base} não recebido de {expected_addr}; sessão encerrada")
                return
            if pkt is None:
                continue

            seq = pkt["seq"]
            if not (base <= seq < base + window) or seq in fragments:
                print(f"[SERVER] DATA {seq} fora da janela ou já recebido ignorado (base={base})")
                continue
            if last_seq is not None and (seq > last_seq or pkt["last"] == 1):
                print(f"[SERVER] DATA {seq} incompatível com LAST {last_seq} ignorado")
                continue
            if pkt["last"] == 1 and any(received > seq for received in fragments):
                print(f"[SERVER] LAST {seq} anterior a fragmento já recebido ignorado")
                continue

            fragment = pkt["payload"].decode("utf-8")
            if text_length + len(fragment) > max_text:
                print(f"[SERVER] Limite de {max_text} caracteres excedido; DATA {seq} ignorado")
                continue
            fragments[seq] = fragment
            text_length += len(fragment)
            if pkt["last"] == 1:
                last_seq = seq
            while base in fragments:
                base += 1
            sock.sendto(build_ack(seq), expected_addr)
            if last_seq is not None and base > last_seq:
                text = "".join(fragments[index] for index in range(last_seq + 1))
                print(f"[SERVER] Mensagem reconstruída: {text}")
                return
            deadline = monotonic() + TIMEOUT
    finally:
        sock.settimeout(None)


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
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_server(args.port, args.window)
