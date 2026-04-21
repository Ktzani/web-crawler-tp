# Pipeline de Execução

Passo a passo para rodar o crawler do zero, do setup até a análise do
corpus. Segue a ordem recomendada — cada etapa depende da anterior.

## Pré-requisitos

- **Python 3.14** instalado (`python3 --version`)
- **Sistema operacional:** Linux, macOS, WSL ou Windows nativo. Os
  caminhos padrão usam `/` e funcionam nos três — os comandos abaixo
  trazem a variante PowerShell quando relevante.
- **Conexão de internet estável** — o crawl completo dura horas.
- **Espaço em disco:** ~2–5 GB para o corpus de 100k páginas em
  `data/corpus/`.

## Etapa 1 — Setup do ambiente

```bash
cd web-crawler-tp

# Cria o virtualenv
python3 -m venv .venv

# Linux / macOS / WSL
source .venv/bin/activate

# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1

# Instala exatamente as libs do requirements.txt
pip3 install -r requirements.txt
```

**Verificação:**

```bash
python3 -c "import requests, bs4, warcio, protego, url_normalize; print('OK')"
```

Se imprimir `OK`, as dependências estão instaladas.

## Etapa 2 — Preparar as seeds

As seeds vão em `seeds/seeds-<matricula>.txt`, uma URL por linha. O
repositório já traz dezenas de arquivos em `seeds/` — você pode
apontar o crawler para um único arquivo ou para o diretório inteiro
(ele concatena todos os `.txt` e deduplica).

```bash
cat > seeds/seeds-2017114124.txt << 'EOF'
https://ucla.edu/
https://whitehouse.gov/
https://estrategiaconcursos.com.br/
# ... mais URLs
EOF
```

**Dicas para escolher boas seeds:**

- **Diversidade é crucial:** seeds de portais grandes (jornais,
  universidades, governos, e-commerces) expandem rapidamente
- **Evite domínios isolados** (blogs pessoais com poucos links externos)
- **Misture idiomas/países** para aumentar cobertura
- **Linhas começando com `#` são comentários** e são ignoradas
- Linhas em branco também são ignoradas

## Etapa 3 — Teste rápido (10 páginas)

Antes de começar o crawl de 100k, **sempre** valide com um crawl pequeno.
Isso garante que seeds, rede e ambiente estão funcionando.

```bash
# Linux / macOS / WSL
python3 crawler.py -s seeds/seeds-2017114124.txt -n 10 -d > data/logs/crawl-test.jsonl

# Windows (PowerShell)
.\.venv\Scripts\python.exe crawler.py -s seeds\seeds-2017114124.txt -n 10 -d `
    > data\logs\crawl-test.jsonl
