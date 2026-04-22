"""
Filtros de URL e MIME: que schemes são aceitos, que extensoes sao
obviamente nao-HTML, e quais Content-Types são aceitos apos o fetch.
"""

# Schemes de URL aceitos.
ALLOWED_SCHEMES = frozenset({"http", "https"})

# Extensoes que claramente nao sao HTML (filtradas antes do fetch).
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

# Prefixos de Content-Type aceitos como HTML.
HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")
