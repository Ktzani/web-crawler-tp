"""
metrics.py
----------
Coleta de metricas para analise posterior (graficos de rate ao longo do
tempo e speedup por threads). Grava um CSV com snapshots periodicos.
"""

import csv
import glob
import os
import re
import threading
import time

from src.config.parallelism import METRICS_INTERVAL

class Metrics:
    """
    Contadores cumulativos + snapshot periodico em CSV. Thread-safe.

    paginas SALVAS vem do WarcStorage.total_saved() para nao duplicar
    contagem; aqui trackeamos apenas pages_failed e bytes_downloaded.
    """

    def __init__(
        self, 
        output_path: str = "logs/metrics.csv", 
        interval: float = METRICS_INTERVAL
    ):
        self._output_path = output_path
        self._interval = interval

        self._pages_failed = 0
        self._bytes_downloaded = 0
        self._lock = threading.Lock()

        self._snapshot_thread: threading.Thread | None = None
        self._csv_file = None
        self._csv_writer = None
        self._start_time: float | None = None

    def record_success(self, n_bytes: int):
        with self._lock:
            self._bytes_downloaded += n_bytes

    def record_failure(self):
        with self._lock:
            self._pages_failed += 1

    def start(self, storage, frontier, stop_event: threading.Event):
        """Dispara a thread de snapshot."""
        output_dir = os.path.dirname(self._output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        self._output_path = self._next_round_path(self._output_path)

        self._csv_file = open(self._output_path, "w", newline="", encoding="utf-8")
        self._csv_writer = csv.writer(self._csv_file)
        self._csv_writer.writerow([
            "timestamp", "elapsed", "pages_saved", "pages_failed",
            "bytes_downloaded", "frontier_size",
        ])
        self._csv_file.flush()

        self._start_time = time.time()
        self._snapshot_thread = threading.Thread(
            target=self._snapshot_loop,
            args=(storage, frontier, stop_event),
            name="metrics-snapshot",
            daemon=True,
        )
        self._snapshot_thread.start()

    def close(self):
        if self._snapshot_thread is not None:
            self._snapshot_thread.join(timeout=self._interval + 1.0)
        if self._csv_file is not None:
            self._csv_file.close()
            self._csv_file = None

    def _snapshot_loop(self, storage, frontier, stop_event: threading.Event):
        while not stop_event.is_set():
            if stop_event.wait(timeout=self._interval):
                break
            self._write_snapshot(storage, frontier)
        # Snapshot final antes de sair.
        self._write_snapshot(storage, frontier)

    @staticmethod
    def _next_round_path(base_path: str) -> str:
        output_dir, filename = os.path.split(base_path)
        stem, ext = os.path.splitext(filename)
        n = 1
        while True:
            candidate = os.path.join(output_dir, f"{stem}_round_{n}{ext}")
            if not os.path.exists(candidate):
                return candidate
            n += 1

    def _write_snapshot(self, storage, frontier):
        now = time.time()
        elapsed = now - self._start_time if self._start_time else 0.0

        with self._lock:
            failed = self._pages_failed
            bytes_dl = self._bytes_downloaded

        saved = storage.total_saved()
        pending = frontier.size()

        self._csv_writer.writerow([
            f"{now:.3f}", f"{elapsed:.3f}",
            saved, failed, bytes_dl, pending,
        ])
        self._csv_file.flush()
