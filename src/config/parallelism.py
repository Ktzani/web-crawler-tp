"""
parallelism.py
--------------
Configuracoes de paralelismo e coleta de metricas.
"""

# Numero de threads worker. Crawling eh I/O-bound (quase todo o tempo
# eh espera de rede), entao o numero de threads pode ser bem maior que
# o numero de cores da CPU. 64 eh um bom default para saturar a banda
# sem abusar dos servidores alvo.
NUM_THREADS = 1

# Intervalo (em segundos) entre snapshots de metricas no CSV.
METRICS_INTERVAL = 5.0

# Caminho do arquivo de metricas (CSV com colunas:
# timestamp, elapsed, pages_saved, pages_failed, bytes_downloaded, frontier_size).
METRICS_FILE = "data/logs/metrics.csv"
