# Especificação do protocolo

Este documento descreve o handshake implementado no CP1 e os pacotes `DATA` e `ACK`, com checksum e validação dos campos. A transferência individual de texto sem erros ou perdas está implementada. Em batch, apenas o handshake e a preparação dos pacotes estão implementados; o fluxo de transferência segue especificado para uma próxima etapa. O CP2 permanece pendente.

## 1. Visão geral e parâmetros

A comunicação usa sockets UDP. No início de cada sessão, o cliente informa o modo de operação, a estratégia e o limite do texto; o servidor responde com o tamanho da janela.

| Parâmetro | Valor | Detalhes |
|---|---|---|
| Transporte | UDP (`SOCK_DGRAM`) | O projeto implementará as regras de transporte confiável na camada de aplicação |
| Porta padrão | 50000 | Configurável via `--port` |
| Ordem dos bytes | Big-endian | Usada nos campos com mais de um byte |
| Modo de operação | `0` (Individual), `1` (Batch) | Definido no campo `MODE` do `HELLO` |
| Estratégia de retransmissão | `0` (Go-Back-N), `1` (Repetição Seletiva) | Definido no campo `STRATEGY` do `HELLO` |
| Payload máximo | 4 pontos de código Unicode, até 16 bytes em UTF-8 | Texto fragmentado antes da codificação; limite validado por pacote `DATA` |
| Limite máximo do texto | Padrão 30 caracteres; configurável de 30 a 65.535 | Informado no campo `MAX_TEXT` de 2 bytes do `HELLO` |
| Janela de recepção | 1 a 5; fixada em 5 no CP1 e nesta especificação do CP2 | Enviada pelo servidor no `HELLO_ACK` |
| Buffer do socket | 1024 bytes | Constante `BUFSIZE` |
| Timeout do cliente | 5.0 segundos | Espera por `HELLO_ACK` e por cada ACK de DATA |
| Timeout de sessão no servidor | 5.0 segundos | Espera por `READY` ou pelo próximo `DATA` válido |

O mínimo de 30 se refere ao limite configurado, não ao tamanho obrigatório da mensagem. Com `MAX_TEXT = 30`, por exemplo, uma mensagem de um caractere está dentro do limite. Para a contagem e a fragmentação, cada caractere corresponde a um ponto de código Unicode.

O cliente valida `--max-text` e, quando informado, `--text` antes de abrir o socket. Valores fora de 30 a 65.535, texto vazio ou acima do limite geram erro. `build_hello` também valida esse intervalo antes de codificar o campo de 2 bytes. Sem `--text`, a execução continua restrita ao handshake; com ele, os pacotes são transferidos no modo individual ou apenas preparados em batch.

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
| `0x04` | `DATA` | Montagem, leitura e transferência individual implementadas; envio em batch pendente |
| `0x05` | `ACK` | Montagem, leitura e confirmação individual implementadas; confirmação em batch pendente |

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

O servidor responde com `HELLO_ACK`, informando o tamanho da janela. No CP1, o valor enviado é sempre 5.

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
| WINDOW | 1 byte | unsigned int | Tamanho da janela (1 a 5; fixo em 5 no CP1) |

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

Na versão atual, o modo individual com `--text` continua a transferência pelo mesmo socket. O servidor mantém o endereço e os parâmetros da sessão e só inicia a recepção após um `READY` válido. Em batch, volta a aguardar `HELLO` ao concluir o handshake.

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
   |     MAGIC(0xAA) | 0x02 | WINDOW(5)                         |
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

Esses timeouts encerram a tentativa de handshake. Ainda não há retransmissão automática.

---

## 4. DATA e ACK

As funções `build_data`, `build_ack` e `parse_packet`, em `src/protocol.py`, montam e leem esses pacotes, validando seus campos e checksum. A validação de um pacote não determina se um ACK corresponde a um fragmento enviado nem se a mensagem completa respeita o `MAX_TEXT` negociado; essas regras dependem da sessão.

