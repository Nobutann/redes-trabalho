# Trabalho I — Transporte Confiável na Camada de Aplicação

Aplicação cliente-servidor que fornece, na **camada de aplicação**, um transporte
confiável de dados sobre um canal com perdas e erros, por meio de um protocolo
próprio, construído sobre sockets. O cliente envia textos que são fragmentados em
pacotes de até 4 caracteres de payload, com cabeçalhos próprios (checksum, flags,
número de sequência), e o servidor os recompõe e confirma a recepção.

**Status:** ✅ Checkpoint 1 concluído — Handshake fim a fim via UDP implementado e validado.

**Linguagem:** Python 3 (versão 3.10+ recomendada; testado em Python 3.14). Utiliza estritamente a biblioteca padrão (`socket`, `struct`, `argparse`, `enum`), sem necessidade de dependências externas.

## Documentação

| Documento | Conteúdo |
|---|---|
| [`docs/requisitos.md`](docs/requisitos.md) | Requisitos funcionais do sistema |
| [`docs/protocolo.md`](docs/protocolo.md) | Especificação técnica do protocolo (design detalhado) |
| [`docs/exemplo-handshake.txt`](docs/exemplo-handshake.txt) | Registro de execução real do handshake no terminal |
| [`docs/ia-log.md`](docs/ia-log.md) | Diário de interações com assistentes de IA |

## Roadmap

| Marco | Data | Status | Escopo |
|---|---|---|---|
| Milestone 1 — Handshake & Sockets | 09/09/2026 | ✅ concluído | Conexão via socket UDP e handshake inicial de 3 vias (modo de operação, estratégia, tamanho máximo do texto e janela de recepção) |
| Milestone 2 — Protocolo sem erros | 21/10/2026 | ⏳ pendente | Transferência completa de dados funcionando em canal sem perdas/erros |
| Milestone 3 — Erros e perdas | 23/11/2026 | ⏳ pendente | Simulação determinística de erros/perdas, retransmissão, Go-Back-N e Repetição Seletiva |

## Estrutura do Projeto

```
redes-trabalho/
├── README.md
├── docs/
│   ├── requisitos.md
│   ├── protocolo.md
│   ├── ia-log.md
│   └── exemplo-handshake.txt
└── src/
    ├── protocol.py   ✅ implementado (CP1)
    ├── server.py     ✅ implementado (CP1)
    └── client.py     ✅ implementado (CP1)
```

## Como executar (Manual de Uso / Runbook)

Este guia orienta a execução passo a passo do sistema de handshake em ambiente local.

### Pré-requisitos

- Python 3.10 ou superior instalado no sistema.
- Não há dependências externas (basta clonar e executar).

---

### Passo 1: Iniciar o Servidor UDP

Abra um terminal na raiz do repositório e inicie o servidor:

```bash
python src/server.py
```

Por padrão, o servidor escuta em todas as interfaces de rede (`0.0.0.0`) na porta UDP `50000`.

**Opções do servidor:**

| Flag | Tipo | Padrão | Descrição |
|---|---|---|---|
| `--port` | inteiro | `50000` | Porta UDP onde o servidor aguardará conexões |

*Exemplo com porta customizada:*
```bash
python src/server.py --port 50001
```

**Saída esperada:**
```
[SERVER] Listening on 0.0.0.0:50000
```

---

### Passo 2: Executar o Cliente UDP

Em um segundo terminal, execute o cliente passando os parâmetros desejados.

#### Parâmetros de linha de comando (`client.py`):

| Flag | Tipo / Opções | Padrão | Descrição |
|---|---|---|---|
| `--host` | string | `127.0.0.1` | Endereço IP do servidor UDP |
| `--port` | inteiro | `50000` | Porta UDP do servidor |
| `--mode` | `individual`, `batch` | `individual` | Modo de transferência |
| `--strategy` | `gbn`, `sr` | `gbn` | Estratégia de recuperação de erros (aplicável ao modo `batch`) |
| `--max-text` | inteiro (≥ 30) | `30` | Comprimento máximo do texto em bytes |

#### Exemplos de comandos para cada modo suportado:

