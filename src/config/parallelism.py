"""
parallelism.py
--------------
Configuracoes de paralelismo e coleta de metricas.
"""

# Numero de threads worker. Crawling eh I/O-bound (quase todo o tempo
# eh espera de rede), entao o numero de threads pode ser bem maior que
# o numero de cores da CPU. 64 eh um bom default para saturar a banda
# sem abusar dos servidores alvo.
NUM_THREADS = 16

# Intervalo (em segundos) entre snapshots de metricas no CSV.
METRICS_INTERVAL = 30.0

# Caminho do arquivo de metricas (CSV com colunas:
# timestamp, elapsed, pages_saved, pages_failed, bytes_downloaded, frontier_size).
METRICS_FILE = "data/logs/metrics.csv"

# --- Watchdog de estagnacao ---
# Checa storage.total_saved() a cada WATCHDOG_INTERVAL segundos. Se o
# contador nao subir por WATCHDOG_STALL_SECONDS, limpa as filas do
# frontier e re-enfileira as seeds originais.
WATCHDOG_INTERVAL = 30.0
WATCHDOG_STALL_SECONDS = 60.0
# Minimo de paginas que devem ser salvas dentro da janela de
# WATCHDOG_STALL_SECONDS para considerar que HA progresso. Abaixo disso,
# mesmo com o contador subindo, consideramos estagnado.
WATCHDOG_MIN_PAGES = 10
