"""
url_utils.py
------------
Utilidades para lidar com URLs: normalizacao canonica, extracao de host
e filtros de escopo (scheme, extensao).
"""

from urllib.parse import urlparse, urljoin, urldefrag
from url_normalize import url_normalize

from src.config.filters import ALLOWED_SCHEMES, NON_HTML_EXTENSIONS

def normalize_url(url: str) -> str | None:
    """
    Normaliza uma URL para uma forma canonica usada como chave de dedup.

    Passos:
      1. Remove o fragment (#...): fragments sao client-side.
      2. Valida scheme ANTES de url_normalize (a lib "conserta" strings
         sem scheme prefixando https://, criando URLs fantasmas).
      3. Aplica url_normalize: lowercase do host, portas default, etc.
    """
    if not url:
        return None

    try:
        url_no_frag, _ = urldefrag(url.strip())
        if not url_no_frag:
            return None

        pre_parsed = urlparse(url_no_frag)
        if not pre_parsed.scheme or pre_parsed.scheme not in ALLOWED_SCHEMES:
            return None
        if not pre_parsed.netloc:
            return None

        normalized = url_normalize(url_no_frag)

        post_parsed = urlparse(normalized)
        if post_parsed.scheme not in ALLOWED_SCHEMES or not post_parsed.netloc:
            return None

        return normalized
    except Exception:
        return None


def resolve_url(base: str, link: str) -> str | None:
    """Resolve URL relativa em relacao a base e normaliza."""
    if not link:
        return None
    stripped = link.strip()
    if not stripped or stripped.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
        return None
    try:
        absolute = urljoin(base, stripped)
        return normalize_url(absolute)
    except Exception:
        return None


def get_host(url: str) -> str | None:
    """Extrai o host (netloc). Usado como chave de politeness por host."""
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        return netloc or None
    except Exception:
        return None


def has_non_html_extension(url: str) -> bool:
    """Heuristica pre-fetch: URLs com extensao obviamente nao-HTML."""
    try:
        path = urlparse(url).path.lower()
        dot_idx = path.rfind(".")
        if dot_idx == -1:
            return False
        ext = path[dot_idx:]
        if len(ext) > 10:
            return False
        return ext in NON_HTML_EXTENSIONS
    except Exception:
        return False


def is_valid_for_crawling(url: str) -> bool:
    """Filtro combinado: normalizavel, scheme http(s), nao-extensao-binaria."""
    normalized = normalize_url(url)
    if normalized is None:
        return False
    if has_non_html_extension(normalized):
        return False
    return True
