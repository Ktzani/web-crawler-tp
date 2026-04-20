# Pipeline de Execução

Passo a passo para rodar o crawler do zero, do setup até a análise do
corpus. Segue a ordem recomendada — cada etapa depende da anterior.

## Pré-requisitos

- **Python 3.14** instalado (`python3 --version`)
- **Sistema operacional:** Linux, macOS ou WSL. No Windows nativo, os
  paths de arquivo podem exigir ajuste.
- **Conexão de internet estável** — o crawl completo dura horas.
- **Espaço em disco:** ~2–5 GB para o corpus de 100k páginas.

## Etapa 1 — Setup do ambiente

```bash
cd pa1-crawler

# Cria e ativa um virtualenv chamado pa1
python3 -m venv .venv

# Linux
source .venv/bin/activate

# Windows 
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

As seeds vão em `seeds/seeds-<matricula>.txt`, uma URL por linha.

```bash
cat > seeds/seeds-2017114124.txt << 'EOF'
https://ucla.edu/
https://whitehouse.gov/
https://estrategiaconcursos.com.br/
# ... mais 47 URLs
EOF
```

**Dicas para escolher boas seeds:**

- **Diversidade é crucial:** 50 seeds de portais grandes (jornais,
  universidades, governos, e-commerces) expandem rapidamente
- **Evite domínios isolados** (blogs pessoais com poucos links externos)
- **Misture idiomas/países** para aumentar cobertura
- **Linhas começando com `#` são comentários** e são ignoradas
- Linhas em branco também são ignoradas

## Etapa 3 — Teste rápido (100 páginas)

Antes de começar o crawl de 100k, **sempre** valide com um crawl pequeno.
Isso garante que seeds, rede e ambiente estão funcionando.

```bash
python3 crawler.py -s seeds/seeds-2017114124.txt -n 10 -d > data/logs/crawl-test.jsonl
ou 
.\.venv\Scripts\python.exe
```

**O que esperar:**

- `stderr` com linhas `[crawler] ...` de progresso
- `stdout` com JSON por página (modo `-d`) — redirecione para arquivo
  se quiser inspecionar
- No final: mensagem `[crawler] concluido: 100 paginas em X.Xs`
- Um arquivo em `corpus/corpus-00000.warc.gz` (~1–5 MB)
- Um CSV em `logs/metrics.csv`

**Tempo esperado:** 30 segundos a 2 minutos, dependendo da latência dos
sites.

**Se algo der errado:**

- **Nenhuma página baixada** → veja `crawl-test.log`; geralmente é seeds
  inválidas ou rede bloqueada
- **Muitas falhas (`pages_failed` alto em `logs/metrics.csv`)** →
  normal para alguns sites; se for a maioria, investigue firewall/DNS
- **Erro de import** → você não ativou o virtualenv (`source pa1/bin/activate`)

## Etapa 4 — Ajustar parâmetros (opcional)

Edite `src/config.py` se quiser ajustar:

```python
NUM_THREADS = 64               # mais threads = mais rápido, até saturar
MAX_PAGES_PER_HOST = 5000      # limita dominio único no corpus
MAX_PAGE_SIZE = 2 * 1024 * 1024  # 2 MB (limite por página)
DEFAULT_CRAWL_DELAY = 0.1       # 100ms, mínimo do enunciado
```

**Recomendação:** começar com o default. Só ajuste depois de observar o
comportamento no teste da Etapa 3.

## Etapa 5 — Crawl completo (100.000 páginas)

```bash
# Limpa corpus anterior se quiser recomeçar do zero
rm -rf corpus/*.warc.gz logs/metrics.csv

# Dispara o crawl completo. SEM -d para não encher o terminal.
# Redireciona stderr para um log de progresso.
python3 crawler.py -s seeds/seeds-2017114124.txt -n 100000 2> logs/crawl.log &

# Acompanha o progresso em outro terminal (ou mesmo, com tail)
tail -f logs/crawl.log
```

**Tempo esperado:** 2–6 horas, dependendo de:
- Diversidade das seeds (mais diverso = mais rápido)
- Velocidade da sua conexão
- Distribuição de `Crawl-delay` nos sites visitados

