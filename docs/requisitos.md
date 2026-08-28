# Requisitos

> O que o sistema deve fazer. Extraídos da especificação do trabalho — em caso de
> dúvida, vale o documento oficial.

## Funcionamento geral

- **RF1** — O cliente conecta-se ao servidor via socket, em `localhost` ou por IP.
- **RF2** — O cliente envia comunicações de texto ao servidor.
- **RF3** — O limite máximo de caracteres do texto é definido dinamicamente no
  início da comunicação (negociado entre cliente e servidor), com default de no
  mínimo **30 caracteres**.
- **RF4** — O texto é fragmentado em múltiplos pacotes do protocolo de aplicação,
  cada um com **payload de no máximo 4 caracteres**. Esse limite refere-se
  estritamente ao conteúdo da aplicação; os cabeçalhos do protocolo (checksum,
  flags, número de sequência) são concatenados ao payload para compor o pacote
  final enviado via socket.
- **RF5** — Ao receber cada pacote, o servidor imprime seus **metadados**; ao
  final da comunicação, apresenta a **mensagem completa** corretamente reconstruída.
- **RF6** — O cliente imprime os **metadados das confirmações** (ACKs) à medida
  que chegam.

## Transporte confiável

O protocolo deve implementar as características do transporte confiável
(Tabela 3.1 do livro-texte), independentemente do protocolo da camada de transporte:

- **RT1** — Soma de verificação (checksum)
- **RT2** — Temporizador (timeout e retransmissão)
- **RT3** — Número de sequência
- **RT4** — Reconhecimento positivo (ACK)
- **RT5** — Reconhecimento negativo (NAK)
- **RT6** — Janela e paralelismo: quantidade de mensagens enviadas ao servidor por
  vez, variando de **1 a 5**, **determinada pelo servidor**, com valor inicial **5**

## Erros e modos de operação

- **RE1** — Simulação de falhas de integridade e/ou perdas a nível de aplicação:
  é possível inserir um "erro" no lado cliente, verificável pelo servidor. O erro
  é **determinístico** (definido do lado cliente).
- **RE2** — Envio de pacotes isolados **ou** em lotes, a partir do cliente.
- **RE3** — O servidor pode ser configurado para confirmar a recepção
  **individual** ou **em grupo** (aceita as duas configurações).
- **RE4** — A confirmação da janela ocorre por **Go-Back-N** ou **Repetição
  Seletiva**, a depender da escolha do cliente.

## Handshake

- **RH1** — Na conexão, cliente e servidor trocam, no mínimo:
  - modo de operação (envio individual vs. lote / Go-Back-N vs. Repetição Seletiva)
  - tamanho máximo do texto inicial (buffer/limite da mensagem do usuário)
  - tamanho da janela (janela de recepção inicial do servidor)