1. **Modo Individual (envio isolado):**
   ```bash
   python src/client.py --mode individual
   ```

2. **Modo Lote com Go-Back-N (GBN):**
   ```bash
   python src/client.py --mode batch --strategy gbn
   ```

3. **Modo Lote com Repetição Seletiva (SR):**
   ```bash
   python src/client.py --mode batch --strategy sr
   ```

4. **Exemplo completo com porta e tamanho de texto customizados:**
   ```bash
   python src/client.py --host 127.0.0.1 --port 50000 --mode batch --strategy sr --max-text 100
   ```

---

### Passo 3: Saída esperada do Handshake

Ao executar o cliente (ex.: no modo lote com GBN), ambos os terminais exibirão a conclusão do handshake:

**Terminal do Cliente:**
```
[CLIENT] HELLO sent to 127.0.0.1:50000
         mode     : BATCH
         strategy : GBN
         max_text : 30
[CLIENT] HELLO_ACK received (window=5)
[CLIENT] Handshake complete
         server   : 127.0.0.1:50000
         mode     : BATCH
         strategy : GBN
         max_text : 30
         window   : 5
```

**Terminal do Servidor:**
```
[SERVER] HELLO received from 127.0.0.1:<porta_efêmera>
         mode     : BATCH
         strategy : GBN
         max_text : 30
[SERVER] HELLO_ACK sent (window=5)
[SERVER] Handshake complete
         client   : 127.0.0.1:<porta_efêmera>
         mode     : BATCH
         strategy : GBN
         max_text : 30
         window   : 5
```

> Para um exemplo completo de saída das duas pontas lado a lado, consulte o arquivo [`docs/exemplo-handshake.txt`](docs/exemplo-handshake.txt).

---

### Verificação do módulo de protocolo (`protocol.py`)

Para rodar os testes unitários internos de serialização, deserialização e validação de pacotes:

```bash
python src/protocol.py
```

Saída esperada: seis testes executados com sucesso (`All checks passed -- protocol.py is working correctly.`).

---

### Resolução de Problemas (Troubleshooting)

| Sintoma observado | Causa provável | Comportamento do código / Solução |
|---|---|---|
| `[CLIENT] ERROR: no response from <host>:<port> after 5s — aborting` | Servidor não iniciado, porta divergente ou firewall bloqueando UDP | O cliente encerra com código `1` após 5 segundos (`_TIMEOUT = 5.0`). Confirme se o servidor está ativo na mesma porta (`--port`). |
| `[CLIENT] ERROR: --max-text must be >= 30 (got X)` | Valor de `--max-text` informado é menor que 30 | O cliente valida o limite antes de abrir o socket e encerra com código `1`. Forneça um valor `--max-text >= 30`. |
| `[CLIENT] ERROR: malformed response: <exc> — aborting` | Resposta recebida pelo cliente tem tamanho incorreto ou MAGIC diferente de `0xAA` | O cliente encerra com código `1`. Verifique se não há outro serviço emitindo pacotes espúrios na mesma porta. |
| `[CLIENT] ERROR: expected HELLO_ACK, got <TYPE> — aborting` | Cliente recebeu tipo inesperado de pacote em resposta ao HELLO | O cliente aborta com código `1`. Indica que o servidor enviou um pacote fora da ordem da máquina de estados. |
| `[SERVER] WARNING: malformed packet from <addr>: <exc>` | Datagrama corrompido, truncado ou com MAGIC incorreto recebido pelo servidor | O servidor loga o aviso com a exceção, descarta o pacote e continua ouvindo (`continue`). |
| `[SERVER] WARNING: packet from unexpected address <addr>, ignoring` | Pacote recebido durante a espera por `READY` partiu de endereço/porta diferente do cliente do `HELLO` | O servidor descarta o pacote de terceiros e continua aguardando o `READY` do cliente original da sessão. |
| `[SERVER] WARNING: expected <TYPE>, got <OUTRO> — ignoring` | Pacote recebido fora da sequência esperada pelo servidor (ex.: READY antes de HELLO) | O servidor descarta o pacote, loga um aviso no console e continua no estado atual. |

