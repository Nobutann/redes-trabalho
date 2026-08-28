# Especificação do Protocolo — *(nome a definir pelo grupo)*

> Documento vivo: evolui a cada checkpoint. No CP2 o protocolo deve estar
> **integralmente definido**. As marcações ⚠️ indicam decisões pendentes do grupo.

## 1. Visão geral e decisões de projeto

| Decisão | Escolha | Justificativa |
|---|---|---|
| Transporte (socket) | ⚠️ UDP (recomendado) ou TCP | Em UDP, a confiabilidade é 100% responsabilidade do nosso protocolo — alinha com o objetivo do trabalho |
| Modo de operação | individual vs. lote (negociado no handshake) | — |
| Estratégia de confirmação | Go-Back-N vs. Repetição Seletiva (escolha do cliente) | — |
| Tamanho do payload | 4 caracteres (fixo, exigência do trabalho) | — |
| Tamanho máximo do texto | ≥ 30 caracteres, definido dinamicamente no início | — |
| Janela | 1 a 5, determinada pelo servidor; inicial 5 | — |
| Checksum | ⚠️ algoritmo a definir (ex.: soma de complemento-um, CRC16 — implementado à mão para ponto extra) | — |
| Criptografia (extra) | ⚠️ opcional (ex.: Cifra de César implementada à mão) | Pontos extra avaliados só na última entrega |

## 2. Formato dos pacotes

> ⚠️ **Proposta inicial — sujeita a revisão.** Os cabeçalhos são concatenados ao
> payload (máx. 4 caracteres) para formar o pacote final enviado via socket.

### 2.1 Pacote de dados (cliente → servidor)

```
 0                   1                   2                   3
+--------+----------+---------+-----------+----------------------+
| MAGIC  | SEQ      | FLAGS   | CHECKSUM  | PAYLOAD (4 chars)    |
| 1 byte | 1 byte   | 1 byte  | 2 bytes   | 4 bytes              |
+--------+----------+---------+-----------+----------------------+
```

- **MAGIC:** byte fixo para validação rápida de pacote do nosso protocolo
- **SEQ:** número de sequência do pacote (faixa: ⚠️ a definir, ex.: 0–255 com módulo)
- **FLAGS:** bitmask de flags de controle (DATA / ACK / NAK / SYN / FIN / EOT)
- **CHECKSUM:** cobre cabeçalho + payload (⚠️ algoritmo e cobertura a definir)
- **PAYLOAD:** até 4 caracteres do conteúdo da aplicação

### 2.2 Pacote de confirmação (servidor → cliente)

```
+--------+----------+---------+-----------+----------------------+
| MAGIC  | ACK#     | FLAGS   | CHECKSUM  | (reservado/vazio)    |
+--------+----------+---------+-----------+----------------------+
```

- Semântica do ACK# em GBN (próximo esperado — ACK cumulativo) vs. SR
  (ACK individual) — ⚠️ a detalhar por estratégia.

## 3. Handshake (Checkpoint 1)

Trocas mínimas exigidas: **modo de operação**, **tamanho máximo do texto inicial**
e **tamanho da janela**.

> ⚠️ Esboço a validar pelo grupo (exemplo com 2 vias):

```
CLIENTE                              SERVIDOR
   |  --- SYN { modo, max_texto } --->  |
   |  <-- SYN-ACK { janela (1..5) } --  |   (janela definida pelo servidor, inicial 5)
   |  --- ACK ----------------------->  |
   |         (conexão estabelecida)     |
```

- O **cliente** informa o modo de operação (individual/lote; GBN/SR) e o tamanho
  máximo do texto (≥ 30, default 30).
- O **servidor** responde com o tamanho da janela de recepção (1–5, inicial 5).

## 4. Fluxo de transferência (Checkpoint 2 — caminho sem erros)

> ⚠️ A preencher conforme implementação. Pontos a descrever:

1. Fragmentação do texto em pacotes de até 4 caracteres
2. Envio conforme a janela (paralelismo de até `N` mensagens por vez)
3. Confirmações: individuais (SR) ou em grupo (GBN)
4. Encerramento da comunicação (flag EOT/FIN) e apresentação da mensagem completa
   no servidor
5. Formato dos metadados impressos:
   - **Servidor:** por pacote recebido (SEQ, checksum OK, payload, timestamp…)
   - **Cliente:** por confirmação recebida (ACK#, flags, timestamp…)

## 5. Tratamento de erros e perdas (Checkpoint 3)

> ⚠️ A preencher. Pontos a especificar:

- **Simulação de falhas (cliente, determinística):** regras de injeção
  - ⚠️ Proposta: lista de "eventos" configurados antes do envio, ex.:
    `corromper(seq=2)` (altera payload/checksum) e `descartar(seq=4)` (não envia)
- **Detecção pelo servidor:** checksum inválido → NAK/descarte; SEQ fora de
  ordem → tratamento conforme GBN/SR
- **Temporizador (cliente):** valor do timeout, o que retransmitir
  - GBN: retransmitir a janela inteira a partir do pacote não confirmado
  - SR: retransmitir apenas o pacote sem confirmação individual
- **Reconhecimento negativo (NAK):** quando o servidor envia e como o cliente reage

## 6. Máquinas de estado (FSM)

> ⚠️ Descrever (e diagramar) nos moldes da Figura 3.15–3.18 do livro Kurose:
> estados do **remetente** (cliente) e do **destinatário** (servidor) para cada
> estratégia (GBN e SR).

## 7. Mensagens de exemplo

> ⚠️ Exemplos concretos (payloads, bytes, prints esperados) serão adicionados
> conforme o formato for fixado — úteis para o manual de uso e para os testes
> da apresentação.
