"""Classifica seeds como visitadas (diretamente), redirecionadas ou nao visitadas."""
import os
import sys
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

seeds = set()
for fname in sorted(os.listdir(os.path.join(ROOT, "seeds"))):
    with open(os.path.join(ROOT, "seeds", fname), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                seeds.add(line)

visited = set(
    line.strip() for line in open(os.path.join(ROOT, "data", "visited.txt"), encoding="utf-8")
    if line.strip()
)

visited_hosts = set()
for u in visited:
    try:
        h = urlparse(u).netloc.lower()
        if h.startswith("www."):
            h = h[4:]
        visited_hosts.add(h)
    except Exception:
        pass

direct = []
redirected = []
missed = []

for s in sorted(seeds):
    if s in visited:
        direct.append(s)
        continue
    host = urlparse(s).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    # qualquer URL do mesmo host (ou subdominio) presente?
    hit = any(
        h == host or h.endswith("." + host)
        for h in visited_hosts
    )
    if hit:
        redirected.append(s)
    else:
        missed.append(s)

print(f"Total de seeds: {len(seeds)}")
print(f"Visitadas diretamente: {len(direct)}")
print(f"Host presente (provavel redirect/subdominio): {len(redirected)}")
print(f"Nao visitadas: {len(missed)}")
print()
print("=== Nao visitadas ===")
for s in missed:
    print(s)
