# Trabalho I: Transporte Confiável na Camada de Aplicação

Este projeto faz parte da disciplina de Infraestrutura de Comunicação. O objetivo é construir uma aplicação cliente-servidor que use UDP e implemente suas próprias regras de transporte confiável.

A aplicação divide textos em fragmentos de até quatro caracteres e prepara pacotes com número de sequência, indicador de último fragmento e checksum. No modo individual, envia um fragmento por vez e aguarda seu ACK. Em batch, usa uma janela anunciada pelo servidor, com confirmações cumulativas em Go-Back-N ou individuais em Repetição Seletiva. Perdas e corrupções são recuperadas com temporizadores, NAK e retransmissões, e podem ser simuladas de forma determinística no cliente.

**Estado atual:** Checkpoint 3 concluído.

---

## Etapas do trabalho

| Marco | Data | Status | Escopo |
|---|---|---|---|
| Checkpoint 1: Handshake & Sockets | 09/09/2026 | Concluído | Conexão UDP e handshake de 3 vias (modo, estratégia, tamanho máximo e janela) |
| Checkpoint 2: Protocolo sem erros | 21/10/2026 | Concluído | Definição completa do protocolo e transferência de dados sem erros ou perdas |
| Checkpoint 3: Erros e perdas | 23/11/2026 | Concluído | Simulação determinística de falhas e recuperação com temporizadores, NAK, Go-Back-N e Repetição Seletiva |

---

## Organização do projeto

```
redes-trabalho/
├── README.md
├── docs/
│   ├── protocolo.md           # Formato dos pacotes, estados e regras de recuperação
│   ├── cenarios-cp3.md        # Saídas reais dos cenários de erros e perdas
│   └── exemplo-handshake.txt  # Exemplo de saída do handshake
├── src/
│   ├── protocol.py            # Fragmentação, checksum, montagem e leitura dos pacotes
│   ├── server.py              # Servidor UDP, handshake, recepção, NAK e duplicatas
│   ├── client.py              # Cliente UDP, janela, temporizadores e retransmissão
│   ├── faults.py              # Simulação determinística de perdas e corrupções
│   └── cipher.py              # Cifra de César
└── tests/
    ├── test_batch.py          # Janelas, confirmações GBN/SR e configuração do servidor
    ├── test_checksum.py       # Cálculo e verificação do checksum
    ├── test_cipher.py         # Cifra de César
    ├── test_client.py         # CLI, handshake, falhas simuladas e cifra no cliente
    ├── test_faults.py         # Regras de falha e alteração dos pacotes
    ├── test_fragmentation.py  # Preparação de DATA, limites e preservação do texto
    ├── test_packets.py        # Formatos e validação de DATA, ACK, NAK e handshake
    ├── test_recovery.py       # Timeouts, NAK e retransmissões em GBN, SR e individual
    ├── test_server.py         # Recepção, NAK, duplicatas e retenção de sessões
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

A janela anunciada no `HELLO_ACK` permanece válida durante toda a sessão.

Parâmetros disponíveis em `server.py`:

- `--port`: Porta UDP (padrão: `50000`)
- `--window`: Janela de recepção, de 1 a 5 (padrão: `5`)
- `--key`: Chave da cifra de César, de 1 a 25. Deve ser a mesma usada no cliente. Sem ela, o texto é exibido como chegou.

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

Sem `--text`, o cliente executa apenas o handshake. Com `--text`, valida e prepara os pacotes antes de abrir o socket. O modo individual envia cada `DATA` e aguarda seu ACK antes de avançar. Em batch, o cliente preenche a janela antes de esperar ACKs e envia novos fragmentos conforme a base avança. Em GBN, `ACK n` confirma tudo até `n`; em SR, confirma apenas `n`, e a base só avança pelas confirmações consecutivas.

Se um DATA não for confirmado em cinco segundos, ou se o servidor responder com NAK, o cliente retransmite: em GBN, todos os pendentes a partir da base; em SR e no modo individual, somente o pacote afetado. Cada DATA admite até três retransmissões. Depois disso, o cliente encerra com status de erro. O servidor responde novamente a duplicatas e encerra uma sessão após 25 segundos sem receber novos fragmentos.

Parâmetros disponíveis em `client.py`:

- `--host`: IP do servidor ou `localhost` (padrão: `127.0.0.1`)
- `--port`: Porta UDP do servidor (padrão: `50000`)
- `--mode`: Modo de transferência, `individual` ou `batch` (padrão: `individual`)
- `--strategy`: Estratégia de confirmação em batch, `gbn` ou `sr` (padrão: `gbn`). No modo individual, as duas se comportam da mesma forma.
- `--max-text`: Limite máximo do texto, em caracteres, de 30 a 65.535 (padrão: `30`). Isso não obriga cada mensagem a ter 30 caracteres.
- `--text`: Texto não vazio para transferir, com até `--max-text` caracteres. Use aspas para manter espaços no argumento.
- `--fault`: Falha simulada no formato `TIPO:SEQ:OCORRÊNCIA:AÇÃO`. Pode ser repetida.
- `--key`: Chave da cifra de César, de 1 a 25. Deve ser a mesma configurada no servidor.

Se mudar a porta do servidor, informe a mesma porta ao cliente com `--port`. Para acessar um servidor em outra máquina, use `--host` seguido do IP correspondente.

### 3. Simular erros e perdas

Cada regra de `--fault` diz qual pacote falha e como:

- `TIPO`: `DATA`, `ACK` ou `NAK`
- `SEQ`: número de sequência do pacote
- `OCORRÊNCIA`: a partir de 1. Para DATA, é a tentativa de envio; para ACK e NAK, é a chegada de número N daquela resposta.
- `AÇÃO`: `perder` descarta o pacote; `corromper` inverte um bit para que o checksum falhe.

A perda de DATA acontece antes do envio, e a de ACK e NAK acontece na chegada ao cliente. Assim, nada precisa ser configurado no servidor. Alguns exemplos:

```bash
# Perda de DATA 1: recuperação por timeout
python src/client.py --mode batch --strategy sr --text "REDE LOCAL TESTE" --fault DATA:1:1:perder

