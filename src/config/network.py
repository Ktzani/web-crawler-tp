"""
Configuracoes de rede: HTTP, User-Agent e limites de tamanho.
"""

# User-Agent honesto: identifica o crawler como bot academico. Fingir
# ser um browser eh anti-etico e pode ignorar regras de robots.txt que
# se aplicam especificamente a bots.
USER_AGENT = "UFMG-IR-Crawler/1.0 (+academic; student assignment)"

# Timeout da requisicao HTTP em segundos: (connect_timeout, read_timeout).
# Connect curto (5s) descarta rapido hosts inacessiveis; read maior (15s)
# tolera servidores lentos. Sem timeout, uma pagina travada seguraria
# uma thread indefinidamente.
HTTP_TIMEOUT = (5, 15)

# Tamanho maximo de pagina em bytes. Paginas > 2 MB sao raras e quase
# sempre sao dumps ou binarios disfarcados. Truncar evita que uma pagina
# gigante trave uma thread.
MAX_PAGE_SIZE = 2 * 1024 * 1024  # 2 MB
