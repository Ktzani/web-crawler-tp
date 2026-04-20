"""
storage.py
----------
Configuracoes de armazenamento: WARC e diretorio de saida.
"""

# Quantidade de paginas por arquivo WARC. O enunciado exige 1000, entao
# para 100k paginas sao gerados exatamente 100 arquivos.
PAGES_PER_WARC = 1000

# Diretorio onde os WARCs serao escritos. Criado se nao existir.
WARC_DIR = "data/corpus"

# Prefixo do nome dos arquivos gerados (ex: corpus-00000.warc.gz,
# corpus-00001.warc.gz, ...).
WARC_PREFIX = "corpus"
