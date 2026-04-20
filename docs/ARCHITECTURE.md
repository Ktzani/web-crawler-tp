# Arquitetura

Documento técnico para quem quer entender como o crawler funciona por
dentro. Complementa o `README.md` (que é focado em uso).

## Visão geral

```
                      ┌──────────────┐
    seeds.txt ───────▶│   Frontier   │◀─── outlinks descobertos
                      │ (por host)   │
                      └──────┬───────┘
                             │ get_next() / release_host()
                             ▼
         ┌─────────────┬─────────────┬─────────────┐
         │  Worker 1   │  Worker 2   │   Worker N  │   (64 threads)
         └──────┬──────┴──────┬──────┴──────┬──────┘
                │             │             │
                ▼             ▼             ▼
            ┌─────────────────────────────────┐
            │           Fetcher               │  HTTP GET com stream
            │  Session por thread             │  valida Content-Type
            │  timeout (5s, 15s)              │  trunca em 2 MB
            └────────────────┬────────────────┘
                             │
                             ▼
            ┌─────────────────────────────────┐
            │            Parser               │  BS4 + html.parser
            │  titulo + texto + outlinks      │
            └────┬────────────────────┬───────┘
                 │                    │
                 ▼                    ▼
         ┌───────────────┐    ┌──────────────┐
         │  WarcStorage  │    │   Frontier   │
         │  1000/arquivo │    │  (re-enqueue │
         │  gzip         │    │   outlinks)  │
         └───────────────┘    └──────────────┘
                 │
                 ▼
         ┌───────────────┐
         │    Metrics    │  snapshot a cada 5s → CSV
         └───────────────┘
```

Em uma frase: **seeds alimentam uma fila por host; 64 threads consomem
em paralelo; cada página baixada vai pro WARC e seus links voltam
pra fila. Tudo respeitando `robots.txt` e delay ≥ 100ms por host.**

## Módulos

| Módulo | Pacote | Responsabilidade |
|---|---|---|
| `crawler.py` | raiz | Entry point: CLI, threads, orquestração |
| `config.py` | `src/` | Constantes centralizadas |
| `frontier.py` | `src/core/` | Fila de URLs com politeness por host |
| `robots.py` | `src/net/` | Cache thread-safe de `robots.txt` |
| `fetcher.py` | `src/net/` | HTTP GET com validação de MIME |
| `url_utils.py` | `src/content/` | Normalização e filtros de URL |
| `parser.py` | `src/content/` | Extração de título, texto e outlinks |
| `storage.py` | `src/output/` | Escrita de WARCs rotativos |
| `metrics.py` | `src/output/` | Snapshot periódico em CSV |

O agrupamento reflete as camadas: `net/` lida com rede, `content/` com
processamento, `output/` com persistência, `core/` com o motor.

## Estruturas de dados

### Frontier (o coração)

| Estrutura | Campo | Complexidade | Propósito |
|---|---|---|---|
| `dict[str, deque[str]]` | `_queues` | O(1) enqueue/dequeue | URLs pendentes por host |
| `dict[str, float]` | `_next_time` | O(1) read/write | Quando cada host fica "pronto" |
| `list[tuple[float, str]]` (heap) | `_ready_heap` | O(log H) | Ordem de hosts por prontidão |
| `set[str]` | `_seen` | O(1) amortizado | Dedup global de URLs |
| `dict[str, int]` | `_host_count` | O(1) | Páginas aceitas por host |

Onde `H` = número de hosts distintos.

**Por que fila por host e não FIFO global?** Com FIFO global e 64
threads, uma sequência de 500 URLs do mesmo host bloquearia 499 threads
esperando o delay de politeness. Com fila por host + heap ordenada por
`next_time`, cada thread sempre pega o host mais pronto — nenhuma
thread fica travada enquanto existe trabalho em outros hosts.

### RobotsCache