As regras desta seção e das seguintes definem a transferência de uma mensagem de texto não vazia, sem erros ou perdas. A fragmentação, a preparação dos pacotes, a transferência individual por sockets e a reconstrução no servidor estão implementadas. A transferência em batch permanece pendente. Cada datagrama UDP transporta um pacote do protocolo. Os formatos do handshake e seus timeouts de cinco segundos permanecem como descritos nas seções anteriores.

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

O significado de `ACK n` dependerá do modo e da estratégia negociados:

| Modo / estratégia | Significado de ACK n |
|---|---|
| Individual, com qualquer estratégia informada no handshake | Confirma somente o fragmento `n` |
| Batch com Repetição Seletiva (SR) | Confirma somente o fragmento `n` |
| Batch com Go-Back-N (GBN) | Confirma todos os fragmentos de `0` até `n`, inclusive |

Em GBN, o servidor só poderá confirmar `n` quando tiver recebido todos os fragmentos até ele. `ACK 0` confirmará o fragmento zero; o número no ACK nunca representará o próximo fragmento esperado.

### 4.4 Checksum de DATA e ACK

O cálculo manual do checksum de 16 bits em complemento de um e sua verificação estão implementados em `src/protocol.py`, pelas funções `calculate_checksum(data)` e `verify_checksum(data)`, sem usar uma função pronta de checksum. Elas processam os bytes exatamente como recebidos, sem interpretar campos ou tipos de pacote. Os construtores de `DATA` e `ACK` zeram o campo `CHECKSUM` antes de chamar o cálculo, seguindo estas regras:

1. Montar os bytes do pacote com os dois bytes de `CHECKSUM` zerados. Em `DATA`, o cálculo cobrirá `MAGIC`, `TYPE`, `SEQ`, `LAST`, `LEN`, o campo `CHECKSUM` zerado e todos os bytes do `PAYLOAD`. Em `ACK`, cobrirá os 6 bytes do pacote, também com `CHECKSUM` zerado. Cabeçalhos IP e UDP não entrarão nessa soma.
2. Agrupar os bytes em palavras de 16 bits em big-endian. Se a quantidade de bytes for ímpar, acrescentar um byte zero à direita apenas para o cálculo. Esse preenchimento não será enviado e não entrará em `LEN`.
3. Somar as palavras. Sempre que houver transporte além dos 16 bits, somá-lo de volta aos 16 bits inferiores, repetindo até não restar transporte.
4. Inverter os 16 bits do resultado e gravar o valor no campo `CHECKSUM`, em big-endian.

Na leitura por `parse_packet`, a mesma soma com transporte circular é feita sobre o pacote inteiro, desta vez incluindo o checksum recebido, sem zerá-lo. O byte zero de preenchimento é considerado novamente quando o tamanho é ímpar. O resultado deve ser `0xFFFF`; de forma equivalente, seu complemento deve ser `0x0000`. O parser aplica essa verificação a `DATA` e `ACK` e rejeita campos inválidos, pacotes truncados e bytes extras com `ValueError`. Os pacotes de handshake não recebem checksum.

Na transferência individual, só um pacote com checksum válido e campos coerentes pode ser aceito ou confirmado. O servidor valida os DATA e o cliente valida os ACKs com `parse_packet`, além de conferir a origem e a sequência esperadas.

---

## 5. Transferência sem erros ou perdas (individual implementado; batch pendente)

Depois do handshake, o cliente individual envia os pacotes `DATA` preparados conforme a seção 4.1. O servidor recebe apenas da sessão ativa e aceita somente a sequência esperada, começando em zero. Antes de armazenar e confirmar cada fragmento, confere o formato, o checksum e o limite total de caracteres negociado. Pacotes inválidos, de outra origem, duplicados ou fora de ordem são descartados sem ACK e sem acrescentar conteúdo.

O servidor exibe sequência, `LAST`, comprimento e checksum dos DATA recebidos; o cliente exibe sequência e checksum dos ACKs recebidos. Um ACK só permite avançar se vier do endereço do servidor e tiver o tipo, o checksum e a sequência esperados. O cliente resolve `localhost` para conferir esse endereço.

