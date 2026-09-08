# Diário de Uso de IA — Trabalho I

Registro do uso de assistentes de IA durante o desenvolvimento do trabalho. Cada entrada detalha as solicitações feitas, artefatos gerados e decisões a serem validadas pelo grupo.

---

## Entrada 1 — Implementação de `protocol.py` (Checkpoint 1)

**Data:** 2026-09-04

### Solicitação
Geração da estrutura inicial do módulo `src/protocol.py` para o handshake de 3 vias (HELLO, HELLO_ACK, READY), com serialização via módulo `struct` (network byte order), enumerações `IntEnum`, classes de erro e validações básicas de parâmetros.

### Gerado
- Constante `MAGIC = 0xAA`
- Enums: `PacketType`, `Mode` e `Strategy`
- Exceção `InvalidPacketError`
- Funções `build_hello`, `build_hello_ack`, `build_ready` e `parse_packet`
- Bloco de teste de round-trip no `__main__`

### Pontos para revisão do grupo
- Validação estrita de limites no desempacotamento (`max_text >= 30` e `window` entre 1 e 5).
- Manutenção do campo `reserved` no pacote `HELLO` para uso futuro.

---

## Entrada 2 — Documentação Inicial (Checkpoint 1)

**Data:** 2026-09-04

### Solicitação
Estruturação de `docs/protocolo.md`, `README.md` e criação deste diário para documentar as decisões tomadas até o momento.

### Gerado
- Especificação dos cabeçalhos dos pacotes e fluxo de handshake no `protocolo.md`.
- Guia de execução inicial no `README.md`.

---

## Entrada 3 — Implementação de `server.py`, `client.py` e Testes Locais

**Data:** 2026-09-04

### Solicitação
1. Implementação do servidor UDP (`src/server.py`) e cliente UDP (`src/client.py`) consumindo `src/protocol.py`.
2. Conexão socket ponta a ponta e salvamento da saída real em `docs/exemplo-handshake.txt`.

### Gerado
- `src/server.py`: loop de escuta em porta UDP, envio de `HELLO_ACK` com janela fixa e espera por `READY`.
- `src/client.py`: linha de comando via `argparse` com validação de parâmetros e timeout de 5 segundos.
- `docs/exemplo-handshake.txt`: captura da execução das duas pontas.

---

## Entrada 4 — Revisão e Humanização do Código

**Data:** 2026-09-08

### Solicitação
Revisão geral para eliminar padrões artificiais gerados por IA, mantendo 100% da lógica e comportamento do protocolo:
- Tradução de comentários e docstrings para português (pt-BR).
- Remoção de underscores privados desnecessários em constantes e funções.
- Simplificação das saídas no terminal (remoção de alinhamentos artificiais).
- Enxugamento do bloco de testes em `protocol.py`.
- Limpeza dos documentos `.md`.

### Gerado
- `src/protocol.py`: constantes padronizadas (`HEADER_SIZE`, `FMT_HEADER`, etc.), comentários em pt-BR e testes concisos.
- `src/server.py`: import de `DEFAULT_PORT`, nomes de constantes e funções simplificados, saída em terminal mais natural.
- `src/client.py`: remoção de tipos redundantes em variáveis locais, alinhamento dos logs e tratamento de erros.
- `README.md`, `docs/protocolo.md` e `docs/exemplo-handshake.txt`: documentação direta e saída real atualizada.

### Pontos para revisão do grupo
- Acompanhar as próximas etapas (CP2) para transferência de pacotes de dados de 4 bytes e cálculo de checksum.
