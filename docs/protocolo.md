# Especificação do Protocolo — *(nome a definir pelo grupo)*

> Documento vivo: evolui a cada checkpoint. No CP2 o protocolo deve estar
> **integralmente definido**. As marcações ⚠️ indicam decisões pendentes do grupo.

## 1. Visão geral e decisões de projeto

| Decisão | Escolha | Justificativa |
|---|---|---|
| Transporte (socket) | **UDP** (`SOCK_DGRAM`) | Em UDP, a confiabilidade é 100% responsabilidade do nosso protocolo — alinha com o objetivo do trabalho |
| Byte order | **big-endian** (network byte order) | Padrão da Internet; todos os campos multi-byte usam o prefixo `!` do módulo `struct` |
| Modo de operação | individual vs. lote (negociado no handshake) | — |
| Estratégia de confirmação | Go-Back-N vs. Repetição Seletiva (escolha do cliente) | — |
| Tamanho do payload | 4 caracteres (fixo, exigência do trabalho) | — |
| Tamanho máximo do texto | ≥ 30 caracteres, definido dinamicamente no início | — |
| Janela | 1 a 5, determinada pelo servidor; inicial 5 | — |
| Checksum | ⚠️ algoritmo a definir (ex.: soma de complemento-um, CRC16 — implementado à mão para ponto extra) | — |
| Criptografia (extra) | ⚠️ opcional (ex.: Cifra de César implementada à mão) | Pontos extra avaliados só na última entrega |

## 2. Formato dos pacotes

### 2.1 Cabeçalho comum (presente em todos os pacotes)

```
+--------+--------+
| MAGIC  | TYPE   |
| 1 byte | 1 byte |
+--------+--------+
```

| Campo | Tamanho | Valores |
|---|---|---|
| MAGIC | 1 byte | `0xAA` — identifica pacotes deste protocolo |
| TYPE  | 1 byte | `0x01` HELLO · `0x02` HELLO_ACK · `0x03` READY |

### 2.2 Pacotes de handshake (Checkpoint 1 — implementados)

#### HELLO (cliente → servidor) — 7 bytes

```
+--------+--------+--------+----------+----------+----------+
| MAGIC  | TYPE   | MODE   | STRATEGY | MAX_TEXT | RESERVED |
| 1 byte | 1 byte | 1 byte | 1 byte   | 2 bytes  | 1 byte   |
+--------+--------+--------+----------+----------+----------+
  0xAA    0x01
```

| Campo | Tamanho | Valores |
|---|---|---|
| MODE     | 1 byte  | `0` = individual · `1` = lote |
| STRATEGY | 1 byte  | `0` = Go-Back-N · `1` = Repetição Seletiva (ignorado se MODE = individual, mas sempre presente) |
| MAX_TEXT | 2 bytes (unsigned short, big-endian) | Comprimento máximo total do texto (mínimo 30) |
| RESERVED | 1 byte  | `0x00` (reservado para uso futuro) |

#### HELLO_ACK (servidor → cliente) — 3 bytes

```
+--------+--------+--------+
| MAGIC  | TYPE   | WINDOW |
| 1 byte | 1 byte | 1 byte |
+--------+--------+--------+
  0xAA    0x02
```

| Campo | Tamanho | Valores |
|---|---|---|
| WINDOW | 1 byte | Tamanho da janela escolhido pelo servidor (1–5) |

#### READY (cliente → servidor) — 2 bytes

```
+--------+--------+
| MAGIC  | TYPE   |
| 1 byte | 1 byte |
+--------+--------+
  0xAA    0x03
```

Sem corpo — confirma que o handshake foi concluído pelo lado do cliente.

### 2.3 Pacotes de dados (Checkpoint 2 — pendente)

> ⚠️ Formato a definir. Esboço inicial:

```
+--------+--------+---------+-----------+--------------------+
| MAGIC  | SEQ    | FLAGS   | CHECKSUM  | PAYLOAD (4 chars)  |
| 1 byte | 1 byte | 1 byte  | 2 bytes   | 4 bytes            |
+--------+--------+---------+-----------+--------------------+
```

