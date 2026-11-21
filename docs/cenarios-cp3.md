# Cenários de erros e perdas

Este documento reúne saídas reais do cliente e do servidor com a simulação de falhas da seção 9 da [especificação do protocolo](protocolo.md). Os temporizadores usam os valores padrão, então cada perda recuperada por timeout leva cerca de cinco segundos.

Em todos os cenários, o servidor foi iniciado com `python src/server.py` e janela 5. As linhas do handshake foram omitidas para facilitar a leitura.

## 1. Perda de DATA no modo individual

O DATA 1 não chega ao servidor. Depois de cinco segundos sem ACK, o cliente retransmite o mesmo pacote e a transferência continua.

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

## 2. Perda de DATA em Go-Back-N

O servidor descarta DATA 2 e 3 por estarem fora de ordem e repete o ACK cumulativo 0. Quando o temporizador da base expira, o cliente reenvia tudo a partir de DATA 1.

```bash
python src/client.py --mode batch --strategy gbn --text "REDE LOCAL TESTE" --fault DATA:1:1:perder
```

**Cliente:**

```
[CLIENT] Pacotes DATA preparados: 4
[CLIENT] DATA enviado (seq=0, tentativa=1)
[CLIENT] DATA enviado (seq=1, tentativa=1)
[FAULT] perder DATA 1 (ocorrência 1)
[CLIENT] DATA enviado (seq=2, tentativa=1)
[CLIENT] DATA enviado (seq=3, tentativa=1)
[CLIENT] ACK recebido (seq=0, checksum=0x55FA)
[CLIENT] Janela avançou (base=1, window=5)
[CLIENT] ACK recebido (seq=0, checksum=0x55FA)
[CLIENT] ACK 0 sem nova confirmação ignorado
[CLIENT] ACK recebido (seq=0, checksum=0x55FA)
[CLIENT] ACK 0 sem nova confirmação ignorado
[CLIENT] Timeout da base 1
[CLIENT] DATA retransmitido por timeout (seq=1, tentativa=2)
[CLIENT] DATA retransmitido por timeout (seq=2, tentativa=2)
[CLIENT] DATA retransmitido por timeout (seq=3, tentativa=2)
[CLIENT] ACK recebido (seq=1, checksum=0x55F9)
[CLIENT] Janela avançou (base=2, window=5)
[CLIENT] ACK recebido (seq=2, checksum=0x55F8)
[CLIENT] Janela avançou (base=3, window=5)
[CLIENT] ACK recebido (seq=3, checksum=0x55F7)
[CLIENT] Janela avançou (base=4, window=5)
[CLIENT] Transferência concluída: todos os fragmentos confirmados
```

**Servidor:**

```
[SERVER] DATA recebido (seq=0, LAST=0, LEN=4, checksum=0xBF6C)
[SERVER] ACK 0 enviado
[SERVER] DATA recebido (seq=2, LAST=0, LEN=4, checksum=0xF454)
[SERVER] DATA 2 fora da janela ou já recebido descartado (base=1)
[SERVER] ACK 0 enviado
[SERVER] DATA recebido (seq=3, LAST=1, LEN=4, checksum=0xBB5B)
[SERVER] DATA 3 fora da janela ou já recebido descartado (base=1)
[SERVER] ACK 0 enviado
[SERVER] DATA recebido (seq=1, LAST=0, LEN=4, checksum=0xE666)
[SERVER] ACK 1 enviado
[SERVER] DATA recebido (seq=2, LAST=0, LEN=4, checksum=0xF454)
[SERVER] ACK 2 enviado
[SERVER] DATA recebido (seq=3, LAST=1, LEN=4, checksum=0xBB5B)
[SERVER] ACK 3 enviado
[SERVER] Mensagem reconstruída: REDE LOCAL TESTE
```

## 3. Perda de DATA em Repetição Seletiva

O servidor guarda e confirma DATA 2 e 3 mesmo com a lacuna. Só o DATA 1 expira e é retransmitido.

```bash
python src/client.py --mode batch --strategy sr --text "REDE LOCAL TESTE" --fault DATA:1:1:perder
```

**Cliente:**