```

**O que esperar:**

- `stderr` com linhas `[crawler] ...` de progresso (via `logging`)
- `stdout` com JSON por página (modo `-d`) — redirecione para arquivo
  se quiser inspecionar
- No final: mensagem `[crawler] concluido: 10 paginas em X.Xs`
- Um arquivo em `data/corpus/corpus-00000.warc.gz` (~centenas de KB)
- Um CSV em `data/logs/metrics.csv`
- Um log `data/visited.txt` com uma URL por linha

**Tempo esperado:** 30 segundos a 2 minutos, dependendo da latência dos
sites.

**Se algo der errado:**

- **Nenhuma página baixada** → veja o log em `data/logs/`; geralmente é
  seeds inválidas ou rede bloqueada
- **Muitas falhas (`pages_failed` alto em `data/logs/metrics.csv`)** →
  normal para alguns sites; se for a maioria, investigue firewall/DNS
- **Erro de import** → você não ativou o virtualenv

## Etapa 4 — Ajustar parâmetros (opcional)

A config foi quebrada em 5 arquivos dentro de `src/config/`, por tema:

| Arquivo | Conteúdo típico |
|---|---|
| `parallelism.py` | `NUM_THREADS` (default 16), `METRICS_INTERVAL = 30s`, `METRICS_FILE` |
| `network.py` | `USER_AGENT`, `HTTP_TIMEOUT`, `MAX_PAGE_SIZE` |
| `politeness.py` | `DEFAULT_CRAWL_DELAY`, `MAX_PAGES_PER_HOST`, `MAX_QUEUE_PER_HOST`, `ROBOTS_TIMEOUT` |
| `filters.py` | `ALLOWED_SCHEMES`, `NON_HTML_EXTENSIONS`, prefixos de Content-Type HTML |
| `storage.py` | `PAGES_PER_WARC`, `WARC_DIR`, `WARC_PREFIX`, `VISITED_FILE`, `VISITED_FSYNC_EVERY` |

**Recomendação:** começar com os defaults. Só ajuste depois de observar
o comportamento no teste da Etapa 3.

## Etapa 5 — Crawl completo (100.000 páginas)

```bash
# Limpa corpus anterior se quiser recomeçar do zero
rm -rf data/corpus/*.warc.gz data/logs/metrics.csv data/visited.txt

# Dispara o crawl completo. SEM -d para não encher o terminal.
# Redireciona stderr para um log de progresso.
python3 crawler.py -s seeds/seeds-2017114124.txt -n 100000 2> data/logs/crawl.log

# Acompanha o progresso em outro terminal
tail -f data/logs/crawl.log
```

**Se a conexão cair no meio do caminho**, retome com `-r`:

```bash
python3 crawler.py -s seeds/seeds-2017114124.txt -n 100000 -r 2>> data/logs/crawl.log
```

O `-r` lê `data/visited.txt`, marca todas as URLs já processadas como
"visto" no frontier e ajusta o contador do storage — ou seja, o crawl
continua de onde parou sem re-baixar nada.

**Tempo esperado:** 2–6 horas, dependendo de:
- Diversidade das seeds (mais diverso = mais rápido)
- Velocidade da sua conexão
- Distribuição de `Crawl-delay` nos sites visitados

**Monitoramento:**

- `data/logs/metrics.csv` atualiza a cada 30s — dá pra plotar em tempo real
- `ls data/corpus/ | wc -l` mostra quantos WARCs já foram fechados
- `wc -l data/visited.txt` mostra quantas URLs já foram processadas
- Ctrl+C faz shutdown limpo (deadline de 10s, grava tudo que já baixou)

**Ao final:** 100 arquivos `corpus-00000.warc.gz` a `corpus-00099.warc.gz`
em `data/corpus/`, totalizando ~2–5 GB.

## Etapa 6 — Experimentos de speedup

Já existe um script pronto em `src/test/speedup_experiment.py` que
automatiza a variação de `NUM_THREADS` (ele patcha temporariamente
`src/config/parallelism.py` e restaura no final):

```bash
python3 src/test/speedup_experiment.py \
    --seeds seeds/seeds-2017114124.txt \
    --limit 2000 \
    --runs 3 \
    --threads 1,2,4,8,16,32,64
```

**Saída:** `data/logs/speedup.csv` com colunas
`num_threads, run, elapsed_sec, pages_saved, pages_per_sec`.

O speedup é calculado como `tempo(1 thread) / tempo(N threads)`.

## Etapa 7 — Caracterização do corpus

O relatório pede: número de domínios únicos, distribuição de páginas
por domínio, distribuição de tokens por página.

Para facilitar a inspeção manual, use `src/test/extract_corpus.py` para
expandir os WARCs em arquivos `.html` individuais em `data/extracted/`:

```bash
python3 src/test/extract_corpus.py --corpus-dir data/corpus --out-dir data/extracted
```

Para a caracterização propriamente dita, crie um notebook em
`data/analysis/characterize.ipynb` com algo como:

```python
import os
from warcio.archiveiterator import ArchiveIterator
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from collections import Counter

corpus_dir = "data/corpus"
hosts = Counter()
tokens_per_page = []

for filename in sorted(os.listdir(corpus_dir)):
    path = os.path.join(corpus_dir, filename)
    with open(path, "rb") as f:
        for record in ArchiveIterator(f):
            if record.rec_type != "response":
                continue
            uri = record.rec_headers.get_header("WARC-Target-URI")
            host = urlparse(uri).netloc
            hosts[host] += 1

            body = record.content_stream().read()
            soup = BeautifulSoup(body, "html.parser")
            for tag in soup(["script", "style"]):
                tag.decompose()
            text = soup.get_text(separator=" ", strip=True)
            tokens_per_page.append(len(text.split()))

print(f"Domínios únicos: {len(hosts)}")
print(f"Páginas totais: {sum(hosts.values())}")
print("Top-10 domínios:")
for host, count in hosts.most_common(10):
    print(f"  {host}: {count}")
```

Gere 3 gráficos (use `matplotlib` — instale fora do `.venv` do crawler
para não contaminar o ambiente):

1. **Histograma de páginas por domínio** (log-log, mostra cauda longa)
2. **Histograma de tokens por página** (distribuição do tamanho)
3. **Download rate ao longo do tempo** (a partir de `data/logs/metrics.csv`)

## Etapa 8 — Empacotar para entrega

```bash
# Faz upload do corpus para o Google Drive e obtém o link compartilhável
# (o enunciado pede link do corpus, não o corpus no zip)

# Monta o zip de entrega (código + relatório, sem o corpus)
zip -r entrega.zip \
    crawler.py requirements.txt README.md \
    src/ seeds/ docs/ \
    -x "data/*" "__pycache__/*" "*.pyc" ".venv/*"
```

O pacote final deve conter:

- **Código-fonte** (`crawler.py`, `src/`, `seeds/`, `requirements.txt`)
- **Relatório PDF** em `docs/` (máximo 2 páginas, template ACM sigconf)
- **Link do Google Drive** com o corpus (separado, no Moodle ou no PDF)

## Troubleshooting rápido

| Sintoma | Causa provável | Solução |
|---|---|---|
| `ModuleNotFoundError: src` | Rodando de dentro do `src/` | Sempre rode da raiz do projeto |
| `ModuleNotFoundError: requests` | Venv não ativado | Reative o `.venv` |
| Crawler "trava" nas primeiras URLs | Seeds com `robots.txt` bloqueando | Normal; verifique `robots.txt` dos sites |
| Muitas páginas com `timeout` | Conexão lenta ou sites pesados | Aumentar `HTTP_TIMEOUT` em `src/config/network.py` |
| `MemoryError` ou OOM | Frontier gigante demais | Reduzir `MAX_QUEUE_PER_HOST` em `src/config/politeness.py` |
| Crawl rápido demais, poucas páginas | Seeds muito restritas | Aumentar número de seeds ou diversidade |
| WARC corrompido | Crash durante escrita | Use Ctrl+C ao parar, nunca `kill -9` |
| Conexão caiu durante crawl | Rede instável | Rode de novo com `-r` para continuar de onde parou |

## Limpeza

Para começar do zero (mantém código, descarta dados):

```bash
rm -rf data/corpus/*.warc.gz
rm -rf data/logs/*.csv data/logs/*.log
rm -f data/visited.txt
rm -rf data/extracted/*
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
```
