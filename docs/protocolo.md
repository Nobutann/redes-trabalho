# Especificação do protocolo

Este documento define o protocolo do projeto. O CP2 implementa o handshake, o checksum manual e a transferência de texto sem erros ou perdas, nos modos individual e batch, com confirmações GBN ou SR. As regras de recuperação também estão definidas aqui, mas sua implementação pertence ao CP3.

As seções 1 a 6 descrevem o funcionamento disponível. As seções 7 a 9 completam a especificação com estados, NAK, retransmissões e simulação de falhas, indicando o que muda no CP3. A seção 10 define a opção de criptografia para a entrega final.

## 1. Visão geral e parâmetros

A comunicação usa sockets UDP. No início de cada sessão, o cliente informa o modo de operação, a estratégia e o limite do texto; o servidor responde com o tamanho da janela.

| Parâmetro | Valor | Detalhes |
|---|---|---|
| Transporte | UDP (`SOCK_DGRAM`) | O projeto implementará as regras de transporte confiável na camada de aplicação |
| Porta padrão | 50000 | Configurável via `--port` |
| Ordem dos bytes | Big-endian | Usada nos campos com mais de um byte |
| Modo de operação | `0` (Individual), `1` (Batch) | Definido no campo `MODE` do `HELLO` |
| Estratégia de confirmação em batch | `0` (Go-Back-N), `1` (Repetição Seletiva) | Definido no campo `STRATEGY` do `HELLO`; retransmissão ainda não implementada |
| Payload máximo | 4 pontos de código Unicode, até 16 bytes em UTF-8 | Texto fragmentado antes da codificação; limite validado por pacote `DATA` |
| Limite máximo do texto | Padrão 30 caracteres; configurável de 30 a 65.535 | Informado no campo `MAX_TEXT` de 2 bytes do `HELLO` |
| Janela de recepção | 1 a 5; padrão 5 | Configurada por `--window` no servidor e anunciada no `HELLO_ACK`; constante durante a sessão |
| Buffer do socket | 1024 bytes | Constante `BUFSIZE` |
| Timeout do cliente no CP2 | 5.0 segundos | Espera por `HELLO_ACK` ou por novas confirmações de DATA |
| Timeout de sessão no servidor no CP2 | 5.0 segundos | Espera por `READY` ou por novos fragmentos válidos |

O mínimo de 30 se refere ao limite configurado, não ao tamanho obrigatório da mensagem. Com `MAX_TEXT = 30`, por exemplo, uma mensagem de um caractere está dentro do limite. Para a contagem e a fragmentação, cada caractere corresponde a um ponto de código Unicode.

O cliente valida `--max-text` e, quando informado, `--text` antes de abrir o socket. Valores fora de 30 a 65.535, texto vazio ou acima do limite geram erro. `build_hello` também valida esse intervalo antes de codificar o campo de 2 bytes. Sem `--text`, a execução continua restrita ao handshake; com ele, os pacotes são transferidos no modo negociado. O servidor valida `--window` antes de abrir o socket e mantém o valor anunciado até o encerramento da sessão.

---

## 2. Formato dos pacotes

### 2.1 Cabeçalho comum

Todos os pacotes começam com dois campos: `MAGIC`, que identifica o protocolo, e `TYPE`, que informa qual mensagem foi enviada. Esse cabeçalho é mantido nos formatos de `DATA` e `ACK` implementados para o CP2.

```
+--------+--------+
| MAGIC  | TYPE   |
| 1 byte | 1 byte |
+--------+--------+
```

- **MAGIC** (`0xAA`): Identificador do protocolo.
- **TYPE**: Identificador de 1 byte, conforme a tabela abaixo.

| TYPE | Pacote | Estado |
|---|---|---|
| `0x01` | `HELLO` | Implementado no CP1 |
| `0x02` | `HELLO_ACK` | Implementado no CP1 |
| `0x03` | `READY` | Implementado no CP1 |
| `0x04` | `DATA` | Montagem, leitura e transferência individual e em batch implementadas |
| `0x05` | `ACK` | Montagem, leitura e confirmações individuais e cumulativas implementadas |
| `0x06` | `NAK` | Definido na seção 8.1; implementação no CP3 |

Todos os campos numéricos são inteiros sem sinal. Campos com mais de um byte usam big-endian, com o byte mais significativo primeiro.

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
| MAX_TEXT | 2 bytes | unsigned int, big-endian | Limite máximo da mensagem em caracteres; de 30 a 65.535, com padrão 30 |
| RESERVED | 1 byte | unsigned int | `0x00` (reservado) |