```
_cache: dict[host, tuple[Protego_parser_or_None, float_delay]]
_host_locks: dict[host, Lock]  ← 1 lock por host (evita thundering herd)
```

### Storage

Rotação baseada em **contador** (não em bytes): exatamente 1000 páginas
por arquivo. O arquivo ativo é trocado dentro do `store()` quando
`current_count >= PAGES_PER_WARC`. Um único lock serializa as escritas
— disk I/O não é gargalo comparado a rede.

### Metrics

Contadores cumulativos (`pages_failed`, `bytes_downloaded`) protegidos
por `Lock`. Uma thread dedicada dorme em `stop_event.wait(timeout=5)` e
escreve uma linha no CSV a cada snapshot.

## Fluxo de execução

### Inicialização (em `crawler.py`)

1. Parseia CLI via `argparse`
2. Lê seeds (linha por linha, comentários `#` ignorados)
3. Instancia `RobotsCache`, `Frontier`, `WarcStorage`, `Metrics`
4. Enfileira cada seed via `frontier.add(url)`
5. `metrics.start()` dispara thread de snapshot
6. Cria `NUM_THREADS` workers e faz `join()` em todas

### Loop do worker

```python
while not stop_event.is_set():
    url = frontier.get_next(stop_event)     # bloqueia se precisar
    if url is None: return                  # fim de trabalho
    try:
        result = fetch(url)                 # HTTP GET
        if not result.ok:
            metrics.record_failure()
            continue
        parsed = parse_html(result.raw_bytes, result.final_url)
        if storage.store(result):
            metrics.record_success(len(result.raw_bytes))
            if debug: print(json_record)
            if storage.total_saved() >= limit:
                stop_event.set()
                frontier.notify_all()
                return
            for link in parsed.outlinks:
                frontier.add(link)
    finally:
        frontier.release_host(url)          # libera o host na heap
```

**Pontos críticos:**

- `try/finally` garante que `release_host()` é sempre chamado. Sem isso,
  um erro no fetch "travaria" o host no heap.
- Checagem do limite **depois** de gravar e **antes** de enfileirar
  outlinks — economiza trabalho inútil.
- `stop_event.set()` + `frontier.notify_all()` acorda as threads
  dormindo em `cond.wait()`.

### Parada

1. Uma thread atinge o limite e seta o event
2. As outras threads veem o event no próximo loop e retornam
3. `metrics.close()` aguarda o último snapshot e fecha o CSV
4. `storage.close()` fecha o WARC atual

## Concorrência

### Locks utilizados

| Lock | Protege | Granularidade |
|---|---|---|
| `Frontier._lock` (Condition) | Estruturas do frontier | Único |
| `RobotsCache._lock` | Dict `_cache` | Único |
| `RobotsCache._host_locks[h]` | Fetch de robots.txt de 1 host | Por host |
| `WarcStorage._lock` | Writer WARC atual | Único |
| `Metrics._lock` | Contadores | Único |

### Padrões de concorrência

**Double-checked locking (RobotsCache).** Checa cache sem lock pesado;
se miss, pega o lock **do host** (não global) pra baixar; re-checa
dentro do lock antes de efetivamente baixar. Evita que 64 threads
interessadas em hosts diferentes se bloqueiem mutuamente.

**Lazy deletion (Frontier heap).** Ao atualizar `next_time[host]`, não
removo a entrada antiga da heap. Em `get_next()`, comparo o `next_time`
do topo da heap com o valor atual do dict — se não bate, descarto
(é "stale") e continuo. Evita operações O(H) de busca.

**Thread-local sessions (Fetcher).** Cada thread tem seu próprio
`requests.Session` via `threading.local`. Session não é garantidamente
thread-safe, mas dar uma por thread traz o benefício extra de
reaproveitar conexões TCP (keep-alive) dentro daquela thread.

### Por que threads e não async/await?

