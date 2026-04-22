"""
Baixa paginas HTML via HTTP. Responsavel por:
  - Manter uma Session por thread (keep-alive, pool de conexoes)
  - Fazer GET com timeout e streaming
  - Validar Content-Type (apenas HTML)
  - Truncar respostas acima do limite configurado
  - Retornar os bytes crus (necessarios para o WARC) e metadados
"""

import threading
from dataclasses import dataclass

import requests

from src.config.network import USER_AGENT, HTTP_TIMEOUT, MAX_PAGE_SIZE
from src.config.filters import HTML_CONTENT_TYPES


# Session por thread: keep-alive aumenta muito a performance. Session NAO
# é garantidamente thread-safe, entao ha uma por thread.
_thread_local = threading.local()

def _get_session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})
        _thread_local.session = session
    return session


@dataclass
class FetchResult:
    ok: bool
    url: str # URL pedida originalmente
    final_url: str # URL efetiva apos redirects
    status_code: int | None
    content_type: str
    raw_bytes: bytes
    error: str


def fetch(url: str) -> FetchResult:
    """
    Baixa a pagina apontada por `url`. Sempre retorna FetchResult (nunca
    None ou excecao): o chamador so precisa olhar `ok`.

    Fluxo:
      1. GET streaming (nao baixa body ainda)
      2. Se status >= 400 ou Content-Type nao-HTML: descarta sem ler body
      3. Le o body em chunks, truncando se passar de MAX_PAGE_SIZE
    """
    session = _get_session()

    try:
        resp = session.get(
            url, timeout=HTTP_TIMEOUT, stream=True, allow_redirects=True,
        )
    except requests.Timeout:
        return _error(url, None, "timeout")
    except requests.TooManyRedirects:
        return _error(url, None, "too_many_redirects")
    except requests.ConnectionError as e:
        return _error(url, None, f"connection_error: {type(e).__name__}")
    except requests.RequestException as e:
        return _error(url, None, f"request_error: {type(e).__name__}")
    except Exception as e:
        return _error(url, None, f"unknown: {type(e).__name__}")

    try:
        final_url = resp.url
        status = resp.status_code
        content_type = resp.headers.get("Content-Type", "")

        if status >= 400:
            return FetchResult(
                ok=False, url=url, final_url=final_url, status_code=status,
                content_type=content_type, raw_bytes=b"", error=f"http_{status}",
            )

        ct_lower = content_type.lower()
        if not any(ct_lower.startswith(prefix) for prefix in HTML_CONTENT_TYPES):
            return FetchResult(
                ok=False, url=url, final_url=final_url, status_code=status,
                content_type=content_type, raw_bytes=b"",
                error="non_html_content_type",
            )

        chunks: list[bytes] = []
        total = 0
        try:
            for chunk in resp.iter_content(chunk_size=16 * 1024, decode_unicode=False):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_PAGE_SIZE:
                    return FetchResult(
                        ok=False, url=url, final_url=final_url,
                        status_code=status, content_type=content_type,
                        raw_bytes=b"", error="too_large",
                    )
                chunks.append(chunk)
        except requests.RequestException as e:
            return _error(url, final_url, f"read_error: {type(e).__name__}")

        body = b"".join(chunks)

        return FetchResult(
            ok=True, url=url, final_url=final_url, status_code=status,
            content_type=content_type, raw_bytes=body, error="",
        )

    finally:
        resp.close()


def _error(url: str, final_url: str | None, msg: str) -> FetchResult:
    return FetchResult(
        ok=False,
        url=url,
        final_url=final_url if final_url else url,
        status_code=None,
        content_type="",
        raw_bytes=b"",
        error=msg,
    )
