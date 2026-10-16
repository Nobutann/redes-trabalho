# Trabalho I — Transporte Confiável na Camada de Aplicação

Este projeto faz parte da disciplina de Infraestrutura de Comunicação. O objetivo é construir uma aplicação cliente-servidor que use UDP e implemente suas próprias regras de transporte confiável.

Ao longo do trabalho, a aplicação passará a dividir textos em fragmentos de até quatro caracteres, acrescentar cabeçalhos com número de sequência, indicador de último fragmento e checksum, e controlar confirmações e retransmissões com Go-Back-N e Repetição Seletiva.

**Estado atual:** Checkpoint 1 concluído. Cliente e servidor já realizam o handshake de três vias e trocam os parâmetros da comunicação. O checksum e a montagem e leitura dos pacotes `DATA` e `ACK` estão implementados e testados em `src/protocol.py`. O envio do texto ainda será implementado no Checkpoint 2.

Os formatos de `DATA` e `ACK` e o fluxo de transferência sem erros estão descritos em [`docs/protocolo.md`](docs/protocolo.md). A fragmentação, a reconstrução do texto, o envio de `DATA` e `ACK` e o controle das confirmações ainda não estão implementados. O suporte aos pacotes não conclui o CP2.

---

## Etapas do trabalho

| Marco | Data | Status | Escopo |
|---|---|---|---|
| Checkpoint 1 — Handshake & Sockets | 09/09/2026 | Concluído | Conexão UDP e handshake de 3 vias (modo, estratégia, tamanho máximo e janela) |
| Checkpoint 2 — Protocolo sem erros | 21/10/2026 | Pendente | Definição completa do protocolo e transferência de dados sem erros ou perdas |
| Checkpoint 3 — Erros e perdas | 23/11/2026 | Pendente | Simulação determinística de falhas e recuperação com temporizadores, Go-Back-N e Repetição Seletiva |

---

## Organização do projeto

```
redes-trabalho/
├── README.md
├── docs/
│   ├── requisitos.md          # Especificação de requisitos do trabalho
│   ├── protocolo.md           # Formato dos pacotes e fluxo de comunicação
│   └── exemplo-handshake.txt  # Exemplo de saída do handshake
├── src/
│   ├── protocol.py            # Constantes, tipos, checksum, montagem e leitura dos pacotes
│   ├── server.py              # Servidor UDP e loop de handshake
│   └── client.py              # Cliente UDP e interface CLI
└── tests/
    ├── test_checksum.py       # Testes do cálculo e da verificação do checksum
    └── test_packets.py        # Formatos, validação de DATA/ACK e compatibilidade do handshake
```

---

## Como executar

Para executar o projeto, basta ter Python 3.10 ou superior. Não é preciso instalar dependências adicionais.

### 1. Iniciar o servidor

Abra um terminal na pasta do projeto e inicie o servidor:

```bash
python src/server.py
```

Por padrão, o servidor escuta em `0.0.0.0:50000`. Para usar outra porta:

```bash
python src/server.py --port 50001
```

### 2. Executar o cliente

Em outro terminal, também na pasta do projeto, execute o cliente com os parâmetros desejados:

```bash
# Modo individual (padrão)
python src/client.py --mode individual

# Modo lote com Go-Back-N
python src/client.py --mode batch --strategy gbn

# Modo lote com Repetição Seletiva e limite de texto igual a 100
python src/client.py --mode batch --strategy sr --max-text 100
```

No CP1, esses comandos apenas negociam o modo e a estratégia. A transferência de dados ainda não acontece.

Parâmetros disponíveis em `client.py`:

- `--host`: IP do servidor (padrão: `127.0.0.1`)
- `--port`: Porta UDP do servidor (padrão: `50000`)
- `--mode`: Modo de transferência — `individual` ou `batch` (padrão: `individual`)
- `--strategy`: Estratégia de retransmissão — `gbn` ou `sr` (padrão: `gbn`)
- `--max-text`: Limite máximo previsto para o texto, em caracteres, de 30 a 65.535 (padrão: `30`). Isso não obriga cada mensagem a ter 30 caracteres.

Se mudar a porta do servidor, informe a mesma porta ao cliente com `--port`. Para acessar um servidor em outra máquina, use `--host` seguido do IP correspondente.

---

## Exemplo de execução

Ao executar `python src/client.py --mode batch --strategy gbn`, as duas pontas mostram as etapas do handshake e os parâmetros acordados:

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

O registro completo dessa execução está em [`docs/exemplo-handshake.txt`](docs/exemplo-handshake.txt). As regras e os formatos dos pacotes estão em [`docs/protocolo.md`](docs/protocolo.md).

---

## Testes

Para executar os testes do checksum e dos pacotes com o módulo `unittest` da biblioteca padrão:

```bash
python -m unittest discover -s tests -v
```

Os testes usam valores esperados conhecidos e cobrem entradas pares e ímpares, transporte circular, checksum em seu campo, alteração de um bit e preservação dos bytes de entrada.

Os testes de pacotes conferem os bytes e deslocamentos dos campos, as sequências de 0 a 16.383, os limites do payload, UTF-8 e a contagem de pontos de código sem normalização. Também verificam a rejeição de campos inválidos, pacotes truncados, bytes extras e checksum incorreto, além da compatibilidade dos pacotes de handshake.

Para executar somente os testes de pacotes:

```bash
python -m unittest discover -s tests -p "test_packets.py" -v
```

Para executar as verificações de montagem e leitura de `HELLO`, `HELLO_ACK` e `READY`:

```bash
python src/protocol.py
```

As verificações de handshake cobrem os pacotes do CP1. Os testes de `DATA` e `ACK` validam a montagem e leitura dos bytes, sem transferência por sockets. Os testes de transferência serão acrescentados quando esse fluxo for implementado.
