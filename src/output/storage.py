"""
storage.py
----------
Escrita de arquivos WARC (.warc.gz), rotacionando a cada N paginas.

Para cada pagina salvamos dois registros:
  - 'request': os metadados da requisicao que fizemos
  - 'response': a resposta HTTP completa (status line + headers + body)

Isso segue a convencao do Heritrix/IA e torna o corpus auto-contido.
"""

import os
import threading
from io import BytesIO
from urllib.parse import urlparse

from warcio.warcwriter import WARCWriter
from warcio.statusandheaders import StatusAndHeaders

from src.config.network import USER_AGENT
from src.config.storage import PAGES_PER_WARC, WARC_DIR, WARC_PREFIX
from src.network.fetcher import FetchResult


class WarcStorage:
    """Gerencia escrita rotativa de WARC.gz. Thread-safe."""

    def __init__(self, output_dir: str = WARC_DIR, prefix: str = WARC_PREFIX):
        self._dir = output_dir
        self._prefix = prefix
        os.makedirs(self._dir, exist_ok=True)

        # Lock serializa escritas. Escrita em disco eh muito mais rapida
        # que I/O de rede, entao esse lock nao vira gargalo.
        self._lock = threading.Lock()

        # Estado do arquivo atual (inicializado preguicosamente).
        self._current_file = None
        self._current_writer = None
        self._current_file_index = 0
        self._current_count = 0
        self._total_saved = 0

    def store(self, result: FetchResult) -> bool:
        """Grava o resultado de um fetch bem-sucedido. Retorna True se gravou."""
        if not result.ok or not result.raw_bytes:
            return False

        with self._lock:
            if self._current_writer is None or self._current_count >= PAGES_PER_WARC:
                self._rotate()

            self._write_pair(result)
            self._current_count += 1
            self._total_saved += 1
            return True

    def total_saved(self) -> int:
        with self._lock:
            return self._total_saved

    def close(self):
        with self._lock:
            if self._current_file is not None:
                self._current_file.close()
                self._current_file = None
                self._current_writer = None

    def _rotate(self):
        """Fecha o WARC atual (se houver) e abre o proximo."""
        if self._current_file is not None:
            self._current_file.close()

        filename = f"{self._prefix}-{self._current_file_index:05d}.warc.gz"
        path = os.path.join(self._dir, filename)

        self._current_file = open(path, "wb")
        self._current_writer = WARCWriter(self._current_file, gzip=True)
        self._current_file_index += 1
        self._current_count = 0

    def _write_pair(self, result: FetchResult):
        """Escreve os registros 'request' e 'response' para uma pagina."""
        # --- Record de REQUEST ---
        request_headers = StatusAndHeaders(
            "GET / HTTP/1.1",
            [("User-Agent", USER_AGENT), ("Host", _host_of(result.final_url))],
            is_http_request=True,
        )
        request_record = self._current_writer.create_warc_record(
            result.final_url, "request", http_headers=request_headers,
        )

        # --- Record de RESPONSE ---
        status_line = f"HTTP/1.1 {result.status_code} OK"
        response_http_headers = StatusAndHeaders(
            status_line,
            [("Content-Type", result.content_type)],
            protocol="HTTP/1.1",
        )
        response_record = self._current_writer.create_warc_record(
            result.final_url, "response",
            payload=BytesIO(result.raw_bytes),
            http_headers=response_http_headers,
        )

        # Amarra request -> response via Concurrent-To.
        request_record.rec_headers.add_header(
            "WARC-Concurrent-To",
            response_record.rec_headers.get_header("WARC-Record-ID"),
        )

        self._current_writer.write_record(request_record)
        self._current_writer.write_record(response_record)


def _host_of(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:
        return ""