# Corrupção de DATA 1: o servidor responde com NAK e o cliente reenvia
python src/client.py --mode batch --strategy gbn --text "REDE LOCAL TESTE" --fault DATA:1:1:corromper

# Perda do último ACK: o servidor confirma a duplicata sem exibir o texto de novo
python src/client.py --mode batch --strategy sr --text "REDE LOCAL" --fault ACK:2:1:perder

# Todas as tentativas de DATA 0 perdidas: o cliente desiste com erro
python src/client.py --text "A" --fault DATA:0:1:perder --fault DATA:0:2:perder --fault DATA:0:3:perder --fault DATA:0:4:perder
```

As saídas completas desses e de outros cenários estão em [docs/cenarios-cp3.md](docs/cenarios-cp3.md).

### 4. Usar a cifra de César

Inicie o servidor e o cliente com a mesma chave:

```bash
python src/server.py --key 3
```

```bash
python src/client.py --text "REDE LOCAL" --key 3
```

O cliente cifra o texto antes de fragmentá-lo, então os pacotes carregam `UHGH ORFDO`. O servidor exibe o texto cifrado recebido e, em seguida, a mensagem decifrada.

---

## Exemplo de execução

Com o servidor em execução, envie uma mensagem perdendo o primeiro envio do DATA 1:

```bash
python src/client.py --mode individual --text "REDE LOCAL" --fault DATA:1:1:perder
```

**Cliente:**

```
[CLIENT] Pacotes DATA preparados: 3
[CLIENT] DATA enviado (seq=0, tentativa=1)
[CLIENT] ACK recebido (seq=0, checksum=0x55FA)
[CLIENT] Janela avançou (base=1, window=1)
[CLIENT] DATA enviado (seq=1, tentativa=1)
[FAULT] perder DATA 1 (ocorrência 1)
[CLIENT] Timeout de DATA 1
[CLIENT] DATA retransmitido por timeout (seq=1, tentativa=2)
[CLIENT] ACK recebido (seq=1, checksum=0x55F9)
[CLIENT] Janela avançou (base=2, window=1)
[CLIENT] DATA enviado (seq=2, tentativa=1)
[CLIENT] ACK recebido (seq=2, checksum=0x55F8)
[CLIENT] Janela avançou (base=3, window=1)
[CLIENT] Transferência concluída: todos os fragmentos confirmados
```

**Servidor:**

```
[SERVER] DATA recebido (seq=0, LAST=0, LEN=4, checksum=0xBF6C)
[SERVER] ACK 0 enviado
[SERVER] DATA recebido (seq=1, LAST=0, LEN=4, checksum=0xE666)
[SERVER] ACK 1 enviado
[SERVER] DATA recebido (seq=2, LAST=1, LEN=2, checksum=0x13AB)
[SERVER] ACK 2 enviado
[SERVER] Mensagem reconstruída: REDE LOCAL
```

O servidor nunca vê o envio perdido. Ele recebe apenas a retransmissão, e o espaço entre as palavras é preservado na reconstrução. O [exemplo de handshake do CP1](docs/exemplo-handshake.txt) continua disponível como registro daquela etapa.

---

## Testes

Para executar os testes com o módulo `unittest` da biblioteca padrão:

```bash
python -m unittest discover -s tests -v
```

Os testes de checksum usam valores esperados conhecidos e cobrem entradas pares e ímpares, transporte circular, checksum em seu campo e alteração de um bit. Os testes de pacotes conferem os bytes e deslocamentos de DATA, ACK e NAK, os limites de sequência e payload, UTF-8 e a rejeição de pacotes inválidos, com `ChecksumError` para checksum incorreto.

Os testes de recuperação usam um relógio simulado para verificar, sem esperas reais, o reenvio a partir da base em GBN, o reenvio individual em SR, o tratamento de NAK repetido, o limite de três retransmissões e o efeito de cada falha simulada. Os testes do servidor cobrem o envio de NAK, as respostas a duplicatas, o prazo de 25 segundos e a retenção da sessão concluída. Também há testes para as regras de `--fault` e para a cifra de César.

Os testes de integração usam processos e sockets UDP reais em localhost, com temporizadores reduzidos. Cobrem a reconstrução exata nos dois modos, GBN e SR com janelas de 1 a 5, recuperação de perdas e corrupções de DATA, ACK e NAK, a cifra de ponta a ponta e novas sessões após conclusão ou timeout. Essa parte da suíte precisa de permissão para abrir sockets locais.

Para executar somente os testes de recuperação:

```bash
python -m unittest discover -s tests -p "test_recovery.py" -v
```

Para executar as verificações de montagem e leitura de `HELLO`, `HELLO_ACK` e `READY`:

```bash
python src/protocol.py
```
