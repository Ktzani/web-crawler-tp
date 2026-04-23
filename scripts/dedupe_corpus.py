"""
Reescreve os WARCs em data/corpus removendo paginas cuja URL ja apareceu antes.
Mantem a 1a ocorrencia (request + response) e descarta as subsequentes.
Gera arquivos novos com rotacao de PAGES_PER_WARC paginas por WARC.

O corpus original e movido para data/corpus.bak/ antes da reescrita.
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from warcio.archiveiterator import ArchiveIterator
from warcio.warcwriter import WARCWriter

from src.config.storage import PAGES_PER_WARC, WARC_DIR, WARC_PREFIX


def main():
    src_dir = WARC_DIR + ".bak"
    dst_dir = WARC_DIR

    if not os.path.isdir(dst_dir):
        print(f"Diretorio {dst_dir} nao existe.")
        return 1

    if os.path.isdir(src_dir):
        print(f"Backup {src_dir} ja existe. Remova ou renomeie antes de rodar.")
        return 1

    print(f"Movendo {dst_dir} -> {src_dir} (backup)...")
    shutil.move(dst_dir, src_dir)
    os.makedirs(dst_dir, exist_ok=True)

    files = sorted(
        f for f in os.listdir(src_dir)
        if f.startswith(WARC_PREFIX + "-") and f.endswith(".warc.gz")
    )
    print(f"Processando {len(files)} WARCs...")

    seen = set()
    pairs_kept = 0
    pairs_dropped = 0
    total_response = 0

    writer = None
    out_file = None
    out_index = 0
    out_count = 0

    def rotate():
        nonlocal writer, out_file, out_index, out_count
        if out_file is not None:
            out_file.close()
        name = f"{WARC_PREFIX}-{out_index:05d}.warc.gz"
        path = os.path.join(dst_dir, name)
        out_file = open(path, "wb")
        writer = WARCWriter(out_file, gzip=True)
        out_index += 1
        out_count = 0

    rotate()

    for fname in files:
        path = os.path.join(src_dir, fname)
        with open(path, "rb") as f:
            pending_request = None
            pending_request_url = None
            for record in ArchiveIterator(f):
                url = record.rec_headers.get_header("WARC-Target-URI")
                rtype = record.rec_type

                if rtype == "request":
                    # Bufferiza ate achar o response correspondente.
                    pending_request = record
                    pending_request_url = url
                elif rtype == "response":
                    total_response += 1
                    if url in seen:
                        pairs_dropped += 1
                        pending_request = None
                        pending_request_url = None
                        continue
                    seen.add(url)

                    if out_count >= PAGES_PER_WARC:
                        rotate()

                    if pending_request is not None and pending_request_url == url:
                        writer.write_record(pending_request)
                    writer.write_record(record)
                    pending_request = None
                    pending_request_url = None
                    out_count += 1
                    pairs_kept += 1

                    if pairs_kept % 5000 == 0:
                        print(f"  ... {pairs_kept} paginas mantidas, {pairs_dropped} descartadas")

    if out_file is not None:
        out_file.close()

    print()
    print(f"Records 'response' lidos: {total_response}")
    print(f"Paginas mantidas (unicas): {pairs_kept}")
    print(f"Paginas descartadas (duplicadas): {pairs_dropped}")
    print(f"WARCs escritos: {out_index}")
    print(f"Backup em: {src_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())