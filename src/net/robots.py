"""
robots.py
---------
Cache thread-safe de arquivos robots.txt por host. Usa Protego para parsing.

O cache eh critico por dois motivos:
  1. Politeness: nao faz sentido baixar robots.txt toda vez que vamos
     crawlear uma URL do mesmo host.
  2. Corretude: se 64 threads comecam a crawlear o mesmo host ao mesmo
     tempo, todas tentariam baixar robots.txt simultaneamente. O lock
     garante que apenas UMA baixa e as outras esperam o resultado.
"""

import threading
from urllib.parse import urlparse

import requests
from protego import Protego

from src.config import USER_AGENT, ROBOTS_TIMEOUT, DEFAULT_CRAWL_DELAY
from src.content.url_utils import get_host


class RobotsCache:
    """Cache de decisoes de robots.txt por host."""

    def __init__(self):
        self._cache: dict[str, tuple[Protego | None, float]] = {}
        self._lock = threading.Lock()
        # Locks por host para evitar thundering herd no fetch do robots.
        self._host_locks: dict[str, threading.Lock] = {}
        self._host_locks_guard = threading.Lock()

    def can_fetch(self, url: str) -> bool:
        """Retorna True se robots.txt permite baixar a URL. Liberal em erros."""
        host = get_host(url)
        if host is None:
            return False
        parser, _ = self._get_or_fetch(host, url)
        if parser is None:
            return True
        try:
            return parser.can_fetch(url, USER_AGENT)
        except Exception:
            return True

    def crawl_delay(self, url: str) -> float:
        """Delay minimo entre requisicoes para o host. Sempre >= 100ms."""
        host = get_host(url)
        if host is None:
            return DEFAULT_CRAWL_DELAY
        _, delay = self._get_or_fetch(host, url)
        return delay

    def _get_or_fetch(self, host: str, sample_url: str):
        # Double-checked locking: fast path sem contencao pesada.
        with self._lock:
            entry = self._cache.get(host)
            if entry is not None:
                return entry

        host_lock = self._get_host_lock(host)
        with host_lock:
            # Re-check apos pegar o lock do host.
            with self._lock:
                entry = self._cache.get(host)
                if entry is not None:
                    return entry

            entry = self._fetch_and_parse(host, sample_url)
            with self._lock:
                self._cache[host] = entry
            return entry

    def _get_host_lock(self, host: str) -> threading.Lock:
        with self._host_locks_guard:
            lock = self._host_locks.get(host)
            if lock is None:
                lock = threading.Lock()
                self._host_locks[host] = lock
            return lock

    def _fetch_and_parse(self, host: str, sample_url: str):
        """
        Baixa e parseia robots.txt. Regras de tratamento de resposta:
          - 2xx: parseia o conteudo
          - 404/410: nao existe, tudo permitido
          - 401/403: bloqueio total (servidor protegeu o proprio robots)
          - outros erros / timeout: liberal (nao travar por erro transiente)
        """
        scheme = urlparse(sample_url).scheme or "https"
        robots_url = f"{scheme}://{host}/robots.txt"

        try:
            resp = requests.get(
                robots_url,
                headers={"User-Agent": USER_AGENT},
                timeout=ROBOTS_TIMEOUT,
                allow_redirects=True,
            )
        except requests.RequestException:
            return (None, DEFAULT_CRAWL_DELAY)

        status = resp.status_code

        if status in (404, 410):
            return (None, DEFAULT_CRAWL_DELAY)

        if status in (401, 403):
            deny_all = Protego.parse("User-agent: *\nDisallow: /\n")
            return (deny_all, DEFAULT_CRAWL_DELAY)

        if status >= 400:
            return (None, DEFAULT_CRAWL_DELAY)

        try:
            parser = Protego.parse(resp.text)
        except Exception:
            return (None, DEFAULT_CRAWL_DELAY)

        try:
            declared_delay = parser.crawl_delay(USER_AGENT)
        except Exception:
            declared_delay = None

        if declared_delay is None:
            effective_delay = DEFAULT_CRAWL_DELAY
        else:
            effective_delay = max(float(declared_delay), DEFAULT_CRAWL_DELAY)

        return (parser, effective_delay)
