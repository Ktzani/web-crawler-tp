"""
Configuracoes de paralelismo e coleta de metricas.
"""

# Numero de threads worker (crawling é I/O-bound).
NUM_THREADS = 16

# Intervalo (em segundos) entre snapshots de metricas no CSV.
METRICS_INTERVAL = 30.0

# Caminho do arquivo de metricas (CSV com colunas:
# timestamp, elapsed, pages_saved, pages_failed, bytes_downloaded, frontier_size).
METRICS_FILE = "data/logs/metrics.csv"

# Watchdog: se o contador de paginas salvas nao subir o suficiente
# dentro da janela, limpa as filas e re-enfileira as seeds.
WATCHDOG_INTERVAL = 30.0
WATCHDOG_STALL_SECONDS = 60.0

# Minimo de paginas salvas na janela para considerar que ha progresso.
WATCHDOG_MIN_PAGES = 10
