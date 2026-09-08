# Requisitos do Trabalho

Requisitos extraídos da especificação oficial do trabalho prático.

## Funcionamento Geral

- **RF1** — Conexão via sockets UDP entre cliente e servidor, em `localhost` ou por IP.
- **RF2** — Envio de mensagens de texto do cliente para o servidor.
- **RF3** — Limite máximo de caracteres do texto definido no handshake, com valor padrão de no mínimo **30 caracteres**.
- **RF4** — Fragmentação do texto em pacotes com **payload de até 4 caracteres**, concatenado aos cabeçalhos do protocolo.
- **RF5** — O servidor imprime os metadados de cada pacote recebido e apresenta a mensagem reconstruída ao final.
- **RF6** — O cliente imprime os metadados das confirmações (ACKs) conforme as recebe.

## Transporte Confiável

Implementação das técnicas de transporte confiável na camada de aplicação:

- **RT1** — Soma de verificação (checksum).
- **RT2** — Temporizador para detecção de perda e retransmissão (timeout).
- **RT3** — Número de sequência nos pacotes.
- **RT4** — Reconhecimento positivo (ACK).
- **RT5** — Reconhecimento negativo (NAK).
- **RT6** — Controle por janela deslizante de tamanho **1 a 5** (iniciado em **5** pelo servidor).

## Modos de Operação e Simulação de Falhas

- **RE1** — Simulação determinística de erros e perdas no remetente (cliente).
- **RE2** — Envio de pacotes de forma isolada (`individual`) ou em lotes (`batch`).
- **RE3** — Servidor capaz de confirmar individualmente ou cumulativamente.
- **RE4** — Suporte aos algoritmos **Go-Back-N** e **Repetição Seletiva** no envio em lote.

## Handshake (CP1)

- **RH1** — Negociação inicial de parâmetros:
  - Modo de operação (individual vs. batch / GBN vs. SR).
  - Tamanho máximo do texto inicial (`max_text >= 30`).
  - Tamanho da janela de recepção (`window` entre 1 e 5).
