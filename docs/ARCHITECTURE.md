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
         │  Worker 1   │  Worker 2   │   Worker N  │   (16 threads default)
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
         │  gzip         │    │   outlinks + │
         │               │    │  visited.txt)│
         └───────┬───────┘    └──────────────┘
                 │
                 ▼
         ┌───────────────┐
         │    Metrics    │  snapshot a cada 30s → CSV
         └───────────────┘
```

Em uma frase: **seeds alimentam uma fila por host; N threads consomem
em paralelo; cada página baixada vai pro WARC (e pro log `visited.txt`)
e seus links voltam pra fila. Tudo respeitando `robots.txt` e delay
≥ 100ms por host.**

## Módulos

| Módulo | Pacote | Responsabilidade |
|---|---|---|
| `crawler.py` | raiz | Entry point: CLI, threads, orquestração |
| `filters.py` | `src/config/` | Schemes aceitos, extensões e MIMEs não-HTML |
| `network.py` | `src/config/` | User-Agent, `HTTP_TIMEOUT`, `MAX_PAGE_SIZE` |
| `parallelism.py` | `src/config/` | `NUM_THREADS`, `METRICS_INTERVAL`, `METRICS_FILE`, `WATCHDOG_*` |
| `politeness.py` | `src/config/` | `DEFAULT_CRAWL_DELAY`, `MAX_PAGES_PER_HOST`, `MAX_QUEUE_PER_HOST` |
| `storage.py` (config) | `src/config/` | `PAGES_PER_WARC`, `WARC_DIR`, `VISITED_FILE` |
| `frontier.py` | `src/core/` | Fila de URLs com politeness por host + log `visited.txt` |
| `robots.py` | `src/network/` | Cache thread-safe de `robots.txt` |
| `fetcher.py` | `src/network/` | HTTP GET com validação de MIME |
| `url_utils.py` | `src/content/` | Normalização e filtros de URL |
| `parser.py` | `src/content/` | Extração de título, texto e outlinks |
| `storage.py` | `src/output/` | Escrita de WARCs rotativos |
| `metrics.py` | `src/output/` | Snapshot periódico em CSV |
| `speedup_experiment.py` | `src/test/` | Varia `NUM_THREADS`, mede tempo, gera `speedup.csv` |
| `extract_corpus_validation.py` | `src/test/` | Expande WARC em arquivos `.html` para inspeção/validação |
| `check_seeds.py` | `scripts/` | Classifica cada seed em visitada, redirecionada ou perdida |
| `dedupe_corpus.py` | `scripts/` | Reescreve os WARCs removendo URLs duplicadas (mantém 1ª ocorrência), com backup em `data/corpus.bak/` |

O agrupamento reflete as camadas: `network/` lida com rede, `content/`
com processamento, `output/` com persistência, `core/` com o motor,
`config/` com constantes (quebrado em 5 arquivos por tema),
`test/` com utilitários que rodam em cima do corpus já gerado, e
`scripts/` com ferramentas one-shot de diagnóstico e limpeza.

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

**Por que fila por host e não FIFO global?** Com FIFO global e várias
threads, uma sequência de 500 URLs do mesmo host bloquearia todas as
threads esperando o delay de politeness. Com fila por host + heap
ordenada por `next_time`, cada thread sempre pega o host mais pronto —
nenhuma thread fica travada enquanto existe trabalho em outros hosts.

**Retomada após crash.** O frontier expõe `load_visited()` e
`mark_visited(urls)`: na inicialização com `-r`, o crawler lê
`data/visited.txt`, marca todas as URLs como vistas (elas nunca serão
re-enfileiradas) e ajusta o contador inicial do `WarcStorage` via
`set_initial_count(len(visited))`.

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

O log append-only em `data/visited.txt` — uma linha por URL processada
— é mantido pelo `Frontier` (`record_visited()`), não pelo storage:
assim, cada URL é registrada no mesmo momento em que sai da fronteira,
independente de ter virado WARC ou não. Abre em modo `a` sob `-r`
(append) ou `w` (sobrescrever) no modo fresh, com `fsync` a cada
`VISITED_FSYNC_EVERY = 50` páginas para sobreviver a quedas.

### Metrics

Contadores cumulativos (`pages_failed`, `bytes_downloaded`) protegidos
por `Lock`. Uma thread dedicada dorme em `stop_event.wait(timeout=30)`
e escreve uma linha no CSV a cada snapshot (`METRICS_INTERVAL = 30s`).

## Fluxo de execução

### Inicialização (em `crawler.py`)

1. Parseia CLI via `argparse` (`-s`, `-n`, `-d`, `-r`)
2. Lê seeds: aceita arquivo único ou diretório (concatena todos os `.txt`)
3. Instancia `RobotsCache`, `Frontier`, `WarcStorage(resume=args.resume)`, `Metrics`
4. Se `-r`: carrega `visited.txt`, marca URLs no frontier, ajusta contador do storage
5. Enfileira cada seed via `frontier.add(url)`
6. `metrics.start()` dispara thread de snapshot
7. Dispara thread do **watchdog** (monitora estagnação — ver abaixo)
8. Cria `NUM_THREADS` workers; join loop tolerante a Ctrl+C

### Loop do worker

```python
while not stop_event.is_set():
    url, _ = frontier.get_next(stop_event)  # bloqueia se precisar
    if url is None: return                  # fim de trabalho
    try:
        result = fetch(url)                 # HTTP GET
        if not result.ok:
            metrics.record_failure()
            continue
        parsed = parse_html(result.raw_bytes.decode(...), result.final_url)
        if storage.store(result):           # grava WARC
            frontier.record_visited(result.final_url)  # appenda visited.txt
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

