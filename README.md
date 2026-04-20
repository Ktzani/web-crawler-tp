# PA1 — Web Crawler

Crawler paralelo em Python 3.14 que respeita robots.txt e politeness.

## Setup

```bash
python3 -m venv pa1
source pa1/bin/activate
pip3 install -r requirements.txt
```

## Uso

```bash
python3 crawler.py -s <seeds_file> -n <limit> [-d]
```

- `-s, --seeds`: arquivo com URLs iniciais (uma por linha)
- `-n, --limit`: numero de paginas a baixar
- `-d, --debug`: imprime JSON por pagina em stdout

## Exemplo

```bash
python3 crawler.py -s seeds/seeds-2017114124.txt -n 100000
```

Em modo debug:
```bash
python3 crawler.py -s seeds/seeds-test.txt -n 10 -d > debug.jsonl
```

## Estrutura

```
pa1-crawler/
├── crawler.py            # entry point
├── requirements.txt
├── src/
│   ├── config.py         # constantes centralizadas
│   ├── core/
│   │   └── frontier.py   # fila de URLs com politeness por host
│   ├── net/
│   │   ├── robots.py     # cache de robots.txt (Protego)
│   │   └── fetcher.py    # HTTP GET com streaming
│   ├── content/
│   │   ├── url_utils.py  # normalizacao e filtros de URL
│   │   └── parser.py     # extracao de titulo/texto/links
│   └── output/
│       ├── storage.py    # escrita de WARCs rotativos
│       └── metrics.py    # snapshot periodico em CSV
├── seeds/                # arquivos de seed URLs
├── corpus/               # WARCs gerados (runtime)
├── logs/                 # metrics.csv (runtime)
├── docs/                 # relatorio PDF
└── analysis/             # notebook de caracterizacao
```

## Saida

- `corpus/corpus-NNNNN.warc.gz` — 1000 paginas por arquivo, gzip
- `logs/metrics.csv` — snapshots a cada 5s com rate/throughput
- stdout (se `-d`) — JSON por pagina: URL, Title, Text (20 palavras), Timestamp
- stderr — progresso

## Politicas de crawling

1. **Selection**: somente HTML (filtro pre-fetch por extensao + pos-fetch por Content-Type)
2. **Revisitation**: dedup via normalizacao de URL + set global
3. **Parallelization**: 64 threads (configuravel em `src/config.py`)
4. **Politeness**: robots.txt via Protego; delay minimo de 100ms por host
5. **Storage**: WARC compactado com gzip, 1000 paginas por arquivo
