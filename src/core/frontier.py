"""
Fila de URLs pendentes para crawling, com politeness por host.

ESTRUTURA DE DADOS
------------------
Em vez de uma fila FIFO global (que bloquearia muitas threads no mesmo
host), o frontier mantem uma fila por host:

  _queues:     dict host -> deque[url]       # URLs pendentes por host
  _next_time:  dict host -> float            # proximo timestamp permitido
  _ready_heap: heap de (next_time, host)     # ordena hosts por prontidao
  _seen:       set[url]                      # dedup global
  _host_count: dict host -> int              # paginas aceitas por host

CONCORRENCIA
------------
Um unico lock protege todas as estruturas. Operacoes do frontier sao
rapidas (memoria); threads passam a maior parte do tempo em I/O de rede.
"""

import heapq
import os
import threading
import time
from collections import deque

from src.config.politeness import (
    DEFAULT_CRAWL_DELAY,
    MAX_PAGES_PER_HOST,
    MAX_QUEUE_PER_HOST,
)

from src.config.storage import VISITED_FILE, VISITED_FSYNC_EVERY

from src.content.url_utils import get_host, is_valid_for_crawling
from src.network.robots import RobotsCache


_EMPTY = (None, None)


class Frontier:
    """Fila thread-safe de URLs para crawling, com politeness por host."""

    def __init__(
        self,
        robots: RobotsCache,
        visited_path: str = VISITED_FILE,
        resume: bool = False,
    ):
        self._robots = robots

        self._queues: dict[str, deque[str]] = {}
        self._next_time: dict[str, float] = {}
        self._ready_heap: list[tuple[float, str]] = []
        self._seen: set[str] = set()
        self._host_count: dict[str, int] = {}

        self._pending_urls = 0

        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)

        self._visited_path = visited_path
        os.makedirs(os.path.dirname(visited_path) or ".", exist_ok=True)
        mode = "a" if resume else "w"
        self._visited_log = open(visited_path, mode, encoding="utf-8")
        self._since_fsync = 0

    def add(self, url: str) -> bool:
        """Enfileira URL se válida, nova e permitida por robots."""
        if not is_valid_for_crawling(url):
            return False

        host = get_host(url)
        if host is None:
            return False

        # Checa robots ANTES do lock: pode envolver rede, e segurar o
        # lock global durante uma requisicao é indesejavel.
        if not self._robots.can_fetch(url):
            return False

        with self._cond:
            if url in self._seen:
                return False

            if self._host_count.get(host, 0) >= MAX_PAGES_PER_HOST:
                return False

            q = self._queues.get(host)
            if q is not None and len(q) >= MAX_QUEUE_PER_HOST:
                return False

            self._seen.add(url)
            self._host_count[host] = self._host_count.get(host, 0) + 1

            if q is None:
                q = deque()
                self._queues[host] = q
                self._next_time[host] = 0.0
                heapq.heappush(self._ready_heap, (0.0, host))

            q.append(url)
            self._pending_urls += 1
            self._cond.notify()
            return True

    def get_next(self, stop_event: threading.Event) -> tuple[str | None, float | None]:
        """
        Retira a proxima URL. Bloqueia ate haver trabalho OU stop_event.
        Retorna (None, None) se o crawler deve parar.
        """
        while not stop_event.is_set():
            with self._cond:
                if not self._ready_heap:
                    if self._pending_urls == 0:
                        return _EMPTY
                    self._cond.wait(timeout=0.5)
                    continue

                next_ready, host = self._ready_heap[0]
                now = time.monotonic()

                if next_ready > now:
                    wait_for = min(next_ready - now, 0.5)
                    self._cond.wait(timeout=wait_for)
                    continue

                heapq.heappop(self._ready_heap)
                # Lazy deletion: entradas stale no heap (next_time mudou)
                # sao simplesmente descartadas.
                if self._next_time.get(host) != next_ready:
                    continue

                q = self._queues.get(host)
                if not q:
                    continue

                url = q.popleft()
                self._pending_urls -= 1

                # Nao re-adicionamos o host na heap aqui - sera feito em
                # release_host() com o next_time atualizado pelo crawl_delay.
                return (url, now)

        return _EMPTY

    def release_host(self, url: str):
        """
        Libera o host de uma URL processada. Atualiza next_time e
        re-enfileira na heap se houver mais URLs pendentes.

        DEVE ser chamado apos cada URL pega via get_next, com sucesso ou nao.
        """
        host = get_host(url)
        if host is None:
            return

        delay = self._robots.crawl_delay(url)
        if delay <= 0:
            delay = DEFAULT_CRAWL_DELAY

        with self._cond:
            next_time = time.monotonic() + delay
            self._next_time[host] = next_time

            q = self._queues.get(host)
            if q:
                heapq.heappush(self._ready_heap, (next_time, host))
                self._cond.notify()


    def size(self) -> int:
        with self._lock:
            return self._pending_urls

    def clear_queues(self, forget: list[str] | None = None):
        """
        Esvazia as filas pendentes por host (bolha de hosts dominantes),
        preservando _seen e _host_count - URLs ja visitadas nao sao
        re-baixadas nem hosts ja saturados sao reabertos.

        forget: URLs a remover do _seen para permitir que sejam
        re-enfileiradas (tipicamente as seeds originais).
        """
        with self._cond:
            self._queues.clear()
            self._next_time.clear()
            self._ready_heap.clear()
            self._pending_urls = 0
            if forget:
                for url in forget:
                    self._seen.discard(url)
            self._cond.notify_all()

    def notify_all(self):
        """Acorda todas as threads (usado no shutdown)."""
        with self._cond:
            self._cond.notify_all()
            
    def mark_visited(self, urls):
        """Marca URLs como ja vistas (usado no resume para nao reprocessar)."""
        with self._lock:
            for url in urls:
                if url in self._seen:
                    continue
                self._seen.add(url)
                host = get_host(url)
                if host is not None:
                    self._host_count[host] = self._host_count.get(host, 0) + 1
            
    def record_visited(self, url: str):
        """Appenda URL ao log de visitados, com flush+fsync a cada N."""
        with self._lock:
            if self._visited_log is None:
                return
            self._visited_log.write(url + "\n")
            self._since_fsync += 1
            if self._since_fsync >= VISITED_FSYNC_EVERY:
                self._visited_log.flush()
                os.fsync(self._visited_log.fileno())
                self._since_fsync = 0

    def load_visited(self) -> list[str]:
        if not os.path.exists(self._visited_path):
            return []
        with open(self._visited_path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

    def close(self):
        with self._lock:
            if self._visited_log is not None:
                try:
                    self._visited_log.flush()
                    os.fsync(self._visited_log.fileno())
                except OSError:
                    pass
                self._visited_log.close()
                self._visited_log = None
