"""
Configuracoes de armazenamento: WARC e diretorio de saida.
"""

# Paginas por arquivo WARC.
PAGES_PER_WARC = 1000

# Diretorio onde os WARCs serao escritos (criado se nao existir).
WARC_DIR = "data/corpus"

# Prefixo do nome dos arquivos gerados (ex: corpus-00000.warc.gz).
WARC_PREFIX = "corpus"

# Log append-only de URLs processadas, usado para retomar apos crash.
VISITED_FILE = "data/visited.txt"

# A cada quantas paginas é feito fsync no log de visitados.
VISITED_FSYNC_EVERY = 50
