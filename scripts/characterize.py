"""Caracterizacao do corpus: paginas, dominios, tokens.

Versao paralela: usa multiprocessing para processar WARCs em paralelo,
e regex (sem BeautifulSoup) para contar tokens.
"""
import multiprocessing as mp
import os
import re
import sys
from collections import Counter
from pathlib import Path
from statistics import mean, median
from urllib.parse import urlparse

from warcio.archiveiterator import ArchiveIterator

CORPUS_DIR = Path("data/corpus")
OUT_DIR = Path("data/analysis")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SCRIPT_STYLE_RE = re.compile(rb"<(script|style|noscript|template)\b[^>]*>.*?</\1>", re.I | re.S)
TAG_RE = re.compile(rb"<[^>]+>")
ENTITY_RE = re.compile(rb"&[#a-zA-Z0-9]+;")
TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def percentile(values, p):
    if not values:
        return 0
    s = sorted(values)
    k = int(round((p / 100) * (len(s) - 1)))
    return s[k]


def process_warc(path: str):
    """Processa um WARC. Retorna (pages_per_domain, tokens_per_page, size)."""
    size = os.path.getsize(path)
    per_domain = Counter()
    tokens = []
    with open(path, "rb") as fh:
        for rec in ArchiveIterator(fh):
            if rec.rec_type != "response":
                continue
            url = rec.rec_headers.get_header("WARC-Target-URI") or ""
            host = urlparse(url).hostname or ""
            try:
                payload = rec.content_stream().read()
            except Exception:
                continue

            body = SCRIPT_STYLE_RE.sub(b" ", payload)
            body = TAG_RE.sub(b" ", body)
            body = ENTITY_RE.sub(b" ", body)
            try:
                text = body.decode("utf-8", errors="ignore")
            except Exception:
                continue
            tok = len(TOKEN_RE.findall(text))
            tokens.append(tok)
            per_domain[host] += 1
    return per_domain, tokens, size


def main():
    warc_files = [str(p) for p in sorted(CORPUS_DIR.glob("*.warc.gz"))]
    n_workers = min(mp.cpu_count(), len(warc_files), 12)
    print(f"Processing {len(warc_files)} WARCs with {n_workers} workers...", file=sys.stderr)

    pages_per_domain = Counter()
    tokens_per_page = []
    total_bytes = 0

    with mp.Pool(n_workers) as pool:
        for i, (pd, tk, sz) in enumerate(pool.imap_unordered(process_warc, warc_files), 1):
            pages_per_domain.update(pd)
            tokens_per_page.extend(tk)
            total_bytes += sz
            print(f"[{i}/{len(warc_files)}] pages={len(tokens_per_page)}", file=sys.stderr)

    total_pages = len(tokens_per_page)
    ppd = list(pages_per_domain.values())
    tpp = tokens_per_page

    with open(OUT_DIR / "summary.txt", "w", encoding="utf-8") as f:
        f.write(f"Total pages: {total_pages}\n")
        f.write(f"Unique domains: {len(pages_per_domain)}\n")
        f.write(f"Compressed size (GB): {total_bytes / (1024**3):.2f}\n")
        f.write("\nPages/domain\n")
        f.write(f"  mean: {mean(ppd):.2f}\n")
        f.write(f"  median: {median(ppd):.0f}\n")
        f.write(f"  p90: {percentile(ppd, 90)}\n")
        f.write(f"  max: {max(ppd)}\n")
        f.write("\nTokens/page\n")
        f.write(f"  mean: {mean(tpp):.2f}\n")
        f.write(f"  median: {median(tpp):.0f}\n")
        f.write(f"  p90: {percentile(tpp, 90)}\n")
        f.write(f"  max: {max(tpp)}\n")
        f.write(f"  min: {min(tpp)}\n")
        f.write("\nTop 10 domains\n")
        for host, cnt in pages_per_domain.most_common(10):
            f.write(f"  {host}\t{cnt}\n")

        bins = [0, 100, 500, 1000, 2000, 5000, 10000, 10**9]
        labels = ["<100", "100-500", "500-1k", "1k-2k", "2k-5k", "5k-10k", "10k+"]
        counts = [0] * (len(bins) - 1)
        for t in tpp:
            for i in range(len(bins) - 1):
                if bins[i] <= t < bins[i + 1]:
                    counts[i] += 1
                    break
        f.write("\nToken distribution\n")
        for lbl, c in zip(labels, counts):
            f.write(f"  {lbl}\t{c}\n")

    print("Done. See data/analysis/summary.txt")


if __name__ == "__main__":
    main()
