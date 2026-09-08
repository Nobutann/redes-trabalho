# Trabalho I — Transporte Confiável na Camada de Aplicação

Implementação de um protocolo de transporte confiável sobre UDP na camada de aplicação, desenvolvido para a disciplina de Infraestrutura de Comunicação.

O sistema fragmenta textos em mensagens com payload de até 4 bytes, adiciona cabeçalhos próprios (número de sequência, flags, checksum) e implementa confirmações e retransmissões (Go-Back-N e Repetição Seletiva).

**Status:** Checkpoint 1 concluído (Handshake UDP de 3 vias).

---

## Roadmap

| Marco | Data | Status | Escopo |
|---|---|---|---|
| Checkpoint 1 — Handshake & Sockets | 09/09/2026 | Concluído | Conexão UDP e handshake de 3 vias (modo, estratégia, tamanho máximo e janela) |
| Checkpoint 2 — Protocolo sem erros | 21/10/2026 | Pendente | Transferência completa de dados em canal sem perdas |
| Checkpoint 3 — Erros e perdas | 23/11/2026 | Pendente | Simulação determinística de falhas, temporizadores, Go-Back-N e Repetição Seletiva |

---

## Estrutura do Projeto

```
redes-trabalho/
├── README.md
├── docs/
│   ├── requisitos.md          # Especificação de requisitos do trabalho
│   ├── protocolo.md           # Formato dos pacotes e fluxo de comunicação
│   └── exemplo-handshake.txt  # Exemplo de saída do handshake
└── src/
    ├── protocol.py            # Constantes, tipos e empacotamento com struct
    ├── server.py              # Servidor UDP e loop de handshake
    └── client.py              # Cliente UDP e interface CLI
```

---

## Como Executar

O projeto requer apenas Python 3 (versão 3.10 ou superior), sem dependências adicionais.

### 1. Iniciar o Servidor

No primeiro terminal:

```bash
python src/server.py
```

Por padrão, o servidor aguarda conexões em `0.0.0.0:50000`. Para indicar outra porta:

```bash
python src/server.py --port 50001
```

### 2. Executar o Cliente

No segundo terminal, execute o cliente com os parâmetros desejados:

```bash
# Modo individual (padrão)
python src/client.py --mode individual

# Modo lote com Go-Back-N
python src/client.py --mode batch --strategy gbn

# Modo lote com Repetição Seletiva e max_text customizado
python src/client.py --mode batch --strategy sr --max-text 100
```

#### Parâmetros disponíveis (`client.py`):

- `--host`: IP do servidor (padrão: `127.0.0.1`)
- `--port`: Porta UDP do servidor (padrão: `50000`)
- `--mode`: Modo de transferência — `individual` ou `batch` (padrão: `individual`)
- `--strategy`: Estratégia de retransmissão — `gbn` ou `sr` (padrão: `gbn`)
- `--max-text`: Tamanho máximo do texto em bytes, mínimo 30 (padrão: `30`)

---

## Exemplo de Saída

Execução com `python src/client.py --mode batch --strategy gbn`:

**Cliente:**
```
[CLIENT] HELLO enviado para 127.0.0.1:50000
  modo: BATCH, estratégia: GBN, max_text: 30
[CLIENT] HELLO_ACK recebido (window=5)
[CLIENT] Handshake concluído com 127.0.0.1:50000
  modo: BATCH, estratégia: GBN, max_text: 30, window: 5
```

**Servidor:**
```
[SERVER] Ouvindo em 0.0.0.0:50000
[SERVER] HELLO recebido de 127.0.0.1:60137
  modo: BATCH, estratégia: GBN, max_text: 30
[SERVER] HELLO_ACK enviado (window=5)
[SERVER] Handshake concluído com 127.0.0.1:60137
  modo: BATCH, estratégia: GBN, max_text: 30, window: 5
```

Um log completo da execução das duas pontas está em [`docs/exemplo-handshake.txt`](docs/exemplo-handshake.txt).

---

## Testes do Protocolo

Para rodar os testes de integridade e decodificação de pacotes:

```bash
python src/protocol.py
```
