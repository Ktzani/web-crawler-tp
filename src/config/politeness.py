"""
Configuracoes de politeness: delay minimo entre requests, timeout de
robots.txt e limites por host.
"""

# Delay minimo (segundos) entre requests consecutivos ao mesmo host.
# Se o robots.txt declarar Crawl-delay maior, o maior prevalece.
DEFAULT_CRAWL_DELAY = 0.1  # 100 ms

# Timeout para baixar robots.txt: (connect, read).
ROBOTS_TIMEOUT = (3, 5)

# Limite brando de paginas por host (evita dominio unico no corpus).
MAX_PAGES_PER_HOST = 5000

# Tamanho maximo da fila de URLs pendentes por host.
MAX_QUEUE_PER_HOST = 10000
