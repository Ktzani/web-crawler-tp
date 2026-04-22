"""
Configuracoes de politeness: delay minimo entre requests, timeout de
robots.txt e limites por host.
"""

# Delay minimo (segundos) entre requests consecutivos para o mesmo host.
# 100ms eh o minimo exigido pelo enunciado. Se o robots.txt declarar
# Crawl-delay maior, o maior prevalece.
DEFAULT_CRAWL_DELAY = 0.1  # 100 ms

# Timeout especifico para baixar robots.txt: (connect, read). Menor que
# o timeout geral porque robots.txt eh pequeno e falhar eh aceitavel
# (fallback eh "tudo permitido").
ROBOTS_TIMEOUT = (3, 5)

# Limite brando de paginas por host. Impede que um unico site domine
# o corpus (importante para a distribuicao por dominio exigida no
# relatorio) e defesa contra spider traps profundas.
MAX_PAGES_PER_HOST = 5000

# Tamanho maximo da fila de URLs pendentes por host. Evita consumo de
# memoria descontrolado quando um site tem muitos links internos.
MAX_QUEUE_PER_HOST = 10000
