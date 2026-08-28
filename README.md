# Trabalho I — Transporte Confiável na Camada de Aplicação

Aplicação cliente-servidor que fornece, na **camada de aplicação**, um transporte
confiável de dados sobre um canal com perdas e erros, por meio de um protocolo
próprio, construído sobre sockets. O cliente envia textos que são fragmentados em
pacotes de até 4 caracteres de payload, com cabeçalhos próprios (checksum, flags,
número de sequência), e o servidor os recompõe e confirma a recepção.

**Status:** 🚧 não iniciado — em fase de planejamento.

**Linguagem planejada:** Python (decisão revisável).

## Documentação

| Documento | Conteúdo |
|---|---|
| [`docs/requisitos.md`](docs/requisitos.md) | Requisitos funcionais do sistema |
| [`docs/protocolo.md`](docs/protocolo.md) | Especificação do protocolo (design do projeto) |

## Roadmap

| Marco | Data | Escopo |
|---|---|---|
| Milestone 1 — Handshake & Sockets | 09/09/2026 | Conexão via socket e handshake inicial (modo de operação, tamanho máximo do texto, tamanho da janela) |
| Milestone 2 — Protocolo sem erros | 21/10/2026 | Transferência completa funcionando em canal sem perdas/erros |
| Milestone 3 — Erros e perdas | 23/11/2026 | Simulação determinística de erros/perdas, retransmissão, GBN e Repetição Seletiva |

## Estrutura (planejada)

```
redes-trabalho/
├── README.md
├── docs/
│   ├── requisitos.md
│   └── protocolo.md
└── src/
    ├── client.py
    ├── server.py
    └── protocol.py
```

## Como executar

> Será preenchido quando houver a primeira versão executável (Milestone 1).
