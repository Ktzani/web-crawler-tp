"""
parser.py
---------
Extrai do HTML: titulo, texto visivel e outlinks. Usa BeautifulSoup com
o parser da stdlib (html.parser) para nao depender de lxml.
"""

from dataclasses import dataclass
from bs4 import BeautifulSoup

from src.content.url_utils import resolve_url, is_valid_for_crawling


@dataclass
class ParsedPage:
    title: str
    text: str
    text_preview: str          # primeiras 20 palavras (debug mode)
    outlinks: list[str]


def parse_html(html: str, base_url: str) -> ParsedPage:
    """Parseia HTML. Retorna titulo, texto e outlinks validos."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove elementos que nao fazem parte do texto visivel.
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    text = soup.get_text(separator=" ", strip=True)
    text = " ".join(text.split())  # normaliza whitespace

    words = text.split()
    text_preview = " ".join(words[:20])

    # Outlinks: <a href=...> resolvidos e filtrados. Set dedup na pagina.
    outlinks_set: set[str] = set()
    for a in soup.find_all("a", href=True):
        resolved = resolve_url(base_url, a["href"])
        if resolved is None:
            continue
        if not is_valid_for_crawling(resolved):
            continue
        outlinks_set.add(resolved)

    return ParsedPage(
        title=title,
        text=text,
        text_preview=text_preview,
        outlinks=list(outlinks_set),
    )
