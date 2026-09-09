# Especificação do Protocolo

> Documento de referência do protocolo. Atualizado a cada checkpoint.

## 1. Visão Geral e Parâmetros

| Parâmetro | Valor | Detalhes |
|---|---|---|
| Transporte | UDP (`SOCK_DGRAM`) | Confiabilidade implementada na camada de aplicação |
| Porta padrão | 50000 | Configurável via `--port` |
| Byte order | Big-endian | Padrão de rede (network byte order) |
| Modo de operação | `0` (Individual), `1` (Batch) | Definido no campo `MODE` do `HELLO` |
| Estratégia de retransmissão | `0` (Go-Back-N), `1` (Repetição Seletiva) | Definido no campo `STRATEGY` do `HELLO` |
| Payload máximo | 4 caracteres | Aplicado nos pacotes de dados (CP2/CP3) |
| Tamanho máx. de texto | Mínimo 30 bytes | Definido no campo `MAX_TEXT` do `HELLO` |
| Janela de recepção | 1 a 5 (fixada em 5 no CP1) | Enviada pelo servidor no `HELLO_ACK` |
| Buffer do socket | 1024 bytes | Constante `BUFSIZE` |
| Timeout do cliente | 5.0 segundos | Constante `TIMEOUT` |

---

## 2. Formato dos Pacotes

### 2.1 Cabeçalho Comum

Presente em todos os pacotes:

```
+--------+--------+
| MAGIC  | TYPE   |
| 1 byte | 1 byte |
+--------+--------+
```

- **MAGIC** (`0xAA`): Identificador do protocolo.
- **TYPE**: `0x01` (HELLO), `0x02` (HELLO_ACK), `0x03` (READY).

---

### 2.2 Pacotes de Handshake (CP1)

#### HELLO (Cliente -> Servidor) — 7 bytes

```
+--------+--------+--------+----------+----------+----------+
| MAGIC  | TYPE   | MODE   | STRATEGY | MAX_TEXT | RESERVED |
| 1 byte | 1 byte | 1 byte | 1 byte   | 2 bytes  | 1 byte   |
+--------+--------+--------+----------+----------+----------+
```

| Campo | Tamanho | Codificação | Descrição |
|---|---|---|---|
| MAGIC | 1 byte | unsigned int | `0xAA` |
| TYPE | 1 byte | unsigned int | `0x01` |
| MODE | 1 byte | unsigned int | `0` = Individual, `1` = Batch |
| STRATEGY | 1 byte | unsigned int | `0` = Go-Back-N, `1` = Repetição Seletiva |
| MAX_TEXT | 2 bytes | unsigned int, big-endian | Tamanho máximo da mensagem (mínimo 30) |
| RESERVED | 1 byte | unsigned int | `0x00` (reservado) |

#### HELLO_ACK (Servidor -> Cliente) — 3 bytes

```
+--------+--------+--------+
| MAGIC  | TYPE   | WINDOW |
| 1 byte | 1 byte | 1 byte |
+--------+--------+--------+
```

| Campo | Tamanho | Codificação | Descrição |
|---|---|---|---|
| MAGIC | 1 byte | unsigned int | `0xAA` |
| TYPE | 1 byte | unsigned int | `0x02` |
| WINDOW | 1 byte | unsigned int | Tamanho da janela (1 a 5; fixo em 5 no CP1) |

#### READY (Cliente -> Servidor) — 2 bytes

```
+--------+--------+
| MAGIC  | TYPE   |
| 1 byte | 1 byte |
+--------+--------+
```

Apenas o cabeçalho comum (`MAGIC = 0xAA`, `TYPE = 0x03`). Confirma que o cliente recebeu a janela e conclui o handshake.

---

## 3. Fluxo do Handshake (CP1)

```
CLIENTE                                                      SERVIDOR
   |                                                            |
   |  1. HELLO [7 bytes]                                        |
   |     MAGIC(0xAA) | 0x01 | MODE | STRATEGY | MAX_TEXT | 0x00 |
   |  --------------------------------------------------------> |
   |  (envia e aguarda resposta por até 5s)                     | (valida MAGIC e campos,
   |                                                            |  registra endereço do cliente)
   |                                                            |
   |  2. HELLO_ACK [3 bytes]                                    |
   |     MAGIC(0xAA) | 0x02 | WINDOW(5)                         |
   |  <-------------------------------------------------------- |
   |  (recebe janela, confirma parâmetros)                      | (aguarda READY da mesma origem)
   |                                                            |
   |  3. READY [2 bytes]                                        |
   |     MAGIC(0xAA) | 0x03                                     |
   |  --------------------------------------------------------> |
   |  (handshake pronto)                                        | (handshake concluído;
   |                                                            |  retorna a aguardar novas sessões)
```

### Regras de Validação e Descarte:
- Pacotes com byte `MAGIC != 0xAA` lançam `InvalidPacketError` e são descartados no servidor com aviso no terminal.
- `MAX_TEXT < 30` ou `WINDOW` fora de `[1, 5]` são rejeitados com `ValueError`.
- Se o servidor receber pacotes de um endereço diferente enquanto aguarda o `READY`, o pacote é ignorado.
- Se o cliente não obtiver resposta em até 5 segundos, a execução é abortada.

---

## 4. Pacotes de Dados e Confirmação (CP2/CP3 — Planejado)

> Esboço para as próximas etapas:

```
+--------+--------+---------+-----------+--------------------+
| MAGIC  | SEQ    | FLAGS   | CHECKSUM  | PAYLOAD (4 bytes)  |
| 1 byte | 1 byte | 1 byte  | 2 bytes   | 4 bytes            |
+--------+--------+---------+-----------+--------------------+
```

- **SEQ**: Número de sequência do fragmento.
- **FLAGS**: Indicadores de controle (dados, fim de transmissão, etc.).
- **CHECKSUM**: Verificação de integridade calculada pelo remetente.
- **PAYLOAD**: Fragmento de até 4 caracteres da mensagem.
