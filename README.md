# PA1 — Web Crawler

Crawler paralelo em Python 3.14 que respeita robots.txt e politeness.

## Setup

```bash
python3 -m venv .venv

# Linux / macOS / WSL
source .venv/bin/activate

# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1

pip3 install -r requirements.txt
```

## Uso

```bash
python3 crawler.py -s <seeds> -n <limit> [-d] [-r]
```

- `-s, --seeds`: arquivo com URLs iniciais OU diretorio com varios `.txt` (um por linha; linhas comecando com `#` sao ignoradas)
- `-n, --limit`: numero de paginas a baixar
- `-d, --debug`: imprime JSON por pagina em stdout
- `-r, --resume`: retoma o crawl lendo `data/visited.txt` (pula URLs ja processadas e soma ao contador de paginas)

## Exemplo

```bash
# Crawl completo
python3 crawler.py -s seeds/seeds-2017114124.txt -n 100000

# Modo debug
python3 crawler.py -s seeds/seeds-2017114124.txt -n 10 -d > debug.jsonl

# Retomar depois de queda de conexao
python3 crawler.py -s seeds/seeds-2017114124.txt -n 100000 -r

# Usar um diretorio inteiro de seeds (concatena todos os .txt)
python3 crawler.py -s seeds/ -n 100000
```

## Estrutura

```
web-crawler-tp/
├── crawler.py               # entry point
├── requirements.txt
├── src/
│   ├── config/              # constantes centralizadas, por tema
│   │   ├── filters.py       # schemes, extensoes, Content-Types
│   │   ├── network.py       # User-Agent, timeouts, MAX_PAGE_SIZE
│   │   ├── parallelism.py   # NUM_THREADS, METRICS_INTERVAL, METRICS_FILE
│   │   ├── politeness.py    # DEFAULT_CRAWL_DELAY, MAX_PAGES_PER_HOST
│   │   └── storage.py       # PAGES_PER_WARC, WARC_DIR, VISITED_FILE
│   ├── core/
│   │   └── frontier.py      # fila de URLs com politeness por host
│   ├── network/
│   │   ├── robots.py        # cache de robots.txt (Protego)
│   │   └── fetcher.py       # HTTP GET com streaming
│   ├── content/
│   │   ├── url_utils.py     # normalizacao e filtros de URL
│   │   └── parser.py        # extracao de titulo/texto/links
│   ├── output/
│   │   ├── storage.py       # escrita de WARCs rotativos + visited.txt
│   │   └── metrics.py       # snapshot periodico em CSV
│   └── test/
│       ├── speedup_experiment.py  # varia NUM_THREADS e mede tempo
│       ├── extract_corpus.py      # WARC → arquivos .html individuais
│       └── base_validation.py     # validacao rapida do corpus
├── seeds/                   # arquivos de seed URLs
├── data/                    # artefatos (runtime)
│   ├── corpus/              # WARCs gerados
│   ├── logs/                # metrics.csv, speedup.csv
│   ├── extracted/           # HTMLs extraidos (opcional)
│   ├── analysis/            # notebooks de caracterizacao
│   └── visited.txt          # log append-only de URLs processadas
└── docs/                    # ARCHITECTURE.md, PIPELINE.md, relatorio
```

## Saida

- `data/corpus/corpus-NNNNN.warc.gz` — 1000 paginas por arquivo, gzip
- `data/logs/metrics.csv` — snapshots a cada 30s com rate/throughput
- `data/visited.txt` — uma URL por linha, append-only (usado pelo `-r`)
- stdout (se `-d`) — JSON por pagina: URL, Title, Text (preview), Timestamp
- stderr — progresso via `logging`

## Politicas de crawling

1. **Selection**: somente HTML (filtro pre-fetch por extensao + pos-fetch por Content-Type)
2. **Revisitation**: dedup via normalizacao de URL + set global; `visited.txt` persiste entre execucoes
3. **Parallelization**: `NUM_THREADS = 16` por default (ajustavel em `src/config/parallelism.py`)
4. **Politeness**: robots.txt via Protego; delay minimo de 100ms por host
5. **Storage**: WARC compactado com gzip, 1000 paginas por arquivo
