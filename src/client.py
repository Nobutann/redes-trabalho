"""Cliente UDP com handshake, transferência confiável e simulação de falhas."""

import argparse
import socket
import sys
from time import monotonic

from cipher import encrypt
from faults import FaultInjector, parse_fault_rules
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
MAX_RETRANSMISSIONS = 3


def run_client(
    host: str,
    port: int,
    mode: Mode,
    strategy: Strategy,
    max_text: int,
    text: str | None = None,
    faults: FaultInjector | None = None,
    key: int | None = None,
) -> None:
    hello = build_hello(mode, strategy, max_text)
    data_packets = None
    if text is not None:
        sent_text = encrypt(text, key) if key is not None else text
        data_packets = prepare_data_packets(sent_text, max_text)
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
            if key is not None:
                print(f"[CLIENT] Texto cifrado com César (chave={key}): {sent_text}")
            batch = mode is Mode.BATCH
            sender = ReliableSender(
                sock,
                server_addr,
                data_packets,
                window=window if batch else 1,
                cumulative=batch and strategy is Strategy.GBN,
                faults=faults or FaultInjector(),
            )
            sender.run()


class ReliableSender:
    """Envia DATA com janela deslizante e retransmissão por timeout ou NAK.

    Com ``cumulative`` verdadeiro, segue Go-Back-N: ACKs cumulativos e um único temporizador
    para a base. Caso contrário, segue Repetição Seletiva, com um temporizador por pacote.
    O modo individual equivale à Repetição Seletiva com janela 1.
    """

    def __init__(
        self,
        sock: socket.socket,
        server_addr: tuple[str, int],
        packets: list[bytes],
        window: int,
        cumulative: bool,
        faults: FaultInjector,
    ):
        self.sock = sock
        self.server_addr = server_addr
        self.packets = packets
        self.window = window
        self.cumulative = cumulative
        self.faults = faults
        self.base = 0
        self.next_seq = 0
        self.acked = set()
        self.attempts = [0] * len(packets)
        self.timers = {}
        self.nak_answered = set()

    def run(self) -> None:
        while self.base < len(self.packets):
            self.fill_window()
            try:
                pkt = receive_reply(self.sock, self.server_addr, min(self.timers.values()), self.faults)
            except TimeoutError:
                self.on_timeout()
                continue
            if pkt is None:
                continue
            if pkt["type"] is PacketType.ACK:
                self.on_ack(pkt["seq"])
            else:
                self.on_nak(pkt["seq"])
        print("[CLIENT] Transferência concluída: todos os fragmentos confirmados")

    def fill_window(self) -> None:
        while self.next_seq < min(self.base + self.window, len(self.packets)):
            self.transmit(self.next_seq)
            self.next_seq += 1
            if self.cumulative and not self.timers:
                self.restart_base_timer()

    def transmit(self, seq: int, reason: str | None = None) -> None:
        if self.attempts[seq] > MAX_RETRANSMISSIONS:
            print(f"[CLIENT] Falha: DATA {seq} sem confirmação após {MAX_RETRANSMISSIONS} retransmissões")
            sys.exit(1)
        self.attempts[seq] += 1
        action = "enviado" if reason is None else f"retransmitido por {reason}"
        print(f"[CLIENT] DATA {action} (seq={seq}, tentativa={self.attempts[seq]})")

        packet = self.faults.apply(PacketType.DATA, seq, self.packets[seq])
        if packet is not None:
            self.sock.sendto(packet, self.server_addr)
        if not self.cumulative:
            self.timers[seq] = monotonic() + TIMEOUT

    def restart_base_timer(self) -> None:
        self.timers = {self.base: monotonic() + TIMEOUT}

    def resend_window(self, reason: str) -> None:
        for seq in range(self.base, self.next_seq):
            self.transmit(seq, reason)
        self.restart_base_timer()

    def on_timeout(self) -> None:
        now = monotonic()
        expired = sorted(seq for seq, deadline in self.timers.items() if deadline <= now)
        if expired and self.cumulative:
            print(f"[CLIENT] Timeout da base {self.base}")
            self.nak_answered.clear()
            self.resend_window("timeout")
            return

        for seq in expired:
            print(f"[CLIENT] Timeout de DATA {seq}")
            self.nak_answered.discard(seq)
            self.transmit(seq, "timeout")

    def on_ack(self, seq: int) -> None:
        if not (self.base <= seq < self.next_seq) or seq in self.acked:
            print(f"[CLIENT] ACK {seq} sem nova confirmação ignorado")
            return

        if self.cumulative:
            self.base = seq + 1
            self.nak_answered.clear()
            if self.base < self.next_seq:
                self.restart_base_timer()
            else:
                self.timers.clear()
        else:
            self.acked.add(seq)
            del self.timers[seq]
            self.nak_answered.discard(seq)
            if seq != self.base:
                return
            while self.base in self.acked:
                self.acked.remove(self.base)
                self.base += 1
        print(f"[CLIENT] Janela avançou (base={self.base}, window={self.window})")

    def on_nak(self, seq: int) -> None:
        if not (self.base <= seq < self.next_seq) or seq in self.acked:
            print(f"[CLIENT] NAK {seq} fora das sequências pendentes ignorado")
            return

        # Em GBN o reenvio sempre parte da base, então um NAK atendido vale para ela.
        answered = self.base if self.cumulative else seq
        if answered in self.nak_answered:
            print(f"[CLIENT] NAK {seq} ignorado: reenvio já realizado, aguardando resposta")
            return
        self.nak_answered.add(answered)

        if self.cumulative:
            self.resend_window("NAK")
        else:
            self.transmit(seq, "NAK")