### Watchdog de estagnação

Em runs longos, a fronteira pode ficar "empoçada" em poucos hosts lentos
ou enormes: as threads ainda trabalham, mas o throughput cai a poucas
páginas por minuto. A thread `watchdog` (em `crawler.py`) monitora
`storage.total_saved()` em janelas de `WATCHDOG_STALL_SECONDS = 60s`. Se
nessa janela foram salvas menos que `WATCHDOG_MIN_PAGES = 10` páginas,
ela chama `frontier.clear_queues(forget=seeds)`:

- Esvazia `_queues`, `_next_time`, `_ready_heap` e zera `_pending_urls`.
- Preserva `_seen` e `_host_count` — URLs já visitadas **não** voltam
  para a fila e hosts já saturados continuam fechados.
- Remove as seeds originais de `_seen` para poder re-enfileirá-las como
  novos pontos de partida.

Constantes em `src/config/parallelism.py` (`WATCHDOG_INTERVAL`,
`WATCHDOG_STALL_SECONDS`, `WATCHDOG_MIN_PAGES`). É um "restart suave" —
o processo, o WARC em andamento e o `visited.txt` continuam intactos.

### Parada

1. Uma thread atinge o limite e seta o event (ou o usuário aperta Ctrl+C)
2. As outras threads veem o event no próximo loop e retornam
3. Em Ctrl+C há um deadline de 10s antes de forçar shutdown
4. `storage.close()` fecha o WARC atual e `frontier.close()` faz o `fsync` final de `visited.txt`
5. `metrics.close()` aguarda o último snapshot e fecha o CSV

## Concorrência

### Locks utilizados

| Lock | Protege | Granularidade |
|---|---|---|
| `Frontier._lock` (Condition) | Estruturas do frontier + log `visited.txt` | Único |
| `RobotsCache._lock` | Dict `_cache` | Único |
| `RobotsCache._host_locks[h]` | Fetch de robots.txt de 1 host | Por host |
| `WarcStorage._lock` | Writer WARC atual | Único |
| `Metrics._lock` | Contadores | Único |

### Padrões de concorrência

**Double-checked locking (RobotsCache).** Checa cache sem lock pesado;
se miss, pega o lock **do host** (não global) pra baixar; re-checa
dentro do lock antes de efetivamente baixar. Evita que várias threads
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
- Threads para I/O-bound é escala gerenciável sem complexidade

## Conformidade com as políticas do enunciado

### 1. Selection Policy (só HTML)

**Dois níveis:**
1. **Pré-fetch:** `has_non_html_extension()` rejeita `.pdf`, `.jpg`, etc.
   Lista em `src/config/filters.py`.
2. **Pós-fetch:** `fetch()` lê o header `Content-Type` antes do body
   (via `stream=True`) e rejeita não-HTML.

### 2. Revisitation Policy (não revisitar)

`Frontier._seen: set[str]` guarda todas as URLs já enfileiradas. Antes
de enfileirar uma URL nova, ela é normalizada (remoção de fragment,
lowercase no host, porta default, percent-encoding canônico) e testada
no set. Lookup O(1).

Para sobreviver a quedas de conexão, URLs processadas são persistidas
em `data/visited.txt` e re-carregadas no início via `-r`.

### 3. Parallelization Policy

- `NUM_THREADS = 16` (default em `src/config/parallelism.py`)
- Crawling é I/O-bound: >95% do tempo é espera de rede
- `src/test/speedup_experiment.py` automatiza a variação de threads
  para gerar o speedup CSV exigido no relatório

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
- Saída em `data/corpus/corpus-NNNNN.warc.gz`

## Decisões de design

### Fila por host vs. FIFO global
**Escolhida:** fila por host com heap.
**Razão:** FIFO global sofre de thread starvation quando várias URLs
seguidas são do mesmo host.

### Config único vs. pacote `config/`
**Escolhida:** pacote `src/config/` com 5 arquivos temáticos
(`filters`, `network`, `parallelism`, `politeness`, `storage`).
**Razão:** o arquivo único crescia demais e misturava assuntos
ortogonais. Quebrar por tema facilita o ajuste direcionado (ex:
experimentos de speedup só tocam `parallelism.py`).

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

### Persistência de visitados em arquivo texto
**Escolhida:** append-only `data/visited.txt` (uma URL por linha).
**Razão:** formato trivialmente inspeccionável com `wc -l`, `grep`,
etc.; append + `fsync` periódico é resistente a crash e barato.
Carregar no start é O(N) linhas, aceitável para 100k URLs.

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
| Escrita WARC + append visited | O(tamanho da página) |
| Load visited no resume | O(V) lido uma vez no start |
| **Total** | **O(N × (log H + L))**, dominado pela rede |

Espaço: O(N) para o set `_seen` + O(outlinks pendentes) para as queues.
Em prática, ~100 bytes por URL — 100k URLs ≈ 10 MB de RAM.

## NEXT STEPS
1- Corrigir despriorização de seed
- Não é bug — é o comportamento esperado quando:

-> Seed é o único ponto de entrada para o domínio.
-> Causa da falha é determinística (TLS/anti-bot), não transiente.

Se quiser mitigar no código: (a) dar uma lista de User-Agents/headers "browser-like" só para o fetch de seeds; (b) em caso de SSLError na seed, tentar fallback para http:// ou www.<host> (o que já resolveria várias .gov.br); (c) fazer retry com backoff específico para seeds antes de considerá-las "queimadas".