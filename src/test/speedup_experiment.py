#!/usr/bin/env python3
"""
speedup_experiment.py
---------------------
Roda o crawler varias vezes com diferentes valores de NUM_THREADS e
gera um CSV com os resultados. Usa as MESMAS seeds em todas as rodadas
para comparacao justa.

Saida: logs/speedup.csv com colunas:
  num_threads, run, elapsed_sec, pages_saved, pages_per_sec

Uso:
    python3 speedup_experiment.py [--seeds FILE] [--limit N] [--runs R] \\
        [--threads 1,2,4,8,16,32,64]

Exemplo tipico:
    python3 speedup_experiment.py --seeds seeds/seeds-2017114124.txt \\
        --limit 2000 --runs 3 --threads 1,2,4,8,16,32,64,128

Leva ~1-2h dependendo dos parametros. Para teste rapido use --limit 500.
"""

import argparse
import csv
import os
import re
import subprocess
import sys
import time


def patch_num_threads(value: int):
    """
    Modifica src/config/parallelism.py para usar o NUM_THREADS desejado.
    Retorna o valor anterior (para restaurar depois).
    """
    path = "src/config/parallelism.py"
    with open(path, "r") as f:
        content = f.read()

    # Regex que pega o valor atual de NUM_THREADS
    match = re.search(r"^NUM_THREADS\s*=\s*(\d+)", content, re.MULTILINE)
    if not match:
        print(f"ERRO: nao achei NUM_THREADS em {path}", file=sys.stderr)
        sys.exit(1)
    previous = int(match.group(1))

    # Substitui
    new_content = re.sub(
        r"^NUM_THREADS\s*=\s*\d+",
        f"NUM_THREADS = {value}",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    with open(path, "w") as f:
        f.write(new_content)

    return previous


def run_one(seeds: str, limit: int) -> tuple[float, int]:
    """
    Executa um crawl e retorna (elapsed_sec, pages_saved).
    Lê o stderr do crawler procurando a linha "concluido: X paginas em Ys".
    """
    # Limpa corpus e logs para nao contaminar entre rodadas
    for d in ["data/corpus", "data/logs"]:
        if os.path.isdir(d):
            for f in os.listdir(d):
                os.remove(os.path.join(d, f))

    t_start = time.time()
    with open("data/logs/debug.jsonl", "w") as debug_file:
        result = subprocess.run(
            [sys.executable, "crawler.py", "-s", seeds, "-n", str(limit), "-d"],
            stdout=debug_file,           # stdout vai DIRETO pro arquivo
            stderr=subprocess.PIPE,      # stderr ainda capturado (usado pro parse)
            text=True,
            timeout=limit * 4,
        )
    t_elapsed = time.time() - t_start

    # Tenta extrair o "X paginas em Ys" do stderr
    match = re.search(
        r"concluido:\s*(\d+)\s*paginas\s*em\s*([\d.]+)\s*s",
        result.stderr,
    )
    if match:
        pages = int(match.group(1))
        elapsed = float(match.group(2))
        return elapsed, pages
    else:
        # Fallback: usa o tempo medido externamente
        print("  AVISO: nao consegui parsear stderr, usando tempo externo",
              file=sys.stderr)
        print(f"  stderr: {result.stderr[-500:]}", file=sys.stderr)
        return t_elapsed, 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", default="seeds/seeds-test.txt",
                        help="Arquivo de seeds (mesmo para todas as rodadas)")
    parser.add_argument("--limit", type=int, default=2000,
                        help="Paginas por rodada (default: 2000)")
    parser.add_argument("--runs", type=int, default=3,
                        help="Repeticoes por nivel de thread (default: 3)")
    parser.add_argument("--threads", default="1,2,4,8,16,32,64",
                        help="Niveis de thread separados por virgula")
    parser.add_argument("--output", default="data/logs/speedup.csv",
                        help="CSV de saida")
    args = parser.parse_args()

    thread_levels = [int(x) for x in args.threads.split(",")]

    if not os.path.exists(args.seeds):
        print(f"ERRO: seeds nao existem em {args.seeds}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    # Salva o valor original para restaurar no final
    original_threads = None

    results = []
    total_runs = len(thread_levels) * args.runs
    run_counter = 0

    try:
        print(f"=== Experimento de speedup ===")
        print(f"Seeds:   {args.seeds}")
        print(f"Limite:  {args.limit} paginas/rodada")
        print(f"Threads: {thread_levels}")
        print(f"Rodadas: {args.runs} por nivel = {total_runs} total")
        print(f"Tempo estimado: ~{total_runs * args.limit / 30 / 60:.0f} min (pessimista)")
        print()

        for n_threads in thread_levels:
            # Aplica o valor dessa rodada
            prev = patch_num_threads(n_threads)
            if original_threads is None:
                original_threads = prev

            for run_id in range(1, args.runs + 1):
                run_counter += 1
                print(f"[{run_counter}/{total_runs}] NUM_THREADS={n_threads} "
                      f"run={run_id}/{args.runs}... ", end="", flush=True)

                try:
                    elapsed, pages = run_one(args.seeds, args.limit)
                    rate = pages / elapsed if elapsed > 0 else 0
                    print(f"{pages} paginas em {elapsed:.1f}s ({rate:.1f} pg/s)")
                    results.append({
                        "num_threads": n_threads,
                        "run": run_id,
                        "elapsed_sec": round(elapsed, 2),
                        "pages_saved": pages,
                        "pages_per_sec": round(rate, 2),
                    })
                except subprocess.TimeoutExpired:
                    print("TIMEOUT (descartado)")
                    continue

    finally:
        # Restaura NUM_THREADS original
        if original_threads is not None:
            patch_num_threads(original_threads)
            print(f"\nRestaurado NUM_THREADS={original_threads}")

    # Escreve o CSV
    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["num_threads", "run", "elapsed_sec",
                        "pages_saved", "pages_per_sec"],
        )
        writer.writeheader()
        writer.writerows(results)

    print(f"\n=== Resultados salvos em {args.output} ===\n")

    # Imprime resumo agregado (media por nivel de threads)
    by_threads: dict[int, list[float]] = {}
    for r in results:
        by_threads.setdefault(r["num_threads"], []).append(r["elapsed_sec"])

    baseline = None
    print(f"{'threads':>8}  {'avg_time':>9}  {'avg_rate':>10}  {'speedup':>8}  {'efic':>6}")
    print("-" * 52)
    for n in sorted(by_threads):
        times = by_threads[n]
        avg_time = sum(times) / len(times)
        avg_rate = args.limit / avg_time
        if baseline is None:
            baseline = avg_time
        speedup = baseline / avg_time
        efficiency = speedup / n
        print(f"{n:>8}  {avg_time:>8.1f}s  {avg_rate:>7.1f} pg/s  "
              f"{speedup:>7.2f}x  {efficiency*100:>5.1f}%")


if __name__ == "__main__":
    main()