```
[CLIENT] Pacotes DATA preparados: 4
[CLIENT] DATA enviado (seq=0, tentativa=1)
[CLIENT] DATA enviado (seq=1, tentativa=1)
[FAULT] perder DATA 1 (ocorrência 1)
[CLIENT] DATA enviado (seq=2, tentativa=1)
[CLIENT] DATA enviado (seq=3, tentativa=1)
[CLIENT] ACK recebido (seq=0, checksum=0x55FA)
[CLIENT] Janela avançou (base=1, window=5)
[CLIENT] ACK recebido (seq=2, checksum=0x55F8)
[CLIENT] ACK recebido (seq=3, checksum=0x55F7)
[CLIENT] Timeout de DATA 1
[CLIENT] DATA retransmitido por timeout (seq=1, tentativa=2)
[CLIENT] ACK recebido (seq=1, checksum=0x55F9)
[CLIENT] Janela avançou (base=4, window=5)
[CLIENT] Transferência concluída: todos os fragmentos confirmados
```

**Servidor:**

```
[SERVER] DATA recebido (seq=0, LAST=0, LEN=4, checksum=0xBF6C)
[SERVER] ACK 0 enviado
[SERVER] DATA recebido (seq=2, LAST=0, LEN=4, checksum=0xF454)
[SERVER] ACK 2 enviado
[SERVER] DATA recebido (seq=3, LAST=1, LEN=4, checksum=0xBB5B)
[SERVER] ACK 3 enviado
[SERVER] DATA recebido (seq=1, LAST=0, LEN=4, checksum=0xE666)
[SERVER] ACK 1 enviado
[SERVER] Mensagem reconstruída: REDE LOCAL TESTE
```

## 4. Corrupção de DATA em Go-Back-N

O servidor detecta o checksum incorreto e envia NAK 1, que antecipa o reenvio da janela a partir da base, sem esperar o timeout.

```bash
python src/client.py --mode batch --strategy gbn --text "REDE LOCAL TESTE" --fault DATA:1:1:corromper
```

**Cliente:**

```
[CLIENT] Pacotes DATA preparados: 4
[CLIENT] DATA enviado (seq=0, tentativa=1)
[CLIENT] DATA enviado (seq=1, tentativa=1)
[FAULT] corromper DATA 1 (ocorrência 1)
[CLIENT] DATA enviado (seq=2, tentativa=1)
[CLIENT] DATA enviado (seq=3, tentativa=1)
[CLIENT] ACK recebido (seq=0, checksum=0x55FA)
[CLIENT] Janela avançou (base=1, window=5)
[CLIENT] NAK recebido (seq=1, checksum=0x55F8)
[CLIENT] DATA retransmitido por NAK (seq=1, tentativa=2)
[CLIENT] DATA retransmitido por NAK (seq=2, tentativa=2)
[CLIENT] DATA retransmitido por NAK (seq=3, tentativa=2)
[CLIENT] ACK recebido (seq=0, checksum=0x55FA)
[CLIENT] ACK 0 sem nova confirmação ignorado
[CLIENT] ACK recebido (seq=0, checksum=0x55FA)
[CLIENT] ACK 0 sem nova confirmação ignorado
[CLIENT] ACK recebido (seq=1, checksum=0x55F9)
[CLIENT] Janela avançou (base=2, window=5)
[CLIENT] ACK recebido (seq=2, checksum=0x55F8)
[CLIENT] Janela avançou (base=3, window=5)
[CLIENT] ACK recebido (seq=3, checksum=0x55F7)
[CLIENT] Janela avançou (base=4, window=5)
[CLIENT] Transferência concluída: todos os fragmentos confirmados
```

**Servidor:**

```
[SERVER] DATA recebido (seq=0, LAST=0, LEN=4, checksum=0xBF6C)
[SERVER] ACK 0 enviado
[SERVER] Checksum de DATA inválido; NAK 1 enviado
[SERVER] DATA recebido (seq=2, LAST=0, LEN=4, checksum=0xF454)
[SERVER] DATA 2 fora da janela ou já recebido descartado (base=1)
[SERVER] ACK 0 enviado
[SERVER] DATA recebido (seq=3, LAST=1, LEN=4, checksum=0xBB5B)
[SERVER] DATA 3 fora da janela ou já recebido descartado (base=1)
[SERVER] ACK 0 enviado
[SERVER] DATA recebido (seq=1, LAST=0, LEN=4, checksum=0xE666)
[SERVER] ACK 1 enviado
[SERVER] DATA recebido (seq=2, LAST=0, LEN=4, checksum=0xF454)
[SERVER] ACK 2 enviado
[SERVER] DATA recebido (seq=3, LAST=1, LEN=4, checksum=0xBB5B)
[SERVER] ACK 3 enviado
[SERVER] Mensagem reconstruída: REDE LOCAL TESTE
```

