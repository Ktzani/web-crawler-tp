"""
config.py
---------
Constantes de configuracao do crawler. Centralizar aqui facilita ajustes
(e.g. experimentos de speedup) sem precisar mexer na logica dos modulos.
"""

# ---------------------------------------------------------------------------
# Paralelismo
# ---------------------------------------------------------------------------
NUM_THREADS = 64

# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
USER_AGENT = "UFMG-IR-Crawler/1.0 (+academic; student assignment)"
HTTP_TIMEOUT = (5, 15)
MAX_PAGE_SIZE = 2 * 1024 * 1024  # 2 MB

# ---------------------------------------------------------------------------
# Politeness
# ---------------------------------------------------------------------------
DEFAULT_CRAWL_DELAY = 0.1  # 100 ms
ROBOTS_TIMEOUT = (3, 5)

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
PAGES_PER_WARC = 1000
WARC_DIR = "corpus"
WARC_PREFIX = "corpus"

# ---------------------------------------------------------------------------
# Frontier e limites de escopo
# ---------------------------------------------------------------------------
MAX_PAGES_PER_HOST = 5000
MAX_QUEUE_PER_HOST = 10000

# ---------------------------------------------------------------------------
# Filtros de URL
# ---------------------------------------------------------------------------
NON_HTML_EXTENSIONS = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico", ".tiff",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".rtf",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm", ".ogg", ".wav",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar", ".xz",
    ".exe", ".dmg", ".iso", ".bin", ".apk", ".deb", ".rpm",
    ".css", ".js", ".json", ".xml", ".csv", ".rss", ".atom",
})

ALLOWED_SCHEMES = frozenset({"http", "https"})
HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")

# ---------------------------------------------------------------------------
# Metricas
# ---------------------------------------------------------------------------
METRICS_INTERVAL = 5.0
METRICS_FILE = "logs/metrics.csv"