def receive_reply(
    sock: socket.socket,
    server_addr: tuple[str, int],
    deadline: float,
    faults: FaultInjector,
) -> dict | None:
    """Aguarda um ACK ou NAK válido até o prazo; retorna None para respostas descartadas."""
    # Com prazo vencido, a leitura não bloqueia e processa respostas que já chegaram.
    sock.settimeout(max(deadline - monotonic(), 0))
    try:
        data, addr = sock.recvfrom(BUFSIZE)
    except BlockingIOError:
        raise TimeoutError from None

    if addr != server_addr:
        print(f"[CLIENT] Pacote de endereço inesperado {addr} ignorado")
        return None
    try:
        pkt = parse_packet(data)
    except ValueError as exc:
        print(f"[CLIENT] Pacote descartado: {exc}")
        return None
    if pkt["type"] not in (PacketType.ACK, PacketType.NAK):
        print(f"[CLIENT] Esperado ACK ou NAK, recebido {pkt['type'].name}")
        return None

    data = faults.apply(pkt["type"], pkt["seq"], data)
    if data is None:
        return None
    try:
        pkt = parse_packet(data)
    except ValueError as exc:
        print(f"[CLIENT] Pacote descartado: {exc}")
        return None
    print(f"[CLIENT] {pkt['type'].name} recebido (seq={pkt['seq']}, checksum=0x{pkt['checksum']:04X})")
    return pkt


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
    parser.add_argument(
        "--fault",
        action="append",
        default=[],
        metavar="TIPO:SEQ:OCORRÊNCIA:AÇÃO",
        help="Falha simulada, como DATA:1:1:perder ou ACK:2:1:corromper; pode ser repetida",
    )
    parser.add_argument(
        "--key",
        type=int,
        choices=range(1, 26),
        metavar="1-25",
        help="Chave da cifra de César; deve ser a mesma configurada no servidor",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    mode = Mode.INDIVIDUAL if args.mode == "individual" else Mode.BATCH
    strategy = Strategy.GBN if args.strategy == "gbn" else Strategy.SR

    try:
        faults = FaultInjector(parse_fault_rules(args.fault))
        run_client(args.host, args.port, mode, strategy, args.max_text, args.text, faults, args.key)
    except ValueError as exc:
        print(f"[CLIENT] Erro: {exc}")
        sys.exit(1)