**Monitoramento:**

- `logs/metrics.csv` atualiza a cada 5s — dá pra plotar em tempo real
- `ls corpus/ | wc -l` mostra quantos WARCs já foram fechados
- Ctrl+C faz shutdown limpo (grava tudo que já foi baixado)

**Ao final:** 100 arquivos `corpus-00000.warc.gz` a `corpus-00099.warc.gz`,
totalizando ~2–5 GB.

## Etapa 6 — Experimentos de speedup (para o relatório)

O relatório pede medição de speedup com N threads variável. Faça rodadas
com `-n` menor (ex: 2000 páginas) variando `NUM_THREADS`:

```bash
# Para cada valor de threads, edita config.py e roda
for N in 1 4 16 32 64 128; do
    # Edita NUM_THREADS em src/config.py (manual ou com sed)
    sed -i "s/^NUM_THREADS = .*/NUM_THREADS = $N/" src/config.py

    rm -rf corpus/* logs/metrics.csv
    time python3 crawler.py -s seeds/seeds-2017114124.txt -n 2000 \
        2> logs/crawl-threads-$N.log

    # Guarda os resultados para análise
    cp logs/metrics.csv logs/metrics-threads-$N.csv
done
```

**Ao final:** 6 CSVs em `logs/metrics-threads-*.csv`. O speedup é
calculado como `tempo(1 thread) / tempo(N threads)`.

## Etapa 7 — Caracterização do corpus

O relatório pede: número de domínios únicos, distribuição de páginas
por domínio, distribuição de tokens por página.

Crie um notebook `analysis/characterize.ipynb` com algo como:

```python
import os
from warcio.archiveiterator import ArchiveIterator
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from collections import Counter

corpus_dir = "corpus"
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
print(f"Top-10 domínios:")
for host, count in hosts.most_common(10):
    print(f"  {host}: {count}")
```

Gere 3 gráficos (use `matplotlib` — **instalar fora do venv `pa1`** para
não contaminar o ambiente do crawler):

1. **Histograma de páginas por domínio** (log-log, mostra cauda longa)
2. **Histograma de tokens por página** (distribuição do tamanho)
3. **Download rate ao longo do tempo** (a partir de `logs/metrics.csv`)

## Etapa 8 — Empacotar para entrega

```bash
# Faz upload do corpus para o Google Drive e obtém o link compartilhável
# (o enunciado pede link do corpus, não o corpus no zip)

# Monta o zip de entrega (código + relatório, sem o corpus)
zip -r entrega.zip \
    crawler.py requirements.txt README.md \
    src/ seeds/ docs/ analysis/ \
    -x "corpus/*" "logs/*" "__pycache__/*" "*.pyc" "pa1/*"
```

O pacote final deve conter:

- **Código-fonte** (`crawler.py`, `src/`, `seeds/`, `requirements.txt`)
- **Relatório PDF** em `docs/` (máximo 2 páginas, template ACM sigconf)
- **Link do Google Drive** com o corpus (separado, no Moodle ou no PDF)

## Troubleshooting rápido

| Sintoma | Causa provável | Solução |
|---|---|---|
| `ModuleNotFoundError: src` | Rodando de dentro do `src/` | Sempre rode da raiz do projeto |
| `ModuleNotFoundError: requests` | Venv não ativado | `source pa1/bin/activate` |
| Crawler "trava" nas primeiras URLs | Seeds com `robots.txt` bloqueando | Normal se seeds bloqueiam o bot; verifique `robots.txt` dos sites |
| Muitas páginas com `timeout` | Conexão lenta ou sites pesados | Aumentar `HTTP_TIMEOUT` em `config.py` |
| `MemoryError` ou OOM | Frontier gigante demais | Reduzir `MAX_QUEUE_PER_HOST` |
| Crawl rápido demais, poucas páginas | Seeds muito restritas | Aumentar número de seeds ou diversidade |
| WARC corrompido | Crash durante escrita | Usar Ctrl+C ao parar, nunca `kill -9` |

## Limpeza

Para começar do zero (mantém código, descarta dados):

```bash
rm -rf corpus/*.warc.gz
rm -rf logs/*.csv logs/*.log
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
```
