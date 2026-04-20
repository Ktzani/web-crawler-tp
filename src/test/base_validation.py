# extract_html.py
import os
from warcio.archiveiterator import ArchiveIterator
from urllib.parse import urlparse

os.makedirs("data/extracted", exist_ok=True)

counter = 0
for filename in sorted(os.listdir("C:\\Users\\gabri\\Documents\\GitHub\\web-crawler-tp\\data\\corpus")):
    if not filename.endswith(".warc.gz"):
        continue
    with open(f"C:\\Users\\gabri\\Documents\\GitHub\\web-crawler-tp\\data\\corpus\\{filename}", "rb") as f:
        for record in ArchiveIterator(f):
            if record.rec_type != "response":
                continue
            uri = record.rec_headers.get_header("WARC-Target-URI")
            body = record.content_stream().read()

            # Nome de arquivo seguro a partir do host
            host = urlparse(uri).netloc.replace(".", "_")
            out_path = f"data/extracted/{counter:05d}_{host}.html"
            with open(out_path, "wb") as out:
                out.write(body)
            counter += 1

print(f"{counter} arquivos HTML extraidos em data/extracted/")