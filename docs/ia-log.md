# Diário de Uso de IA — Trabalho I

Registro das interações com assistentes de IA durante o desenvolvimento do
trabalho. Cada entrada descreve o que foi pedido, as decisões tomadas e os
pontos que o grupo deve revisar antes de considerar o resultado como definitivo.

---

## Entrada 1 — Implementação de `protocol.py` (Checkpoint 1)

**Data:** 2026-09-04

### O que foi pedido

Implementação completa do módulo `src/protocol.py` para a fase de handshake
(CP1). O prompt especificou o formato exato dos três pacotes (HELLO, HELLO_ACK,
READY), o uso de `struct` com network byte order, enums `IntEnum`, funções de
build/parse, exceção customizada `InvalidPacketError` e um bloco `__main__`
de verificação.

### O que foi gerado

- Constante `MAGIC = 0xAA`
- Enums: `PacketType` (HELLO/HELLO_ACK/READY), `Mode` (INDIVIDUAL/BATCH),
  `Strategy` (GBN/SR)
- Exceção: `InvalidPacketError(ValueError)`
- Funções: `build_hello`, `build_hello_ack`, `build_ready`, `parse_packet`
- Bloco `__main__` com seis verificações (3 round-trips + 3 erros de validação)

### Decisões tomadas pela IA que o grupo deve revisar

| Decisão | Detalhe | Impacto |
|---|---|---|
| Transporte confirmado como UDP | O código não cria sockets ainda, mas a decisão foi registrada como definitiva em `protocolo.md` | Confirmar com o grupo antes do CP2 |
| Campo `RESERVED` presente no dict de retorno | `parse_packet` devolve `"reserved"` no resultado de HELLO | Pode ser omitido se o grupo preferir uma interface mais limpa |
| Validação de `max_text` no parser | O parser rejeita MAX_TEXT < 30 recebido na rede | Comportamento defensivo razoável, mas o grupo pode optar por apenas logá-lo como aviso |
| Validação de `window` no parser | O parser rejeita WINDOW fora de [1, 5] recebido na rede | Mesma consideração |
| Sem persistência de estado | `protocol.py` é puramente funcional (sem classes de estado) | Quando `client.py`/`server.py` forem implementados, decidir onde manter o estado da sessão |

### Pontos a revisar no código gerado

- O bloco `__main__` usa `assert` simples — não substitui testes unitários
  formais. Considerar adicionar `tests/` com `pytest` no CP2.
- O campo `RESERVED` é sempre `0x00` por ora; quando for utilizado,
  atualizar `parse_packet` para não ignorá-lo silenciosamente.
- O nome do protocolo ainda não foi definido pelo grupo (marcação no topo de
  `protocolo.md`).

---

## Entrada 2 — Atualização da documentação (Checkpoint 1)

**Data:** 2026-09-04

### O que foi pedido

Atualização de `docs/protocolo.md`, `README.md` e criação de `docs/ia-log.md`
para refletir o estado real após a implementação de `protocol.py`. O prompt
solicitou manter seções pendentes marcadas com ⚠️ e não inventar detalhes de
CPs futuros.

### O que foi alterado

- **`docs/protocolo.md`:** seção 1 (transporte decidido, byte order adicionado),
  seção 2 reescrita com o formato real dos pacotes de handshake, seção 3 com
  os nomes corretos (HELLO/HELLO_ACK/READY em vez de SYN/SYN-ACK/ACK), seção 7
  com exemplos concretos de bytes.
- **`README.md`:** status atualizado, roadmap com coluna de status, estrutura
  de diretórios atualizada, seção "Como executar" preenchida para o estado atual.
- **`docs/ia-log.md`:** criado (este arquivo).

### Pontos que o grupo deve revisar

- Os exemplos de bytes na seção 7 de `protocolo.md` foram gerados a partir da
  saída real do `__main__` de `protocol.py` — conferir se batem com o esperado.
- A seção "Como executar" do README usa `from src.protocol import …` — funciona
  quando o REPL é iniciado na raiz do repositório; ajustar se a estrutura de
  pacotes mudar.

---

## Entrada 3 — Implementação de `server.py`, `client.py`, testes fim a fim e documentação do CP1

**Data:** 2026-09-04

### O que foi pedido

1. Implementação do servidor UDP (`src/server.py`) e do cliente UDP (`src/client.py`) para completar a troca do handshake de 3 vias (HELLO, HELLO_ACK, READY) do Checkpoint 1, consumindo `src/protocol.py`.
2. Execução de testes fim a fim cobrindo os modos de operação (`individual`, `batch` com GBN e SR) e persistência da saída real em `docs/exemplo-handshake.txt`.
3. Atualização da documentação do repositório (`README.md`, `docs/protocolo.md` e este log) para refletir a conclusão do Checkpoint 1, incluindo guia passo a passo de execução (runbook), descrição exata dos argumentos de linha de comando (`argparse`) e seção de troubleshooting.

### O que foi gerado

- **`src/server.py`:** servidor UDP com socket vinculado a `0.0.0.0:50000`, laço iterativo de atendimento, validação de integridade dos pacotes com descarte defensivo e avisos no console, controle de endereço de origem durante o aguardo de `READY` e confirmação dos parâmetros acordados.
- **`src/client.py`:** cliente UDP com interface de linha de comando (`--host`, `--port`, `--mode`, `--strategy`, `--max-text`), validação prévia de `--max-text >= 30`, temporizador de 5,0 segundos para recepção de respostas e finalização defensiva com código de erro 1 em caso de timeout ou respostas inválidas.
- **`docs/exemplo-handshake.txt`:** captura de saída real de uma execução simultânea de servidor e cliente em modo lote com Go-Back-N.
- **`README.md`:** status atualizado para CP1 concluído, roadmap e árvore de arquivos atualizados, manual de uso detalhado com sintaxe e flags reais de `argparse`, comandos prontos para cada modo e tabela de diagnóstico de erros/troubleshooting.
- **`docs/protocolo.md`:** formalização dos parâmetros operacionais de rede (porta UDP 50000, buffer de 1024B, timeout de 5s), detalhamento do fluxo de handshake de 3 vias e remoção de marcações de decisão pendente para itens já implementados.

### Decisões e pontos que o grupo deve revisar

| Decisão | Detalhe | Impacto |
|---|---|---|
| Modelo iterativo no servidor | O servidor CP1 atende um handshake e retorna ao laço principal | Suficiente para o CP1; no CP2/CP3, definir como o servidor gerenciará o estado da transferência e múltiplas sessões |
| Janela fixa no servidor | `_WINDOW = 5` fixada no código do servidor | Atende ao requisito do CP1; a variação/adaptação dinâmica da janela de 1 a 5 será definida em checkpoints futuros |
| Timeout do cliente | Fixado em 5,0 segundos (`sock.settimeout(5.0)`) | Cobriu com folga os testes locais; avaliar necessidade de parametrização via CLI nos próximos marcos |
| Validação antecipada de `max_text` | O cliente encerra com código 1 antes de tocar a rede se `--max-text < 30` | Evita tráfego inútil na rede e garante conformidade estrita com o requisito RF3 |