- **SEQ:** número de sequência (faixa: ⚠️ a definir)
- **FLAGS:** bitmask de controle (DATA / ACK / NAK / FIN / EOT — ⚠️ a definir)
- **CHECKSUM:** cobre cabeçalho + payload (⚠️ algoritmo a definir)

### 2.4 Pacote de confirmação (Checkpoint 2 — pendente)

> ⚠️ Formato a definir. Semântica do ACK# difere entre GBN (cumulativo) e SR
> (individual) — a detalhar por estratégia.

## 3. Handshake (Checkpoint 1 — implementado)

Trocas realizadas na conexão: **modo de operação**, **tamanho máximo do texto** e
**tamanho da janela**.

```
CLIENTE                                SERVIDOR
   |  --- HELLO { mode, strategy,  -->  |
   |             max_text }             |
   |  <-- HELLO_ACK { window } ------   |   (window ∈ [1, 5], definido pelo servidor)
   |  --- READY ----------------------> |
   |          (handshake concluído)     |
```

- O **cliente** envia HELLO informando o modo de operação, a estratégia de
  confirmação e o comprimento máximo do texto (≥ 30, padrão 30).
- O **servidor** responde com HELLO_ACK informando o tamanho da janela (1–5).
- O **cliente** confirma com READY, encerrando o handshake.

## 4. Fluxo de transferência (Checkpoint 2 — caminho sem erros)

> ⚠️ A preencher conforme implementação. Pontos a descrever:

1. Fragmentação do texto em pacotes de até 4 caracteres
2. Envio conforme a janela (paralelismo de até `N` mensagens por vez)
3. Confirmações: individuais (SR) ou em grupo (GBN)
4. Encerramento da comunicação (flag EOT/FIN) e apresentação da mensagem completa
   no servidor
5. Formato dos metadados impressos:
   - **Servidor:** por pacote recebido (SEQ, checksum OK, payload, timestamp…)
   - **Cliente:** por confirmação recebida (ACK#, flags, timestamp…)

## 5. Tratamento de erros e perdas (Checkpoint 3)

> ⚠️ A preencher. Pontos a especificar:

- **Simulação de falhas (cliente, determinística):** regras de injeção
  - ⚠️ Proposta: lista de "eventos" configurados antes do envio, ex.:
    `corromper(seq=2)` (altera payload/checksum) e `descartar(seq=4)` (não envia)
- **Detecção pelo servidor:** checksum inválido → NAK/descarte; SEQ fora de
  ordem → tratamento conforme GBN/SR
- **Temporizador (cliente):** valor do timeout, o que retransmitir
  - GBN: retransmitir a janela inteira a partir do pacote não confirmado
  - SR: retransmitir apenas o pacote sem confirmação individual
- **Reconhecimento negativo (NAK):** quando o servidor envia e como o cliente reage

## 6. Máquinas de estado (FSM)

> ⚠️ Descrever (e diagramar) nos moldes da Figura 3.15–3.18 do livro Kurose:
> estados do **remetente** (cliente) e do **destinatário** (servidor) para cada
> estratégia (GBN e SR).

## 7. Mensagens de exemplo

### 7.1 Handshake completo (Checkpoint 1)

Exemplo com modo lote, Repetição Seletiva e `max_text = 100`:

| Mensagem   | Bytes (hex)           | Tamanho |
|---|---|---|
| HELLO      | `AA 01 01 01 00 64 00` | 7 bytes |
| HELLO_ACK  | `AA 02 05`             | 3 bytes |
| READY      | `AA 03`                | 2 bytes |

Decodificação do HELLO (`AA 01 01 01 00 64 00`):
- `AA` → MAGIC
- `01` → TYPE = HELLO
- `01` → MODE = BATCH
- `01` → STRATEGY = SR
- `00 64` → MAX_TEXT = 100 (big-endian)
- `00` → RESERVED

### 7.2 Pacotes de dados (Checkpoint 2)

> ⚠️ Exemplos serão adicionados quando o formato de dados for fixado.
