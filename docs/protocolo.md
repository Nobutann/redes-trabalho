# Especificação do Protocolo — *(nome a definir pelo grupo)*

> Documento vivo: evolui a cada checkpoint. No CP2 o protocolo deve estar
> **integralmente definido**. As marcações ⚠️ indicam decisões pendentes do grupo.

## 1. Visão geral e decisões de projeto

| Decisão | Escolha | Justificativa |
|---|---|---|
| Transporte (socket) | **UDP** (`SOCK_DGRAM`) | Em UDP, a confiabilidade é 100% responsabilidade do nosso protocolo — alinha com o objetivo do trabalho |
| Porta padrão | **50000** (configurável via `--port`) | Porta definida como padrão no servidor e cliente para comunicação local ou em rede |
| Byte order | **big-endian** (network byte order) | Padrão da Internet; todos os campos multi-byte usam o prefixo `!` do módulo `struct` |
| Modo de operação | individual (`0`) vs. lote (`1`) | Negociado no handshake via campo `MODE` do pacote `HELLO` |
| Estratégia de confirmação | Go-Back-N (`0`) vs. Repetição Seletiva (`1`) | Escolha enviada pelo cliente no campo `STRATEGY` do pacote `HELLO` (ignorado se individual) |
| Tamanho do payload | 4 caracteres (fixo, exigência do trabalho) | Escopo dos checkpoints de transferência (CP2 e CP3) |
| Tamanho máximo do texto | ≥ 30 caracteres (padrão 30) | Definido dinamicamente pelo cliente no campo `MAX_TEXT` do pacote `HELLO` |
| Janela de recepção | 1 a 5, determinada pelo servidor | Enviada no campo `WINDOW` do `HELLO_ACK`; fixada em `5` para o Checkpoint 1 |
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

| Campo | Tamanho | Formato `struct` | Valores |
|---|---|---|---|
| MAGIC    | 1 byte  | `!B` | `0xAA` |
| TYPE     | 1 byte  | `!B` | `0x01` (HELLO) |
| MODE     | 1 byte  | `!B` | `0` = individual · `1` = lote |
| STRATEGY | 1 byte  | `!B` | `0` = Go-Back-N · `1` = Repetição Seletiva (ignorado se MODE = individual, mas sempre presente) |
| MAX_TEXT | 2 bytes | `!H` (unsigned short) | Comprimento máximo total do texto (mínimo 30) |
| RESERVED | 1 byte  | `!B` | `0x00` (reservado para expansões futuras) |

#### HELLO_ACK (servidor → cliente) — 3 bytes

```
+--------+--------+--------+
| MAGIC  | TYPE   | WINDOW |
| 1 byte | 1 byte | 1 byte |
+--------+--------+--------+
  0xAA    0x02
```

| Campo | Tamanho | Formato `struct` | Valores |
|---|---|---|---|
| MAGIC  | 1 byte | `!B` | `0xAA` |
| TYPE   | 1 byte | `!B` | `0x02` (HELLO_ACK) |
| WINDOW | 1 byte | `!B` | Tamanho da janela escolhido pelo servidor (1–5; fixado em `5` no CP1) |

#### READY (cliente → servidor) — 2 bytes

```
+--------+--------+
| MAGIC  | TYPE   |
| 1 byte | 1 byte |
+--------+--------+
  0xAA    0x03
```

| Campo | Tamanho | Formato `struct` | Valores |
|---|---|---|---|
| MAGIC | 1 byte | `!B` | `0xAA` |
| TYPE  | 1 byte | `!B` | `0x03` (READY) |

Sem corpo de dados — confirma ao servidor a recepção da janela e encerra o handshake.

### 2.2.1 Parâmetros operacionais e tratamento de exceções (CP1)

