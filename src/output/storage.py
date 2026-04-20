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
import re
import threading
from io import BytesIO
from urllib.parse import urlparse

from warcio.archiveiterator import ArchiveIterator
from warcio.warcwriter import WARCWriter
from warcio.statusandheaders import StatusAndHeaders

from src.config.network import USER_AGENT
from src.config.storage import (
    PAGES_PER_WARC,
    VISITED_FILE,
    VISITED_FSYNC_EVERY,
    WARC_DIR,
    WARC_PREFIX,
)
from src.network.fetcher import FetchResult

def _host_of(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:
        return ""

class WarcStorage:
    """Gerencia escrita rotativa de WARC.gz. Thread-safe."""

    def __init__(
        self,
        output_dir: str = WARC_DIR,
        prefix: str = WARC_PREFIX,
        visited_path: str = VISITED_FILE,
        resume: bool = False,
    ):
        self._dir = output_dir
        self._prefix = prefix
        self._visited_path = visited_path
        os.makedirs(self._dir, exist_ok=True)
        os.makedirs(os.path.dirname(visited_path) or ".", exist_ok=True)

        # Lock serializa escritas. Escrita em disco eh muito mais rapida
        # que I/O de rede, entao esse lock nao vira gargalo.
        self._lock = threading.Lock()

        # Estado do arquivo atual (inicializado preguicosamente).
        self._current_file = None
        self._current_writer = None
        self._current_file_index = 0
        self._current_count = 0
        self._total_saved = 0
        self._since_fsync = 0

        last = self._last_warc(self._dir, prefix)
        if resume and last is not None:
            idx, path = last
            pages = self.repair_warc(path)
            self._current_file = open(path, "ab")
            self._current_writer = WARCWriter(self._current_file, gzip=True)
            self._current_count = pages
            self._current_file_index = idx + 1
        elif last is not None:
            # Crawl novo mas ja existem WARCs antigos no diretorio: avanca o
            # indice para nao sobrescrever silenciosamente. Quem quiser comecar
            # do zero deve apagar o diretorio antes.
            self._current_file_index = last[0] + 1

        mode = "ab" if resume else "wb"
        self._visited_log = open(visited_path, mode, buffering=0)
        
    def set_initial_count(self, count: int):
        """Ajusta contador para execucoes que retomam crawls anteriores."""
        with self._lock:
            self._total_saved = count

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

            self._visited_log.write((result.final_url + "\n").encode("utf-8"))
            self._since_fsync += 1
            if self._since_fsync >= VISITED_FSYNC_EVERY:
                os.fsync(self._visited_log.fileno())
                self._since_fsync = 0
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
                
            if self._visited_log is not None:
                try:
                    os.fsync(self._visited_log.fileno())
                except OSError:
                    pass
                self._visited_log.close()
                self._visited_log = None

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
        
    @staticmethod
    def _last_warc(directory: str, prefix: str) -> tuple[int, str] | None:
        """Retorna (indice, caminho) do ultimo WARC existente, ou None."""
        if not os.path.isdir(directory):
            return None
        pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)\.warc\.gz$")
        matches = [(int(m.group(1)), f) for f in os.listdir(directory) if (m := pattern.match(f))]
        if not matches:
            return None
        idx, name = max(matches)
        return idx, os.path.join(directory, name)
    
    @staticmethod
    def repair_warc(path: str) -> int:
        """
        Trunca o WARC ate o fim do ultimo record completo e legivel.
        Retorna o numero de records 'response' (== paginas) preservados.
        """
        last_good_end = 0
        pages = 0
        try:
            with open(path, "rb") as f:
                it = ArchiveIterator(f)
                while True:
                    try:
                        record = next(it)
                    except StopIteration:
                        break
                    except Exception:
                        break
                    try:
                        record.content_stream().read()
                        end = it.get_record_offset() + it.get_record_length()
                        if record.rec_type == "response":
                            pages += 1
                        last_good_end = end
                    except Exception:
                        break
        except Exception:
            return 0

        size = os.path.getsize(path)
        if last_good_end < size:
            with open(path, "r+b") as f:
                f.truncate(last_good_end)
        return pages