#### HELLO_ACK (Servidor -> Cliente) — 3 bytes

O servidor responde com `HELLO_ACK`, informando o tamanho da janela configurado por `--window` (padrão 5). Esse valor permanece válido durante toda a sessão.

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
| WINDOW | 1 byte | unsigned int | Tamanho da janela de 1 a 5, com padrão 5 |

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

Na versão atual, ambos os modos com `--text` continuam a transferência pelo mesmo socket. O servidor mantém o endereço e os parâmetros da sessão, incluindo estratégia e janela, e só inicia a recepção após um `READY` válido.

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
   |     MAGIC(0xAA) | 0x02 | WINDOW(1 a 5)                     |
   |  <-------------------------------------------------------- |
   |  (recebe janela, confirma parâmetros)                      | (aguarda READY da mesma origem)
   |                                                            |
   |  3. READY [2 bytes]                                        |
   |     MAGIC(0xAA) | 0x03                                     |
   |  --------------------------------------------------------> |
   |  (handshake pronto)                                        | (handshake concluído;
   |                                                            |  segue conforme o modo negociado)
```

### Validação e descarte

- Se `MAGIC` for diferente de `0xAA`, a leitura do pacote gera `InvalidPacketError`. O servidor registra um aviso e descarta o pacote.
- Valores de `MAX_TEXT` fora do intervalo de 30 a 65.535 ou de `WINDOW` fora do intervalo de 1 a 5 geram `ValueError`.
- Enquanto espera o `READY`, o servidor aceita apenas pacotes do endereço que enviou o `HELLO`. Pacotes de outras origens são ignorados.
- Se o cliente não receber resposta em até cinco segundos, ele informa o timeout e encerra a tentativa.
- O servidor também espera até cinco segundos pelo `READY`. Se esse prazo terminar sem a mensagem esperada, registra o handshake interrompido e volta a aguardar um novo `HELLO`, sem iniciar a recepção de DATA.

Esses timeouts encerram a tentativa de handshake. Não há retransmissão automática dessa etapa; uma nova tentativa exige executar o cliente novamente. A simulação de falhas do CP3 começa depois do `READY` e não altera o handshake.

---

## 4. DATA e ACK

As funções `build_data`, `build_ack` e `parse_packet`, em `src/protocol.py`, montam e leem esses pacotes, validando seus campos e checksum. A validação de um pacote não determina se um ACK corresponde a um fragmento enviado nem se a mensagem completa respeita o `MAX_TEXT` negociado; essas regras dependem da sessão.

As seções 4 a 6 descrevem a transferência de uma mensagem de texto não vazia, sem erros ou perdas. A fragmentação, a preparação dos pacotes, as transferências individual e em batch e a reconstrução no servidor estão implementadas. Cada datagrama UDP transporta um pacote do protocolo. Os formatos do handshake e seus timeouts de cinco segundos permanecem como descritos nas seções anteriores.

### 4.1 Texto, fragmentação e sequência

O cliente aceita textos não vazios de até `MAX_TEXT` caracteres pelo argumento `--text`, contando pontos de código Unicode antes da codificação em UTF-8. O padrão é 30 e o limite configurado deve ficar entre 30 e 65.535. A mensagem pode ser menor que 30 caracteres.

`prepare_data_packets(text, max_text)`, em `src/protocol.py`, valida esses limites e retorna uma lista dos pacotes completos em bytes, reutilizando `build_data`. A função independe de sockets e é chamada pelo cliente antes da comunicação.

O texto original é dividido, na ordem, em fragmentos de quatro pontos de código. Apenas o último pode ter menos de quatro. Cada fragmento é então codificado em UTF-8 separadamente, sem cortar os bytes de um caractere. Um ponto de código pode ocupar de um a quatro bytes em UTF-8; por isso, quatro caracteres podem ocupar de quatro a 16 bytes. Espaços também contam como caracteres e são preservados. A contagem usa os pontos de código do texto original, sem normalização: um acento combinante separado conta como outro ponto de código.

O primeiro fragmento tem `SEQ = 0`, e cada fragmento seguinte soma um à sequência. O último tem `LAST = 1`, mesmo quando contém exatamente quatro caracteres; todos os anteriores têm `LAST = 0`.

Com o maior `MAX_TEXT` representável, são necessários no máximo `ceil(65.535 / 4) = 16.384` fragmentos, numerados de 0 a 16.383. Um byte de sequência não comporta esse total; dois bytes são suficientes e evitam reutilizar números dentro da mesma mensagem.

### 4.2 DATA (Cliente -> Servidor)

O pacote tem 8 bytes de cabeçalho, seguidos por `LEN` bytes de payload, totalizando de 9 a 24 bytes. `build_data(seq, last, payload)` recebe o payload já codificado em bytes UTF-8 e retorna os bytes do pacote completo. Os deslocamentos abaixo começam em zero e se referem ao início do pacote da aplicação.

```
+--------+--------+---------+--------+--------+----------+-------------+
| MAGIC  | TYPE   | SEQ     | LAST   | LEN    | CHECKSUM | PAYLOAD     |
| 1 byte | 1 byte | 2 bytes | 1 byte | 1 byte | 2 bytes  | LEN bytes   |
+--------+--------+---------+--------+--------+----------+-------------+
```

| Campo | Deslocamento | Tamanho | Valores e significado |
|---|---|---|---|
| MAGIC | 0 | 1 byte | `0xAA` |
| TYPE | 1 | 1 byte | `0x04` (`DATA`) |
| SEQ | 2 | 2 bytes | Número do fragmento em big-endian; de 0 a 16.383, limitado à posição na mensagem |
| LAST | 4 | 1 byte | `0x00` = há mais fragmentos; `0x01` = último fragmento; outros valores são inválidos |
| LEN | 5 | 1 byte | Quantidade de bytes do payload UTF-8, de 1 a 16; deve corresponder ao tamanho recebido após o cabeçalho |
| CHECKSUM | 6 | 2 bytes | Checksum de 16 bits em big-endian, de `0x0000` a `0xFFFF`, calculado conforme a seção 4.4 |
| PAYLOAD | 8 | LEN bytes | UTF-8 válido com quatro pontos de código, ou de um a quatro no último fragmento |

Não há terminador de texto nem bytes extras após o payload. `LEN` conta bytes, enquanto `MAX_TEXT` e o limite de quatro por fragmento contam caracteres. Um byte é suficiente para `LEN`, pois o payload tem no máximo 16 bytes.

### 4.3 ACK (Servidor -> Cliente)

O pacote tem exatamente 6 bytes e não carrega texto nem campo de comprimento de payload. `build_ack(seq)` recebe a sequência reconhecida e retorna os bytes do pacote completo.

```
+--------+--------+---------+----------+
| MAGIC  | TYPE   | SEQ     | CHECKSUM |
| 1 byte | 1 byte | 2 bytes | 2 bytes  |
+--------+--------+---------+----------+
```

| Campo | Deslocamento | Tamanho | Valores e significado |
|---|---|---|---|
| MAGIC | 0 | 1 byte | `0xAA` |
| TYPE | 1 | 1 byte | `0x05` (`ACK`) |
| SEQ | 2 | 2 bytes | Sequência reconhecida, em big-endian; de 0 a 16.383 e referente a um fragmento enviado da mensagem |
| CHECKSUM | 4 | 2 bytes | Checksum de 16 bits em big-endian, de `0x0000` a `0xFFFF`, calculado conforme a seção 4.4 |

O significado de `ACK n` depende do modo e da estratégia negociados:

| Modo / estratégia | Significado de ACK n |
|---|---|
| Individual, com qualquer estratégia informada no handshake | Confirma somente o fragmento `n` |
| Batch com Repetição Seletiva (SR) | Confirma somente o fragmento `n` |
| Batch com Go-Back-N (GBN) | Confirma todos os fragmentos de `0` até `n`, inclusive |

Em GBN, o servidor só confirma `n` quando tiver recebido todos os fragmentos até ele. `ACK 0` confirma o fragmento zero; o número no ACK nunca representa o próximo fragmento esperado.

### 4.4 Checksum de DATA e ACK

O cálculo manual do checksum de 16 bits em complemento de um e sua verificação estão implementados em `src/protocol.py`, pelas funções `calculate_checksum(data)` e `verify_checksum(data)`, sem usar uma função pronta de checksum. Elas processam os bytes exatamente como recebidos, sem interpretar campos ou tipos de pacote. Os construtores de `DATA` e `ACK` zeram o campo `CHECKSUM` antes de chamar o cálculo, seguindo estas regras:

1. Montar os bytes do pacote com os dois bytes de `CHECKSUM` zerados. Em `DATA`, o cálculo cobrirá `MAGIC`, `TYPE`, `SEQ`, `LAST`, `LEN`, o campo `CHECKSUM` zerado e todos os bytes do `PAYLOAD`. Em `ACK`, cobrirá os 6 bytes do pacote, também com `CHECKSUM` zerado. Cabeçalhos IP e UDP não entrarão nessa soma.
2. Agrupar os bytes em palavras de 16 bits em big-endian. Se a quantidade de bytes for ímpar, acrescentar um byte zero à direita apenas para o cálculo. Esse preenchimento não será enviado e não entrará em `LEN`.
3. Somar as palavras. Sempre que houver transporte além dos 16 bits, somá-lo de volta aos 16 bits inferiores, repetindo até não restar transporte.
4. Inverter os 16 bits do resultado e gravar o valor no campo `CHECKSUM`, em big-endian.

Na leitura por `parse_packet`, a mesma soma com transporte circular é feita sobre o pacote inteiro, desta vez incluindo o checksum recebido, sem zerá-lo. O byte zero de preenchimento é considerado novamente quando o tamanho é ímpar. O resultado deve ser `0xFFFF`; de forma equivalente, seu complemento deve ser `0x0000`. O parser aplica essa verificação a `DATA` e `ACK` e rejeita campos inválidos, pacotes truncados e bytes extras com `ValueError`. Os pacotes de handshake não recebem checksum.

Nos dois modos, só um pacote com checksum válido e campos coerentes pode ser aceito ou confirmado. O servidor valida os DATA e o cliente valida os ACKs com `parse_packet`, além de conferir a origem e as sequências permitidas pela sessão.

---

## 5. Transferência sem erros ou perdas

Depois do handshake, o cliente envia os pacotes `DATA` preparados conforme a seção 4.1. O servidor recebe apenas da sessão ativa. No modo individual e em GBN, aceita somente a sequência esperada, começando em zero. Em SR, também aceita fragmentos adiantados dentro da janela de recepção e os armazena por sequência. Antes de armazenar e confirmar cada fragmento, confere o formato, o checksum e o limite total de caracteres negociado. Pacotes inválidos, de outra origem, duplicados ou fora do intervalo permitido são descartados sem ACK e sem acrescentar conteúdo ou contar caracteres novamente.

O servidor exibe sequência, `LAST`, comprimento e checksum dos DATA recebidos; o cliente exibe sequência e checksum dos ACKs recebidos. Um ACK só permite confirmar dados se vier do endereço do servidor, tiver tipo e checksum válidos e se referir a uma sequência já enviada. ACKs antigos ou repetidos não fazem a base retroceder nem liberam espaço adicional. O cliente resolve `localhost` para conferir esse endereço.

### 5.1 Janela e avanço

O servidor anuncia a janela configurada, de 1 a 5, no `HELLO_ACK`. No modo individual, o cliente mantém apenas um pacote sem confirmação: envia o fragmento `n`, aguarda seu ACK e só então envia `n + 1`. O comportamento é o mesmo com estratégia GBN ou SR.

A base da janela em batch é o menor número de sequência ainda não confirmado. O cliente preenche o intervalo de `base` até `base + WINDOW - 1`, limitado ao último fragmento da mensagem, antes de aguardar ACKs. Cada DATA é enviado uma única vez. Conforme a base avança, os novos fragmentos liberados são enviados sem esperar a confirmação do lote inteiro.

- Em GBN, `ACK n` confirma tudo até `n`, inclusive, e a base avança para `n + 1`, se esse ACK trouxer novas confirmações. O servidor pode emitir um ACK a cada avanço da sequência contígua recebida.
- Em SR, cada ACK marca apenas seu fragmento como confirmado. A base avança pelos fragmentos consecutivos já confirmados; um ACK de sequência maior, sozinho, não permite pular uma lacuna nem enviar além de `base + WINDOW - 1`.

Na recepção SR, a base é a primeira sequência ainda não recebida. O servidor aceita novos fragmentos no intervalo de `base` até `base + WINDOW - 1`, confirma cada um individualmente e avança a base pelas sequências consecutivas já armazenadas. Há no máximo `WINDOW` pacotes pendentes no cliente, todos dentro do intervalo permitido. A recuperação por retransmissão está definida na seção 8 e será implementada no CP3.

### 5.2 Conclusão da mensagem

No modo individual, o servidor aceita `LAST = 1` apenas na sequência esperada, depois de ter aceitado todos os fragmentos anteriores. Envia o ACK final e apresenta o texto reconstruído, preservando o conteúdo original. Em seguida, descarta o estado da sessão e volta a aguardar `HELLO`. O servidor atende sessões sequencialmente, sem concorrência.

Em batch, `LAST = 1` informa a sequência final, mas a mensagem só está completa quando todos os fragmentos de zero até essa sequência tiverem sido recebidos com checksum válido, respeitando `MAX_TEXT`. Em SR, o último fragmento pode ser armazenado e confirmado antes dos anteriores; o servidor aguarda as lacunas serem preenchidas e reconstrói o texto em ordem antes de apresentá-lo.

O cliente individual só informa a transferência concluída após receber o ACK válido do último fragmento. Em batch, SR exige um ACK para cada sequência, enquanto GBN usa o ACK cumulativo da sequência final. Não há mensagem adicional de encerramento: o marcador `LAST` e os ACKs são suficientes para esse fluxo. Ao concluir, o servidor descarta o estado e volta a aguardar `HELLO`.

### 5.3 Espera e encerramento por timeout

O cliente individual espera até cinco segundos pelo ACK de cada DATA. Em batch, espera até cinco segundos sem novas confirmações. Se o prazo expirar, encerra com status de erro, sem reenviar pacotes. Pacotes inválidos, ACKs de sequências não enviadas e confirmações antigas ou repetidas não renovam esse prazo.

O servidor encerra uma sessão após cinco segundos sem aceitar novos fragmentos, descarta o texto incompleto e volta a aguardar `HELLO`. Esse prazo também libera uma sessão que tenha feito apenas o handshake, pois o protocolo não informa se o cliente tem texto a enviar. Pacotes inválidos, repetidos ou de outras origens não renovam a espera. O timeout do socket é removido ao encerrar a sessão para permitir a próxima comunicação.

---

## 6. Exemplos de preparação e transferência

### 6.1 Texto “REDE LOCAL”

Com `MAX_TEXT = 30`, a mensagem de dez caracteres está dentro do limite e é dividida assim. As aspas apenas delimitam os fragmentos; o espaço inicial de `" LOC"` faz parte do texto.

| SEQ | Fragmento | Caracteres | LEN em bytes UTF-8 | LAST | Tamanho do DATA |
|---|---|---|---|---|---|
| 0 | `"REDE"` | 4 | 4 | 0 | 12 bytes |
| 1 | `" LOC"` | 4 | 4 | 0 | 12 bytes |
| 2 | `"AL"` | 2 | 2 | 1 | 10 bytes |

Cada `DATA` usa `TYPE = 0x04` e seu próprio checksum. Cada ACK usa `TYPE = 0x05`, checksum próprio e tamanho de 6 bytes.

No modo individual, o fluxo é `DATA 0 -> ACK 0`, depois `DATA 1 -> ACK 1` e `DATA 2 -> ACK 2`. O servidor apresenta “REDE LOCAL” após aceitar DATA 2 e enviar ACK 2; o cliente conclui ao receber esse ACK. Esse fluxo pode ser executado com `python src/client.py --mode individual --text "REDE LOCAL"`.

Em batch com janela de cinco, os três fragmentos são enviados antes da primeira espera por ACK. Em SR, os ACKs 0, 1 e 2 confirmam os respectivos fragmentos; em GBN, esses mesmos ACKs confirmam cumulativamente até 0, até 1 e até 2.

### 6.2 Texto com acentos: “AÇÃO”

Usando `Ç` e `Ã` como pontos de código únicos, “AÇÃO” tem quatro caracteres e forma um único fragmento. Em UTF-8, seus bytes são `41 C3 87 C3 83 4F`: `A` e `O` ocupam um byte cada, e `Ç` e `Ã`, dois bytes cada.

Esse `DATA` tem `SEQ = 0`, `LAST = 1` e `LEN = 6`, totalizando 14 bytes com o cabeçalho. Para `MAX_TEXT`, o texto conta como quatro caracteres; para `LEN` e o checksum, o payload tem seis bytes. No modo individual, `ACK 0` confirma o fragmento e conclui a transferência.

### 6.3 Oito fragmentos com janela de cinco

O texto `ABCDEFGHIJKLMNOPQRSTUVWXYZ1234` tem 30 caracteres e produz oito fragmentos. Com `WINDOW = 5`, o cliente envia DATA 0 a DATA 4 antes de aguardar ACKs. Quando ACK 0 libera a base, envia DATA 5.

Em GBN, ACK 2 confirma DATA 0, 1 e 2, avança a base para três e permite enviar até DATA 7. Em SR, ACK 2 confirma apenas DATA 2; se ACK 0 ainda não chegou, a base permanece em zero e DATA 5 continua fora da janela.

---

## 7. Sessão e estados

Uma sessão transporta uma mensagem e é identificada pelo IP e pela porta UDP do cliente no socket do servidor. O cliente usa o mesmo socket do `HELLO` até a última confirmação. A sequência começa em zero em cada sessão e não dá a volta durante uma mensagem. O modo, a estratégia, `MAX_TEXT` e `WINDOW` permanecem constantes.

| Estado do cliente | Evento | Ação e próximo estado |
|---|---|---|
| Preparação | Parâmetros e texto válidos | Preparar DATA, enviar `HELLO` e aguardar `HELLO_ACK` |
| Espera de `HELLO_ACK` | Resposta válida do servidor | Enviar `READY` e iniciar a transferência; sem texto, encerrar |
| Espera de `HELLO_ACK` | Timeout ou resposta inválida | Encerrar com erro |
| Transferência | ACK com nova confirmação | Atualizar confirmações e enviar os fragmentos liberados pela janela |
| Transferência | Todos os fragmentos confirmados | Informar conclusão e fechar o socket |
| Transferência | Timeout | No CP2, encerrar com erro; no CP3, aplicar a seção 8.2 |
| Transferência | NAK válido | Apenas no CP3, aplicar a seção 8.2 |

Durante a transferência, respostas inválidas ou de outra origem são ignoradas, sem alterar confirmações ou renovar temporizadores.

| Estado do servidor | Evento | Ação e próximo estado |
|---|---|---|
| Espera de `HELLO` | `HELLO` válido | Registrar parâmetros e origem, enviar `HELLO_ACK` e aguardar `READY` |
| Espera de `READY` | `READY` válido da mesma origem | Iniciar recepção da mensagem |
| Espera de `READY` | Timeout | Liberar a sessão e aguardar `HELLO` |
| Recepção | Novo DATA válido e permitido | Armazenar, confirmar e avançar a recepção conforme o modo |
| Recepção | Mensagem completa | Exibir o texto uma vez e voltar a aguardar `HELLO`; no CP3, preservar o registro descrito na seção 8.4 |
| Recepção | Timeout da sessão | Descartar o texto incompleto e aguardar `HELLO` |

O servidor mantém uma transferência ativa por vez. Pacotes sem transição prevista são descartados; durante uma sessão, outra origem não substitui o cliente atual. No CP3, DATA corrompido, fora de ordem ou repetido segue as regras da seção 8.3.

## 8. Recuperação de erros e perdas — implementação no CP3

Estas regras completam a especificação exigida no CP2. O código atual encerra a transferência no timeout, descarta duplicatas sem ACK e não reconhece `NAK`. No CP3, esses comportamentos serão substituídos pelos definidos a seguir, preservando os formatos existentes de `DATA` e `ACK`.

### 8.1 NAK (Servidor -> Cliente)

O NAK informa que o servidor detectou corrupção e solicita o primeiro fragmento que ainda falta para completar a sequência contígua. Tem exatamente 6 bytes, sem payload:

| Campo | Deslocamento | Tamanho | Valor |
|---|---|---|---|
| MAGIC | 0 | 1 byte | `0xAA` |
| TYPE | 1 | 1 byte | `0x06` (`NAK`) |
| SEQ | 2 | 2 bytes | Primeira sequência ainda não recebida, de 0 a 16.383, em big-endian |
| CHECKSUM | 4 | 2 bytes | Checksum dos 6 bytes, calculado conforme a seção 4.4 |

O servidor envia NAK quando recebe da origem ativa um datagrama identificável como DATA, com tamanho e `LEN` coerentes, mas checksum incorreto. O número solicitado vem do estado local do receptor, nunca do cabeçalho corrompido. Se não for possível reconhecer o pacote, ele é descartado; o temporizador do cliente garante uma nova tentativa.

O cliente aceita NAK apenas do servidor negociado, com formato e checksum válidos, para uma sequência já enviada e ainda não confirmada. Um NAK não confirma dados nem avança a janela. NAK perdido ou corrompido é tratado pelo timeout, sem confirmação adicional do NAK.

### 8.2 Temporizadores e retransmissão

O prazo de retransmissão é fixo: cinco segundos, medidos com relógio monotônico. Cada DATA admite o envio inicial e até três retransmissões. Se uma nova retransmissão for necessária após esse limite, o cliente informa falha e encerra com status de erro. Um descarte simulado também conta como tentativa de envio.

| Modo | Temporizador | Ao expirar | Ao receber NAK válido |
|---|---|---|---|
| Individual | Um para o DATA pendente, iniciado a cada envio | Reenviar esse DATA | Reenviar esse DATA |
| GBN | Um para a base, iniciado ao enviar o primeiro DATA pendente | Reenviar, em ordem, todos os DATA enviados e ainda não confirmados, a partir da base | Reenviar o mesmo intervalo a partir da base |
| SR | Um por DATA enviado e ainda não confirmado | Reenviar somente o DATA cujo prazo terminou | Reenviar somente a sequência solicitada |

O cliente conserva os bytes corretos dos DATA para reutilizá-los nas retransmissões. Não muda sequência, `LAST`, payload ou checksum. A janela continua limitada ao valor negociado; reenviar não libera espaço nem avança a base.

No modo individual, o ACK esperado cancela o temporizador. Em GBN, um ACK que avança a base reinicia o prazo de cinco segundos para a nova base, se ainda houver dados pendentes; caso contrário, cancela o temporizador. Novos envios dentro de uma janela GBN já ocupada não renovam esse prazo. Em SR, `ACK n` cancela apenas o temporizador de `n`; os demais continuam correndo. Cada retransmissão reinicia o temporizador correspondente e consome uma das três tentativas adicionais, inclusive quando provocada por NAK. ACKs antigos, duplicados ou inválidos não renovam prazos. O cliente processa as confirmações recebidas antes de decidir quais pacotes ainda precisam de reenvio.

Após reenviar por NAK, o cliente ignora novos NAKs para a mesma sequência até receber seu ACK ou ocorrer o próximo timeout. Em GBN, essa limitação vale para a base atual e termina quando ela avança ou seu temporizador expira. Assim, vários pacotes corrompidos que provoquem o mesmo pedido não esgotam as tentativas antes de chegar uma resposta ao reenvio.

No CP3, a sessão de recepção expira após 25 segundos sem aceitar um novo fragmento. Isso permite as quatro tentativas do cliente e a espera pela última resposta, que somam até 20 segundos sem confirmação. Duplicatas e pacotes inválidos não renovam o prazo de recepção. O timeout do handshake continua em cinco segundos. No CP2, permanece o timeout de cinco segundos da seção 5.3.

### 8.3 Recepção, duplicatas e ordem

O receptor só armazena DATA com formato, checksum, conteúdo e sequência válidos para a sessão. Cada fragmento conta uma única vez para `MAX_TEXT`. Depois de conhecido o último fragmento, não aceita outra posição final nem fragmentos posteriores a ela.

| Situação | Individual | GBN | SR |
|---|---|---|---|
| Próximo fragmento esperado | Armazenar e enviar ACK da sequência | Armazenar e enviar ACK da maior sequência contígua | Armazenar, enviar ACK da sequência e avançar a base pelas posições já recebidas |
| Fragmento adiantado | Descartar | Descartar e repetir o ACK da maior sequência contígua, se houver | Armazenar e confirmar se estiver na janela; fora dela, descartar |
| Duplicata de fragmento aceito | Repetir seu ACK | Repetir o ACK da maior sequência contígua | Repetir seu ACK, inclusive se estiver antes da base atual |
| DATA com checksum incorreto | Descartar e enviar NAK conforme a seção 8.1 | Mesmo procedimento | Mesmo procedimento |

Uma duplicata deve ter a mesma sequência, `LAST` e payload do fragmento armazenado. Conteúdo diferente na mesma posição é descartado. Nenhuma duplicata é acrescentada ao texto novamente. Não existe `ACK -1`: se GBN ainda não recebeu DATA 0, descarta um fragmento adiantado sem ACK e aguarda o reenvio de DATA 0. ACKs repetidos, por si só, não provocam retransmissão no cliente.

Por exemplo, se DATA 1 se perder em uma janela com DATA 0 a 4, GBN descarta DATA 2 a 4 e o cliente reenvia os pendentes a partir de 1 após o timeout. Em SR, o servidor guarda e confirma DATA 2 a 4, e o cliente reenvia apenas DATA 1. Se DATA 1 chegar corrompido, o NAK pode antecipar essa recuperação.

### 8.4 Última confirmação e encerramento

O cliente só informa sucesso quando todos os fragmentos estiverem confirmados. O servidor apresenta o texto assim que o tiver completo, uma única vez. Não há pacote `FIN` nem confirmação de ACK.

Para recuperar uma confirmação perdida após completar a mensagem, o servidor preserva por 25 segundos um registro da sessão concluída: origem, modo, estratégia e fragmentos aceitos. O prazo começa na conclusão e não é renovado. Durante esse período, uma duplicata válida recebe novamente seu ACK no modo individual ou SR, ou o ACK cumulativo final em GBN. Isso também cobre um ACK anterior perdido em SR, mesmo que o último fragmento já tenha sido confirmado. O texto não é exibido novamente.

Esse registro não ocupa a transferência ativa: o servidor pode atender outro cliente, de outra porta UDP, enquanto responde a duplicatas da sessão concluída. Um `HELLO` da mesma origem ainda retida é ignorado. Cada nova mensagem usa um novo socket e uma porta que não esteja em retenção; a alternativa é aguardar o prazo antes de reutilizar a origem. Após 25 segundos, o registro é removido. A identificação por IP e porta pressupõe esse intervalo entre reutilizações e não cobre datagramas antigos que sobrevivam além dele.

Se todas as confirmações se perderem até esgotar as tentativas, o cliente informa falha, mesmo que o servidor já tenha exibido o texto. O protocolo não promete distinguir esse caso de uma mensagem que não chegou ao destino.

## 9. Simulação determinística — implementação no CP3

A simulação será configurada no cliente e ficará desativada por padrão. Cada regra indica o tipo de pacote (`DATA`, `ACK` ou `NAK`), a sequência, a ocorrência a partir de 1 e a ação (`perder` ou `corromper`). Para DATA, ocorrência é a tentativa de envio; para ACK e NAK, é a chegada de uma resposta válida daquele tipo e sequência, antes de aplicar a falha. A regra afeta somente a ocorrência indicada; para repetir a falha, é preciso indicar outras ocorrências. Regras conflitantes para o mesmo evento são rejeitadas antes do handshake.

- **Perda de DATA:** o cliente registra a tentativa e inicia o temporizador, mas não envia o datagrama.
- **Corrupção de DATA:** o cliente altera o bit menos significativo do primeiro byte do payload de uma cópia do pacote, depois de calcular o checksum, sem recalculá-lo. O pacote original permanece disponível para reenvio.
- **Perda de ACK ou NAK:** o cliente recebe a resposta, identifica a regra e a descarta antes de atualizar o estado do protocolo.
- **Corrupção de ACK ou NAK:** o cliente altera o bit menos significativo do último byte do checksum de uma cópia da resposta, antes da validação usada para aceitá-la. A verificação rejeita essa cópia.

A perda e a corrupção de respostas são simuladas na entrada do cliente; não precisam de comandos extras ao servidor nem de novos campos no handshake. Uma resposta já inválida é descartada sem consumir uma ocorrência. O registro de cada falha inclui tipo, sequência, ocorrência e ação. Os logs também mostram o motivo de cada reenvio, para permitir repetir e explicar o experimento.

| Regra de exemplo | Resultado esperado |
|---|---|
| Perder DATA 1 no primeiro envio | Recuperação por timeout; reenvio dos pendentes em GBN ou somente de DATA 1 em SR |
| Corromper DATA 1 no primeiro envio | Rejeição por checksum; NAK solicita a primeira lacuna e antecipa o reenvio quando ainda necessário |
| Perder o primeiro ACK da sequência final | Cliente recupera a confirmação por retransmissão, sem duplicar a entrega do texto |
| Perder as quatro tentativas de DATA 0 | Cliente encerra com erro ao esgotar as tentativas |

## 10. Pontos extras na entrega final

O checksum de 16 bits já é calculado e verificado manualmente. Ele cobre cabeçalho e payload de DATA e ACK; o NAK usará o mesmo cálculo no CP3. Para a entrega final, os testes de alteração de bytes e a simulação de corrupção demonstrarão a detecção e a recuperação. A avaliação do bônus depende também da explicação e da autoria exigidas no enunciado.

A opção de criptografia será a cifra de César, implementada pelo grupo, sem bibliotecas de criptografia. Ficará desativada por padrão. Quando habilitada, cliente e servidor devem ser configurados previamente com a mesma chave inteira de 1 a 25; a chave não é enviada pelo protocolo. Para letras ASCII, `A` a `Z` e `a` a `z`, a posição da letra cifrada é `(posição + chave) mod 26`, preservando maiúsculas e minúsculas. A decifragem subtrai a chave. Espaços, acentos e demais caracteres permanecem iguais. Por exemplo, com chave 3, `REDE LOCAL` vira `UHGH ORFDO`.

O cliente valida o limite do texto original, cifra, fragmenta, codifica em UTF-8 e calcula o checksum. O servidor valida o checksum dos bytes recebidos, reconstrói o texto cifrado e só então decifra para exibição. A transformação preserva a quantidade de caracteres e os formatos dos pacotes. É uma cifra didática, escolhida para a demonstração do bônus; sua implementação fica para a entrega final.