- **Porta UDP padrão:** `50000` (`DEFAULT_PORT = 50000`).
- **Buffer de recepção de datagramas:** `1024` bytes (`_BUFSIZE = 1024`).
- **Timeout no cliente:** `5.0` segundos (`_TIMEOUT = 5.0`).
- **Validação de integridade e descarte:**
  - `parse_packet(data)` valida o tamanho mínimo (≥ 2 bytes) e o identificador `MAGIC == 0xAA`. Se o byte mágico diferir, levanta `InvalidPacketError`.
  - Se o tipo for desconhecido, o pacote for mais curto que o corpo esperado ou os campos violarem os limites (`MAX_TEXT < 30` ou `WINDOW` fora de `[1, 5]`), levanta `ValueError`.
  - **No servidor:** erros de decodificação geram mensagens de aviso no console (`WARNING: malformed packet from ...`) e o pacote é descartado sem interromper a execução do serviço.
  - **No cliente:** erros de decodificação, recepção de pacote com tipo divergente de `HELLO_ACK` ou esgotamento do temporizador de 5 segundos abortam o processo com código de retorno 1 (`sys.exit(1)`).
- **Filtragem de endereço no servidor:**
  - Durante a espera pelo pacote `READY`, o servidor valida a tupla de endereço de origem `(ip, port)`. Datagramas recebidos de qualquer endereço que não seja o do cliente que iniciou o `HELLO` são descartados com log de aviso, evitando poluição de estado entre sessões concorrentes.

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

Trocas realizadas no início da comunicação para estabelecer os parâmetros da sessão: **modo de operação** (`individual` ou `batch`), **estratégia de recuperação** (`gbn` ou `sr`), **tamanho máximo do texto** (`max_text ≥ 30`) e **tamanho da janela** (`window ∈ [1, 5]`).

### Diagrama de sequência implementado

```
CLIENTE (porta efêmera)                                       SERVIDOR (0.0.0.0:50000)
   |                                                                     |
   |  1. HELLO [7 bytes]                                                 |
   |     MAGIC(0xAA) | TYPE(0x01) | MODE | STRATEGY | MAX_TEXT | 0x00    |
   |  ---------------------------------------------------------------->  |
   |  (envia via UDP e inicia timeout de 5s)                             | (recebe via recvfrom, valida MAGIC,
   |                                                                     |  decodifica campos e endereço do cliente)
   |                                                                     |
   |  2. HELLO_ACK [3 bytes]                                             |
   |     MAGIC(0xAA) | TYPE(0x02) | WINDOW (5)                           |
   |  <----------------------------------------------------------------  |
   |  (recebe dentro do timeout de 5s, valida janela)                    | (envia ACK e aguarda READY do mesmo addr)
   |                                                                     |
   |  3. READY [2 bytes]                                                 |
   |     MAGIC(0xAA) | TYPE(0x03)                                        |
   |  ---------------------------------------------------------------->  |
   |  (handshake concluído no cliente)                                   | (recebe do mesmo addr, valida tipo READY;
   |                                                                     |  imprime resumo da sessão negociada;
   |                                                                     |  retorna ao loop para novo HELLO)
```

### Etapas detalhadas do fluxo

1. **Envio do `HELLO`:**
   - O cliente empacota os parâmetros selecionados via argumentos de linha de comando (`mode`, `strategy`, `max_text`) em um pacote `HELLO` de 7 bytes.
   - O cliente envia o datagrama para o endereço e porta do servidor (`--host`, `--port`) e aguarda a resposta sob um temporizador de 5,0 segundos.
2. **Processamento do `HELLO` e resposta com `HELLO_ACK`:**
   - O servidor recebe o datagrama e valida a integridade com `parse_packet`.
   - Se for um pacote válido do tipo `HELLO`, o servidor extrai e exibe os metadados acordados (modo, estratégia e tamanho máximo do texto).
   - O servidor monta um pacote `HELLO_ACK` de 3 bytes com `window = 5` e envia de volta ao endereço do cliente.
   - O servidor entra no estado de espera por confirmação (`_await_ready`), bloqueando para receber dados exclusivamente do mesmo endereço de origem.
3. **Recepção do `HELLO_ACK` e envio do `READY`:**
   - O cliente recebe o pacote antes do tempo limite, valida o tipo `HELLO_ACK` e obtém o tamanho da janela aceito pelo servidor.
   - O cliente envia o pacote `READY` de 2 bytes confirmando a sincronização e registra localmente o handshake como concluído.
4. **Finalização do Handshake no Servidor:**
   - O servidor recebe o pacote `READY` vindo do cliente esperado, imprime a confirmação de handshake completo com todos os parâmetros negociados e retorna ao laço principal para atender novas conexões.

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
