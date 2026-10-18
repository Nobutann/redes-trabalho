# Trabalho I — Transporte Confiável na Camada de Aplicação

Este projeto faz parte da disciplina de Infraestrutura de Comunicação. O objetivo é construir uma aplicação cliente-servidor que use UDP e implemente suas próprias regras de transporte confiável.

A aplicação divide textos em fragmentos de até quatro caracteres e prepara pacotes com número de sequência, indicador de último fragmento e checksum. No modo individual, envia um fragmento por vez, aguarda seu ACK e reconstrói o texto no servidor. O envio em lote e as retransmissões com Go-Back-N e Repetição Seletiva serão implementados nas próximas etapas.

**Estado atual:** Checkpoint 1 concluído. Cliente e servidor realizam o handshake de três vias e trocam os parâmetros da comunicação. A transferência individual de texto sem erros ou perdas está implementada, usando o mesmo socket do handshake e o checksum manual de `src/protocol.py`. Em batch, o cliente apenas negocia os parâmetros e prepara os pacotes `DATA`.

Os formatos de `DATA` e `ACK` e o fluxo de transferência sem erros estão descritos em [`docs/protocolo.md`](docs/protocolo.md). A transferência em batch e o controle de janelas ainda não estão implementados. O CP2 permanece pendente.

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
│   ├── protocolo.md           # Formato dos pacotes e fluxo de comunicação
│   └── exemplo-handshake.txt  # Exemplo de saída do handshake
├── src/
│   ├── protocol.py            # Fragmentação, checksum, montagem e leitura dos pacotes
│   ├── server.py              # Servidor UDP, handshake e recepção individual
│   └── client.py              # Cliente UDP e interface CLI
└── tests/
    ├── test_checksum.py       # Testes do cálculo e da verificação do checksum
    ├── test_client.py         # CLI, handshake e envio individual com ACK
    ├── test_fragmentation.py  # Preparação de DATA, limites e preservação do texto
    ├── test_packets.py        # Formatos, validação de DATA/ACK e compatibilidade do handshake
    ├── test_server.py         # Recepção, reconstrução e encerramento de sessões
    └── test_transfer.py       # Integração com UDP real em localhost
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

# Transferência individual de três fragmentos
python src/client.py --mode individual --text "REDE LOCAL"

# Em batch, apenas handshake e preparação dos pacotes
python src/client.py --mode batch --strategy sr --text "REDE LOCAL"
```

Sem `--text`, o cliente executa apenas o handshake. Com `--text`, valida e prepara os pacotes antes de abrir o socket. Após o handshake, o modo individual envia cada `DATA` e aguarda seu ACK antes de avançar. A transferência só termina após a confirmação do último fragmento, e o servidor exibe o texto reconstruído. Em batch, a execução termina após informar a quantidade de pacotes preparados.

O cliente aguarda até cinco segundos por cada ACK; sem uma confirmação válida, encerra com status de erro. O servidor encerra uma sessão individual após cinco segundos sem aceitar o próximo `DATA` e volta a aguardar `HELLO`. Isso também libera sessões de clientes sem `--text`. Não há retransmissão. O servidor atende uma sessão por vez; após um handshake individual sem texto, aguarde esse prazo antes de iniciar outra sessão.

Parâmetros disponíveis em `client.py`:

- `--host`: IP do servidor ou `localhost` (padrão: `127.0.0.1`)
- `--port`: Porta UDP do servidor (padrão: `50000`)
- `--mode`: Modo de transferência — `individual` ou `batch` (padrão: `individual`)
- `--strategy`: Estratégia de retransmissão — `gbn` ou `sr` (padrão: `gbn`). No modo individual, ambas usam a mesma transferência sem retransmissão.
- `--max-text`: Limite máximo do texto, em caracteres, de 30 a 65.535 (padrão: `30`). Isso não obriga cada mensagem a ter 30 caracteres.
- `--text`: Texto não vazio para transferir no modo individual ou apenas preparar pacotes em batch, com até `--max-text` caracteres. Espaços são preservados e cada ponto de código Unicode conta como um caractere, sem normalização. Use aspas para manter espaços no argumento.

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

Para executar os testes com o módulo `unittest` da biblioteca padrão:

```bash
python -m unittest discover -s tests -v
```

Os testes usam valores esperados conhecidos e cobrem entradas pares e ímpares, transporte circular, checksum em seu campo, alteração de um bit e preservação dos bytes de entrada.

Os testes de pacotes conferem os bytes e deslocamentos dos campos, as sequências de 0 a 16.383, os limites do payload, UTF-8 e a contagem de pontos de código sem normalização. Também verificam a rejeição de campos inválidos, pacotes truncados, bytes extras e checksum incorreto, além da compatibilidade dos pacotes de handshake.

Os testes de preparação cobrem sequências, `LAST`, payloads, checksum e reconstrução exata do texto, incluindo espaços, acentos, caracteres de quatro bytes em UTF-8 e os limites de `max_text`. Os testes unitários do cliente e do servidor usam sockets simulados para conferir a validação antes da comunicação, o avanço apenas com ACK válido, a recepção em ordem e os timeouts sem retransmissão.

Os testes de integração usam processos e sockets UDP reais em localhost, com portas disponíveis escolhidas pelo sistema. Cobrem a reconstrução exata, o envio individual, o comportamento de batch e novas sessões após conclusão ou timeout, inclusive após handshake sem texto. Essa parte da suíte precisa de permissão para abrir sockets locais.

Para executar somente os testes de pacotes:

```bash
python -m unittest discover -s tests -p "test_packets.py" -v
```

Para executar as verificações de montagem e leitura de `HELLO`, `HELLO_ACK` e `READY`:

```bash
python src/protocol.py
```

As verificações de handshake cobrem os pacotes do CP1. Os testes de transferência cobrem o modo individual sem retransmissão; a transferência em batch permanece pendente.
