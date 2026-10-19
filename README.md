# Trabalho I — Transporte Confiável na Camada de Aplicação

Este projeto faz parte da disciplina de Infraestrutura de Comunicação. O objetivo é construir uma aplicação cliente-servidor que use UDP e implemente suas próprias regras de transporte confiável.

A aplicação divide textos em fragmentos de até quatro caracteres e prepara pacotes com número de sequência, indicador de último fragmento e checksum. No modo individual, envia um fragmento por vez e aguarda seu ACK. Em batch, usa uma janela anunciada pelo servidor, com confirmações cumulativas em Go-Back-N ou individuais em Repetição Seletiva. O servidor reconstrói o texto nos dois modos.

**Estado atual:** Código e especificação do CP2 concluídos. As transferências individual e em batch funcionam no caminho sem erros ou perdas, usando o mesmo socket do handshake e o checksum manual de `src/protocol.py`. Os timeouts encerram tentativas sem progresso.

A [especificação do protocolo](docs/protocolo.md) reúne os formatos dos pacotes, os estados da sessão e as regras de confirmação e recuperação. NAK, retransmissões e simulação de falhas estão definidos para implementação no CP3. A cifra de César está prevista para o bônus da entrega final.

---

## Etapas do trabalho

| Marco | Data | Status | Escopo |
|---|---|---|---|
| Checkpoint 1 — Handshake & Sockets | 09/09/2026 | Concluído | Conexão UDP e handshake de 3 vias (modo, estratégia, tamanho máximo e janela) |
| Checkpoint 2 — Protocolo sem erros | 21/10/2026 | Código e protocolo concluídos | Definição completa do protocolo e transferência de dados sem erros ou perdas |
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
# Transferência individual de três fragmentos
python src/client.py --mode individual --text "REDE LOCAL"

# Transferência em batch com Repetição Seletiva
python src/client.py --mode batch --strategy sr --text "REDE LOCAL"

# Oito fragmentos em batch com Go-Back-N
python src/client.py --mode batch --strategy gbn --text "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234"

# Apenas o handshake, com limite de texto igual a 100
python src/client.py --mode batch --strategy sr --max-text 100
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

Com o servidor em execução, envie uma mensagem:

```bash
python src/client.py --mode individual --text "REDE LOCAL"
```

Depois do handshake, o cliente envia os três fragmentos e recebe suas confirmações:

**Cliente:**

```
[CLIENT] Pacotes DATA preparados: 3
[CLIENT] DATA enviado (seq=0)
[CLIENT] ACK recebido (seq=0, checksum=0x55FA)
[CLIENT] DATA enviado (seq=1)
[CLIENT] ACK recebido (seq=1, checksum=0x55F9)
[CLIENT] DATA enviado (seq=2)
[CLIENT] ACK recebido (seq=2, checksum=0x55F8)
[CLIENT] Transferência concluída: todos os fragmentos confirmados
```

**Servidor:**

```
[SERVER] DATA recebido (seq=0, LAST=0, LEN=4, checksum=0xBF6C)
[SERVER] DATA recebido (seq=1, LAST=0, LEN=4, checksum=0xE666)
[SERVER] DATA recebido (seq=2, LAST=1, LEN=2, checksum=0x13AB)
[SERVER] Mensagem reconstruída: REDE LOCAL
```

O espaço entre as palavras faz parte do segundo fragmento e é preservado na reconstrução. O [exemplo de handshake do CP1](docs/exemplo-handshake.txt) continua disponível como registro daquela etapa.

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