### 5.1 Janela e avanço

O servidor mantém `WINDOW = 5` no `HELLO_ACK`. No modo individual, o cliente mantém apenas um pacote sem confirmação: envia o fragmento `n`, aguarda seu ACK e só então envia `n + 1`. O comportamento é o mesmo com estratégia GBN ou SR.

As regras a seguir para batch ainda não estão implementadas. A base da janela será o menor número de sequência ainda não confirmado. O cliente poderá enviar os fragmentos da base até `base + 4`, limitados ao último fragmento da mensagem. A janela avançará conforme os ACKs chegarem, liberando o envio de novos fragmentos sem precisar esperar a confirmação de todo o lote.

- Em GBN, `ACK n` confirmará tudo até `n`, inclusive, e a base avançará para `n + 1`, se esse ACK trouxer novas confirmações.
- Em SR, cada ACK marcará apenas seu fragmento como confirmado. A base avançará pelos fragmentos consecutivos já confirmados; um ACK de sequência maior, sozinho, não permitirá pular uma lacuna.

Assim, haverá no máximo cinco pacotes pendentes no modo batch, todos dentro da janela. Essas regras descrevem apenas o caminho sem falhas; a recuperação por retransmissão será tratada no CP3.

### 5.2 Conclusão da mensagem

No modo individual, o servidor aceita `LAST = 1` apenas na sequência esperada, depois de ter aceitado todos os fragmentos anteriores. Envia o ACK final e apresenta o texto reconstruído, preservando o conteúdo original. Em seguida, descarta o estado da sessão e volta a aguardar `HELLO`. O servidor atende sessões sequencialmente, sem concorrência.

Na futura recepção em batch, `LAST = 1` informará a sequência final, mas a mensagem só estará completa quando todos os fragmentos de zero até essa sequência tiverem sido recebidos com checksum válido, respeitando `MAX_TEXT`.

O cliente individual só informa a transferência concluída após receber o ACK válido do último fragmento. Na futura transferência em batch, SR exigirá um ACK para cada sequência, enquanto GBN usará o ACK cumulativo da sequência final. Não há mensagem adicional de encerramento: o marcador `LAST` e os ACKs são suficientes para esse fluxo.

### 5.3 Espera e encerramento por timeout

O cliente espera até cinco segundos pelo ACK de cada DATA. Se não receber uma confirmação válida, encerra com status de erro, sem reenviar o pacote. Pacotes inesperados não renovam esse prazo.

O servidor encerra uma sessão individual após cinco segundos sem aceitar o próximo DATA, descarta os fragmentos incompletos e volta a aguardar `HELLO`. Esse prazo também libera uma sessão que tenha feito apenas o handshake, pois o protocolo não informa se o cliente tem texto a enviar. Pacotes inválidos ou de outras origens não renovam a espera. O timeout do socket é removido ao encerrar a sessão para permitir a próxima comunicação.

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

Na futura transferência em batch, os três fragmentos caberão na janela de cinco. Em SR, os ACKs 0, 1 e 2 confirmarão os respectivos fragmentos; em GBN, esses mesmos ACKs confirmarão cumulativamente até 0, até 1 e até 2.

### 6.2 Texto com acentos: “AÇÃO”

Usando `Ç` e `Ã` como pontos de código únicos, “AÇÃO” tem quatro caracteres e forma um único fragmento. Em UTF-8, seus bytes são `41 C3 87 C3 83 4F`: `A` e `O` ocupam um byte cada, e `Ç` e `Ã`, dois bytes cada.

Esse `DATA` tem `SEQ = 0`, `LAST = 1` e `LEN = 6`, totalizando 14 bytes com o cabeçalho. Para `MAX_TEXT`, o texto conta como quatro caracteres; para `LEN` e o checksum, o payload tem seis bytes. No modo individual, `ACK 0` confirma o fragmento e conclui a transferência.