## 5. Corrupção de DATA em Repetição Seletiva

O NAK 1 faz o cliente reenviar somente o DATA 1. Os outros fragmentos já tinham sido confirmados individualmente.

```bash
python src/client.py --mode batch --strategy sr --text "REDE LOCAL TESTE" --fault DATA:1:1:corromper
```

**Cliente:**

```
[CLIENT] Pacotes DATA preparados: 4
[CLIENT] DATA enviado (seq=0, tentativa=1)
[CLIENT] DATA enviado (seq=1, tentativa=1)
[FAULT] corromper DATA 1 (ocorrência 1)
[CLIENT] DATA enviado (seq=2, tentativa=1)
[CLIENT] DATA enviado (seq=3, tentativa=1)
[CLIENT] ACK recebido (seq=0, checksum=0x55FA)
[CLIENT] Janela avançou (base=1, window=5)
[CLIENT] NAK recebido (seq=1, checksum=0x55F8)
[CLIENT] DATA retransmitido por NAK (seq=1, tentativa=2)
[CLIENT] ACK recebido (seq=2, checksum=0x55F8)
[CLIENT] ACK recebido (seq=3, checksum=0x55F7)
[CLIENT] ACK recebido (seq=1, checksum=0x55F9)
[CLIENT] Janela avançou (base=4, window=5)
[CLIENT] Transferência concluída: todos os fragmentos confirmados
```

**Servidor:**

```
[SERVER] DATA recebido (seq=0, LAST=0, LEN=4, checksum=0xBF6C)
[SERVER] ACK 0 enviado
[SERVER] Checksum de DATA inválido; NAK 1 enviado
[SERVER] DATA recebido (seq=2, LAST=0, LEN=4, checksum=0xF454)
[SERVER] ACK 2 enviado
[SERVER] DATA recebido (seq=3, LAST=1, LEN=4, checksum=0xBB5B)
[SERVER] ACK 3 enviado
[SERVER] DATA recebido (seq=1, LAST=0, LEN=4, checksum=0xE666)
[SERVER] ACK 1 enviado
[SERVER] Mensagem reconstruída: REDE LOCAL TESTE
```

## 6. Perda do último ACK

O servidor já exibiu o texto, mas o ACK 2 se perde. O cliente retransmite DATA 2 e o servidor, usando o registro da sessão concluída, reenvia o ACK sem exibir a mensagem de novo.

```bash
python src/client.py --mode batch --strategy sr --text "REDE LOCAL" --fault ACK:2:1:perder
```

**Cliente:**

```
[CLIENT] Pacotes DATA preparados: 3
[CLIENT] DATA enviado (seq=0, tentativa=1)
[CLIENT] DATA enviado (seq=1, tentativa=1)
[CLIENT] DATA enviado (seq=2, tentativa=1)
[CLIENT] ACK recebido (seq=0, checksum=0x55FA)
[CLIENT] Janela avançou (base=1, window=5)
[CLIENT] ACK recebido (seq=1, checksum=0x55F9)
[CLIENT] Janela avançou (base=2, window=5)
[FAULT] perder ACK 2 (ocorrência 1)
[CLIENT] Timeout de DATA 2
[CLIENT] DATA retransmitido por timeout (seq=2, tentativa=2)
[CLIENT] ACK recebido (seq=2, checksum=0x55F8)
[CLIENT] Janela avançou (base=3, window=5)
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
[SERVER] Duplicata de sessão concluída; ACK 2 reenviado
```

## 7. Corrupção de ACK em Go-Back-N

O ACK 1 corrompido é rejeitado pelo checksum. Como o ACK 2 é cumulativo, ele confirma também o fragmento 1 e não há retransmissão.

```bash
python src/client.py --mode batch --strategy gbn --text "REDE LOCAL" --fault ACK:1:1:corromper
```

**Cliente:**