- O enunciado pede paralelização por threads explicitamente
- `requests` (requirement) é síncrono — `aiohttp` exigiria outra lib
- Overhead do GIL é irrelevante aqui: I/O de rede libera o GIL
- 64 threads para I/O-bound é escala gerenciável sem complexidade

## Conformidade com as políticas do enunciado

### 1. Selection Policy (só HTML)

**Dois níveis:**
1. **Pré-fetch:** `has_non_html_extension()` rejeita `.pdf`, `.jpg`, etc.
2. **Pós-fetch:** `fetch()` lê o header `Content-Type` antes do body
   (via `stream=True`) e rejeita não-HTML.

### 2. Revisitation Policy (não revisitar)

`Frontier._seen: set[str]` guarda todas as URLs já enfileiradas. Antes
de enfileirar uma URL nova, ela é normalizada (remoção de fragment,
lowercase no host, porta default, percent-encoding canônico) e testada
no set. Lookup O(1).

### 3. Parallelization Policy

- `NUM_THREADS = 64` (em `src/config.py`)
- Crawling é I/O-bound: >95% do tempo é espera de rede
- 64 threads saturam banda doméstica sem serem rejeitadas como abusivas

### 4. Politeness Policy

**robots.txt via Protego** (mais completo que `urllib.robotparser`):

- Cache por host, baixado sob demanda
- Tratamento deliberado de falhas:
  - `404/410` → tudo permitido
  - `401/403` → tudo bloqueado (servidor protegeu o próprio robots)
  - `5xx / timeout` → liberal (erro transiente não trava o site)
- `Crawl-delay` lido do robots; aplicado `max(declarado, 100ms)`
- A heap garante que nenhum host é acessado antes do seu `next_time`

### 5. Storage Policy

- WARC comprimido com gzip (`warcio` com `gzip=True`)
- Rotação a cada 1000 páginas → 100 arquivos para 100k
- Dois registros por página: `request` + `response` (padrão Heritrix/IA)
- Amarrados via header `WARC-Concurrent-To`

## Decisões de design

### Fila por host vs. FIFO global
**Escolhida:** fila por host com heap.
**Razão:** FIFO global sofre de thread starvation quando várias URLs
seguidas são do mesmo host.

### Lock único vs. locks finos no Frontier
**Escolhida:** um `Lock` + `Condition` para todo o Frontier.
**Razão:** operações são curtas (memória); o lock não é gargalo
comparado ao tempo gasto em I/O. Simplicidade > micro-otimização.

### `html.parser` vs. `lxml`
**Escolhida:** `html.parser` (stdlib).
**Razão:** `lxml` não está no `requirements.txt`. `html.parser` é mais
lento mas suficiente — o bottleneck é rede, não parsing.

### Dedup por URL vs. hash de conteúdo
**Escolhida:** por URL normalizada.
**Razão:** o enunciado fala em "URL previamente crawleada", não em
conteúdo duplicado. Dedup por conteúdo seria outra política.

### Limite de páginas por host
**Escolhida:** `MAX_PAGES_PER_HOST = 5000` (não exigido).
**Razão:** (1) evita que um site grande domine o corpus, ajudando na
distribuição por domínio do relatório; (2) defesa contra spider traps.

## Complexidade

Sejam $N$ o total de páginas, $H$ o número de hosts distintos, $L$ o
número médio de outlinks por página:

| Operação | Complexidade |
|---|---|
| `frontier.add(url)` | O(log H) |
| `frontier.get_next()` | O(log H) |
| `frontier.release_host(url)` | O(log H) |
| Dedup (`url in seen`) | O(1) |
| Fetch HTTP | O(tamanho da página), dominado por rede |
| Parse HTML | O(tamanho do HTML) |
| Escrita WARC | O(tamanho da página) |
| **Total** | **O(N × (log H + L))**, dominado pela rede |

Espaço: O(N) para o set `_seen` + O(outlinks pendentes) para as queues.
Em prática, ~100 bytes por URL — 100k URLs ≈ 10 MB de RAM.
