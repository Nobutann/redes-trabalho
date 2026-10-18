# Trabalho I — Transporte Confiável na Camada de Aplicação

Este projeto faz parte da disciplina de Infraestrutura de Comunicação. O objetivo é construir uma aplicação cliente-servidor que use UDP e implemente suas próprias regras de transporte confiável.

A aplicação divide textos em fragmentos de até quatro caracteres e prepara pacotes com número de sequência, indicador de último fragmento e checksum. No modo individual, envia um fragmento por vez e aguarda seu ACK. Em batch, usa uma janela anunciada pelo servidor, com confirmações cumulativas em Go-Back-N ou individuais em Repetição Seletiva. O servidor reconstrói o texto nos dois modos.

**Estado atual:** Checkpoint 1 concluído. As transferências individual e em batch estão implementadas no caminho sem erros ou perdas, usando o mesmo socket do handshake e o checksum manual de `src/protocol.py`. Os timeouts encerram tentativas sem progresso; ainda não há recuperação por retransmissão.

Os formatos de `DATA` e `ACK` e o fluxo de transferência sem erros estão descritos em [`docs/protocolo.md`](docs/protocolo.md). O CP2 permanece pendente da revisão final da especificação e dos requisitos.

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
│   ├── server.py              # Servidor UDP, handshake e recepção do texto
│   └── client.py              # Cliente UDP e interface CLI
└── tests/
    ├── test_batch.py          # Janelas, confirmações GBN/SR e configuração do servidor
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

Por padrão, o servidor escuta em `0.0.0.0:50000` e anuncia uma janela de cinco fragmentos. `--window` aceita inteiros de 1 a 5, validados antes de abrir o socket. Para usar outra porta e uma janela de três:

```bash
python src/server.py --port 50001 --window 3
```

A janela anunciada no `HELLO_ACK` permanece válida durante toda a sessão. O cliente usa esse valor, sem alterar a janela durante a transferência.

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

# Transferência em batch com Repetição Seletiva
python src/client.py --mode batch --strategy sr --text "REDE LOCAL"

# Oito fragmentos em batch com Go-Back-N
python src/client.py --mode batch --strategy gbn --text "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234"
```

Sem `--text`, o cliente executa apenas o handshake. Com `--text`, valida e prepara os pacotes antes de abrir o socket. Após o handshake, o modo individual envia cada `DATA` e aguarda seu ACK antes de avançar. Em batch, preenche a janela antes de esperar ACKs e envia novos fragmentos conforme a base avança. Em GBN, `ACK n` confirma tudo até `n`; em SR, confirma apenas `n`, e a base só avança pelas confirmações consecutivas. O servidor exibe o texto apenas quando todos os fragmentos tiverem sido recebidos, e o cliente conclui quando todos estiverem confirmados.

O cliente encerra com status de erro após cinco segundos sem novas confirmações. O servidor encerra uma sessão após cinco segundos sem aceitar novos fragmentos e volta a aguardar `HELLO`. Isso também libera sessões de clientes sem `--text`. Pacotes inválidos ou repetidos não renovam a espera. Não há retransmissão. O servidor atende uma sessão por vez; após um handshake sem texto, aguarde esse prazo antes de iniciar outra sessão.

Parâmetros disponíveis em `client.py`:

- `--host`: IP do servidor ou `localhost` (padrão: `127.0.0.1`)
- `--port`: Porta UDP do servidor (padrão: `50000`)
- `--mode`: Modo de transferência — `individual` ou `batch` (padrão: `individual`)
- `--strategy`: Estratégia de confirmação em batch — `gbn` ou `sr` (padrão: `gbn`). No modo individual, ambas usam a mesma transferência sem retransmissão.
- `--max-text`: Limite máximo do texto, em caracteres, de 30 a 65.535 (padrão: `30`). Isso não obriga cada mensagem a ter 30 caracteres.
- `--text`: Texto não vazio para transferir, com até `--max-text` caracteres. Espaços são preservados e cada ponto de código Unicode conta como um caractere, sem normalização. Use aspas para manter espaços no argumento.

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

Os testes de preparação cobrem sequências, `LAST`, payloads, checksum e reconstrução exata do texto, incluindo espaços, acentos, caracteres de quatro bytes em UTF-8 e os limites de `max_text`. Os testes unitários também conferem a validação antes da comunicação, janelas de 1 a 5, ACKs cumulativos e fora de ordem, recepção sem duplicatas e timeouts sem retransmissão.

Os testes de integração usam processos e sockets UDP reais em localhost, com portas disponíveis escolhidas pelo sistema. Cobrem a reconstrução exata nos dois modos, GBN e SR com janelas de 1 a 5 e novas sessões após conclusão ou timeout. Testes com ACKs controlados verificam o preenchimento da janela antes da primeira espera e o envio dos fragmentos liberados, incluindo a retenção da base em SR quando há lacunas. Essa parte da suíte precisa de permissão para abrir sockets locais.

Para executar somente os testes de pacotes:

```bash
python -m unittest discover -s tests -p "test_packets.py" -v
```

Para executar as verificações de montagem e leitura de `HELLO`, `HELLO_ACK` e `READY`:

```bash
python src/protocol.py
```

As verificações de handshake cobrem os pacotes do CP1. Os testes de transferência cobrem os modos individual e batch no caminho sem recuperação por retransmissão.
