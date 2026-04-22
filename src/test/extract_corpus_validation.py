#!/usr/bin/env python3
"""
extract_html.py
---------------
Extrai cada pagina HTML do corpus WARC para um arquivo .html individual.
Util para inspecao manual (abrir no browser) e validacao.

Uso:
    python analysis/extract_html.py [--corpus-dir corpus] [--out-dir data/extracted/html]

Gera arquivos nomeados como:
    00000_example_com.html
    00001_www_iana_org.html
    ...
O prefixo numerico preserva a ordem de crawling.
"""

import argparse
import os
import sys
from urllib.parse import urlparse
from warcio.archiveiterator import ArchiveIterator


def safe_filename(url: str, counter: int) -> str:
    """Gera um nome de arquivo seguro a partir da URL."""
    host = urlparse(url).netloc.replace(".", "_").replace(":", "_")
    # Limita tamanho do host pra nao estourar o limite de nome do OS
    host = host[:80] if host else "unknown"
    return f"{counter:05d}_{host}.html"


def extract_corpus(corpus_dir: str, out_dir: str, limit: int | None = None):
    os.makedirs(out_dir, exist_ok=True)

    warc_files = sorted(
        f for f in os.listdir(corpus_dir) if f.endswith(".warc.gz")
    )
    if not warc_files:
        print(f"ERRO: nenhum .warc.gz em {corpus_dir}/", file=sys.stderr)
        sys.exit(1)

    print(f"Lendo {len(warc_files)} arquivos WARC...", file=sys.stderr)

    counter = 0
    for warc_name in warc_files:
        path = os.path.join(corpus_dir, warc_name)
        with open(path, "rb") as f:
            for record in ArchiveIterator(f):
                if record.rec_type != "response":
                    continue

                uri = record.rec_headers.get_header("WARC-Target-URI") or "unknown"
                body = record.content_stream().read()

                filename = safe_filename(uri, counter)
                out_path = os.path.join(out_dir, filename)
                with open(out_path, "wb") as out:
                    out.write(body)

                counter += 1
                if limit and counter >= limit:
                    print(f"Atingiu limite de {limit} paginas.", file=sys.stderr)
                    print(f"-> {counter} HTMLs extraidos em {out_dir}/", file=sys.stderr)
                    return

        print(f"  {warc_name}: {counter} paginas acumuladas", file=sys.stderr)

    print(f"-> {counter} HTMLs extraidos em {out_dir}/", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Extrai paginas HTML do corpus WARC para arquivos individuais."
    )
    parser.add_argument("--corpus-dir", default="corpus",
                        help="Diretorio com os .warc.gz (default: corpus)")
    parser.add_argument("--out-dir", default="data/extracted/html",
                        help="Diretorio de saida (default: data/extracted/html)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Extrai no maximo N paginas (default: todas)")
    args = parser.parse_args()

    extract_corpus(args.corpus_dir, args.out_dir, args.limit)


if __name__ == "__main__":
    main()