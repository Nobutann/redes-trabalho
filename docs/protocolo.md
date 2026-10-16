# Especificação do protocolo

Este documento reúne as regras de comunicação entre cliente e servidor e será atualizado a cada checkpoint. A versão atual descreve o handshake implementado no CP1. O formato dos pacotes de dados ainda está em planejamento.

## 1. Visão geral e parâmetros

A comunicação usa sockets UDP. No início de cada sessão, o cliente informa o modo de operação, a estratégia e o limite do texto; o servidor responde com o tamanho da janela.

| Parâmetro | Valor | Detalhes |
|---|---|---|
| Transporte | UDP (`SOCK_DGRAM`) | O projeto implementará as regras de transporte confiável na camada de aplicação |
| Porta padrão | 50000 | Configurável via `--port` |
| Ordem dos bytes | Big-endian | Usada nos campos com mais de um byte |
| Modo de operação | `0` (Individual), `1` (Batch) | Definido no campo `MODE` do `HELLO` |
| Estratégia de retransmissão | `0` (Go-Back-N), `1` (Repetição Seletiva) | Definido no campo `STRATEGY` do `HELLO` |
| Payload máximo | 4 caracteres | Limite previsto para cada fragmento de dados, a partir do CP2 |
| Limite máximo do texto | Padrão 30 caracteres; limite configurável de pelo menos 30 | Informado no campo `MAX_TEXT` do `HELLO` |
| Janela de recepção | 1 a 5 (fixada em 5 no CP1) | Enviada pelo servidor no `HELLO_ACK` |
| Buffer do socket | 1024 bytes | Constante `BUFSIZE` |
| Timeout do cliente | 5.0 segundos | Constante `TIMEOUT` |

O mínimo de 30 se refere ao limite configurado, não ao tamanho obrigatório da mensagem. Com `MAX_TEXT = 30`, por exemplo, uma mensagem de dez caracteres está dentro do limite.

No CP1, apenas o valor desse limite é trocado no handshake. A ajuda de `--max-text` no código ainda usa a palavra "bytes"; essa descrição precisa ser ajustada na etapa de implementação do CP2, pois o enunciado define o limite em caracteres.

---

## 2. Formato dos pacotes

### 2.1 Cabeçalho comum

Todos os pacotes implementados começam com dois campos: `MAGIC`, que identifica o protocolo, e `TYPE`, que informa qual mensagem foi enviada.

```
+--------+--------+
| MAGIC  | TYPE   |
| 1 byte | 1 byte |
+--------+--------+
```

- **MAGIC** (`0xAA`): Identificador do protocolo.
- **TYPE**: `0x01` (HELLO), `0x02` (HELLO_ACK), `0x03` (READY).

---

### 2.2 Pacotes de handshake (CP1)

#### HELLO (Cliente -> Servidor) — 7 bytes

O cliente envia `HELLO` para iniciar a comunicação e informar os parâmetros que deseja usar.

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
| MAX_TEXT | 2 bytes | unsigned int, big-endian | Limite máximo da mensagem em caracteres; o limite configurado deve ser pelo menos 30 |
| RESERVED | 1 byte | unsigned int | `0x00` (reservado) |

#### HELLO_ACK (Servidor -> Cliente) — 3 bytes

O servidor responde com `HELLO_ACK`, informando o tamanho da janela. No CP1, o valor enviado é sempre 5.

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

O cliente envia `READY` para confirmar que recebeu a janela. Esse pacote contém apenas o cabeçalho comum (`MAGIC = 0xAA`, `TYPE = 0x03`) e conclui o handshake.

---

## 3. Fluxo do handshake (CP1)

O handshake tem três mensagens. Ao final, as duas pontas exibem os parâmetros acordados. Na versão do CP1, o cliente encerra a execução e o servidor volta a aguardar uma nova sessão.

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

### Validação e descarte

- Se `MAGIC` for diferente de `0xAA`, a leitura do pacote gera `InvalidPacketError`. O servidor registra um aviso e descarta o pacote.
- Valores de `MAX_TEXT` menores que 30 ou de `WINDOW` fora do intervalo de 1 a 5 geram `ValueError`.
- Enquanto espera o `READY`, o servidor aceita apenas pacotes do endereço que enviou o `HELLO`. Pacotes de outras origens são ignorados.
- Se o cliente não receber resposta em até cinco segundos, ele informa o timeout e encerra a tentativa.
- O servidor também espera até cinco segundos pelo `READY`. Se esse prazo terminar sem a mensagem esperada, ele volta a aguardar um novo `HELLO`.

Esses timeouts encerram a tentativa de handshake. Ainda não há retransmissão automática.

---

## 4. Pacotes de dados e confirmação (planejamento)

O desenho abaixo registra o esboço inicial dos pacotes de dados. Ele ainda não é um formato definitivo e não está implementado. A especificação completa será fechada no CP2, junto com o caminho de transmissão sem erros ou perdas. A recuperação de falhas será implementada no CP3.

```
+--------+--------+---------+-----------+--------------------+
| MAGIC  | SEQ    | FLAGS   | CHECKSUM  | PAYLOAD            |
| 1 byte | 1 byte | 1 byte  | 2 bytes   | tamanho variável   |
+--------+--------+---------+-----------+--------------------+
```

- **SEQ** identifica o fragmento e sua posição na mensagem.
- **FLAGS** reúne as indicações de controle previstas, como o fim da transmissão.
- **CHECKSUM** armazena o resultado do cálculo de integridade feito pelo remetente.
- **PAYLOAD** carrega um fragmento de até quatro caracteres. A quantidade de bytes depende da codificação; quatro caracteres não correspondem necessariamente a quatro bytes.

Antes da implementação, esse esboço precisa ser completado com os tipos de dados e de confirmação, preservando o cabeçalho `MAGIC + TYPE`. Também faltam fechar os tamanhos dos campos, a representação do comprimento do payload, o cálculo do checksum e as regras dos ACKs. Essas decisões serão registradas aqui na próxima etapa.
