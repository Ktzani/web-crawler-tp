"""
Configuracoes de rede: HTTP, User-Agent e limites de tamanho.
"""

# User-Agent identificando o crawler como bot academico.
USER_AGENT = "UFMG-IR-Crawler/1.0 (+academic; student assignment)"

# Timeout HTTP em segundos: (connect_timeout, read_timeout).
HTTP_TIMEOUT = (5, 15)

# Tamanho maximo de pagina em bytes.
MAX_PAGE_SIZE = 2 * 1024 * 1024  # 2 MB