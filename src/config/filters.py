"""
Filtros de URL e MIME: que schemes são aceitos, que extensoes sao
obviamente nao-HTML, e quais Content-Types são aceitos apos o fetch.
"""

# Schemes de URL aceitos. Rejeita ftp, mailto, javascript, data, etc.
ALLOWED_SCHEMES = frozenset({"http", "https"})

# Extensoes que claramente NAO sao HTML. Filtrar antes de fazer a
# requisicao economiza banda e tempo. A lista cobre os casos mais
# comuns; o filtro final eh feito pelo Content-Type da resposta.
NON_HTML_EXTENSIONS = frozenset({
    # Imagens
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico", ".tiff",
    # Documentos
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".rtf",
    # Audio/Video
    ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm", ".ogg", ".wav",
    # Arquivos compactados
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar", ".xz",
    # Executaveis e binarios
    ".exe", ".dmg", ".iso", ".bin", ".apk", ".deb", ".rpm",
    # Dados / outros
    ".css", ".js", ".json", ".xml", ".csv", ".rss", ".atom",
})

# Prefixos de Content-Type considerados como HTML (validacao pos-fetch).
# Comparados em lowercase; "text/html; charset=utf-8" eh HTML valido.
HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")
