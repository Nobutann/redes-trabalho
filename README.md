# Trabalho I — Transporte Confiável na Camada de Aplicação

Aplicação cliente-servidor que fornece, na **camada de aplicação**, um transporte
confiável de dados sobre um canal com perdas e erros, por meio de um protocolo
próprio, construído sobre sockets. O cliente envia textos que são fragmentados em
pacotes de até 4 caracteres de payload, com cabeçalhos próprios (checksum, flags,
número de sequência), e o servidor os recompõe e confirma a recepção.

**Status:** 🔨 em desenvolvimento — Checkpoint 1 (handshake) em andamento.

**Linguagem:** Python 3.

## Documentação

| Documento | Conteúdo |
|---|---|
| [`docs/requisitos.md`](docs/requisitos.md) | Requisitos funcionais do sistema |
| [`docs/protocolo.md`](docs/protocolo.md) | Especificação do protocolo (design do projeto) |

## Roadmap

| Marco | Data | Status | Escopo |
|---|---|---|---|
| Milestone 1 — Handshake & Sockets | 09/09/2026 | 🔨 em andamento | Conexão via socket e handshake inicial (modo de operação, tamanho máximo do texto, tamanho da janela) |
| Milestone 2 — Protocolo sem erros | 21/10/2026 | ⏳ pendente | Transferência completa funcionando em canal sem perdas/erros |
| Milestone 3 — Erros e perdas | 23/11/2026 | ⏳ pendente | Simulação determinística de erros/perdas, retransmissão, GBN e Repetição Seletiva |

## Estrutura

```
redes-trabalho/
├── README.md
├── docs/
│   ├── requisitos.md
│   ├── protocolo.md
│   └── ia-log.md
└── src/
    ├── protocol.py   ✅ implementado (CP1)
    ├── client.py     ⏳ pendente
    └── server.py     ⏳ pendente
```

## Como executar

### Verificar o módulo de protocolo (`protocol.py`)

O módulo pode ser exercitado de forma autônoma — sem necessidade de servidor
ou cliente em execução — de duas maneiras:

**1. Bloco `__main__` (testes de ida e volta + validações):**

```bash
python src/protocol.py
```

Saída esperada: seis verificações passando, incluindo três round-trips
(HELLO, HELLO_ACK, READY) e três casos de erro validados.

**2. Importação interativa no REPL do Python:**

```python
from src.protocol import build_hello, build_hello_ack, build_ready, parse_packet
from src.protocol import Mode, Strategy

# Construir e inspecionar um pacote HELLO
raw = build_hello(Mode.BATCH, Strategy.SR, max_text=50)
print(raw.hex(" ").upper())   # AA 01 01 01 00 32 00

# Parsear de volta
print(parse_packet(raw))
```

> `client.py` e `server.py` serão documentados aqui quando implementados
> (Milestone 1).