```
[CLIENT] Pacotes DATA preparados: 3
[CLIENT] DATA enviado (seq=0, tentativa=1)
[CLIENT] DATA enviado (seq=1, tentativa=1)
[CLIENT] DATA enviado (seq=2, tentativa=1)
[CLIENT] ACK recebido (seq=0, checksum=0x55FA)
[CLIENT] Janela avançou (base=1, window=5)
[FAULT] corromper ACK 1 (ocorrência 1)
[CLIENT] Pacote descartado: Checksum de ACK inválido
[CLIENT] ACK recebido (seq=2, checksum=0x55F8)
[CLIENT] Janela avançou (base=3, window=5)
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

## 8. Corrupção de DATA com perda do NAK

O NAK que pediria o reenvio se perde, e o temporizador garante a recuperação.

```bash
python src/client.py --mode individual --text "REDE" --fault DATA:0:1:corromper --fault NAK:0:1:perder
```

**Cliente:**

```
[CLIENT] Pacotes DATA preparados: 1
[CLIENT] DATA enviado (seq=0, tentativa=1)
[FAULT] corromper DATA 0 (ocorrência 1)
[FAULT] perder NAK 0 (ocorrência 1)
[CLIENT] Timeout de DATA 0
[CLIENT] DATA retransmitido por timeout (seq=0, tentativa=2)
[CLIENT] ACK recebido (seq=0, checksum=0x55FA)
[CLIENT] Janela avançou (base=1, window=1)
[CLIENT] Transferência concluída: todos os fragmentos confirmados
```

**Servidor:**

```
[SERVER] Checksum de DATA inválido; NAK 0 enviado
[SERVER] DATA recebido (seq=0, LAST=1, LEN=4, checksum=0xBE6C)
[SERVER] ACK 0 enviado
[SERVER] Mensagem reconstruída: REDE
```

## 9. Esgotamento das tentativas

Todas as quatro tentativas de DATA 0 se perdem. O cliente desiste após três retransmissões e encerra com código de saída 1. O servidor nunca recebe o fragmento.

```bash
python src/client.py --mode individual --text "A" --fault DATA:0:1:perder --fault DATA:0:2:perder --fault DATA:0:3:perder --fault DATA:0:4:perder
```

**Cliente:**

```
[CLIENT] Pacotes DATA preparados: 1
[CLIENT] DATA enviado (seq=0, tentativa=1)
[FAULT] perder DATA 0 (ocorrência 1)
[CLIENT] Timeout de DATA 0
[CLIENT] DATA retransmitido por timeout (seq=0, tentativa=2)
[FAULT] perder DATA 0 (ocorrência 2)
[CLIENT] Timeout de DATA 0
[CLIENT] DATA retransmitido por timeout (seq=0, tentativa=3)
[FAULT] perder DATA 0 (ocorrência 3)
[CLIENT] Timeout de DATA 0
[CLIENT] DATA retransmitido por timeout (seq=0, tentativa=4)
[FAULT] perder DATA 0 (ocorrência 4)
[CLIENT] Timeout de DATA 0
[CLIENT] Falha: DATA 0 sem confirmação após 3 retransmissões
```

## 10. Cifra de César

Com a mesma chave nas duas pontas, o cliente cifra o texto antes de fragmentar e o servidor decifra depois de reconstruir. O texto cifrado é o que trafega nos pacotes.

```bash
python src/server.py --key 3
python src/client.py --mode batch --strategy sr --text "REDE LOCAL" --key 3
```

**Cliente:**

```
[CLIENT] Pacotes DATA preparados: 3
[CLIENT] Texto cifrado com César (chave=3): UHGH ORFDO
[CLIENT] DATA enviado (seq=0, tentativa=1)
[CLIENT] DATA enviado (seq=1, tentativa=1)
[CLIENT] DATA enviado (seq=2, tentativa=1)
[CLIENT] ACK recebido (seq=0, checksum=0x55FA)
[CLIENT] Janela avançou (base=1, window=5)
[CLIENT] ACK recebido (seq=1, checksum=0x55F9)
[CLIENT] Janela avançou (base=2, window=5)
[CLIENT] ACK recebido (seq=2, checksum=0x55F8)
[CLIENT] Janela avançou (base=3, window=5)
[CLIENT] Transferência concluída: todos os fragmentos confirmados
```

**Servidor:**

```
[SERVER] DATA recebido (seq=0, LAST=0, LEN=4, checksum=0xB966)
[SERVER] ACK 0 enviado
[SERVER] DATA recebido (seq=1, LAST=0, LEN=4, checksum=0xE360)
[SERVER] ACK 1 enviado
[SERVER] DATA recebido (seq=2, LAST=1, LEN=2, checksum=0x10A8)
[SERVER] ACK 2 enviado
[SERVER] Texto cifrado recebido: UHGH ORFDO
[SERVER] Mensagem reconstruída: REDE LOCAL
```
