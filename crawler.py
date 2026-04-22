#!/usr/bin/env python3
"""
crawler.py
----------
Entry point do web crawler. Orquestra os demais modulos:

  seeds -> Frontier -> [N workers] -> Fetcher -> Parser -> Storage
                                               +-> enqueue outlinks

Uso:
  python3 crawler.py -s <seeds_file> -n <limit> [-d]

Argumentos:
  -s, --seeds   Arquivo com URLs iniciais (uma por linha).
  -n, --limit   Numero alvo de paginas a baixar.
  -d, --debug   Modo debug: imprime JSON por pagina em stdout.
"""

import argparse
import json
import os
import sys
import threading
import time

# Garante que 'src/' eh encontrado independente de onde rodamos o script.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config.parallelism import (
    NUM_THREADS, METRICS_FILE,
    WATCHDOG_INTERVAL, WATCHDOG_STALL_SECONDS, WATCHDOG_MIN_PAGES,
)
from src.core.frontier import Frontier
from src.network.robots import RobotsCache
from src.network.fetcher import fetch
from src.content.parser import parse_html
from src.output.storage import WarcStorage
from src.output.metrics import Metrics

from logging import basicConfig, getLogger, INFO

basicConfig(level=INFO)
logger = getLogger(__name__)

def worker(
    worker_id: int,
    frontier: Frontier,
    storage: WarcStorage,
    metrics: Metrics,
    stop_event: threading.Event,
    limit: int,
    debug: bool,
):
    """
    Loop principal de uma thread worker.

    Repete ate stop_event ser setado OU o frontier ficar vazio:
      1. Pega a proxima URL (bloqueia se preciso)
      2. Faz o fetch
      3. Se OK e eh HTML: parseia, armazena, e enfileira os outlinks
      4. Chama release_host para atualizar o delay do host (em finally)
    """
    while not stop_event.is_set():
        url, _ = frontier.get_next(stop_event)
        if url is None:
            return

        try:
            result = fetch(url)

            if not result.ok:
                metrics.record_failure()
                continue

            try:
                parsed = parse_html(
                    result.raw_bytes.decode("utf-8", errors="replace"),
                    result.final_url,
                )
            except Exception:
                metrics.record_failure()
                continue

            saved = storage.store(result)
            if not saved:
                metrics.record_failure()
                continue

            frontier.record_visited(result.final_url)
            metrics.record_success(len(result.raw_bytes))

            if debug:
                record = {
                    "URL": result.final_url,
                    "Title": parsed.title,
                    "Text": parsed.text_preview,
                    "Timestamp": int(time.time()),
                }
                print(json.dumps(record, ensure_ascii=False), flush=True)

            # Verifica limite logo apos incrementar.
            if storage.total_saved() >= limit:
                stop_event.set()
                frontier.notify_all()
                return

            # Enfileira outlinks descobertos.
            for link in parsed.outlinks:
                if stop_event.is_set():
                    break
                frontier.add(link)

        finally:
            # SEMPRE liberamos o host, mesmo em caso de erro.
            frontier.release_host(url)


def watchdog(
    frontier: Frontier,
    storage: WarcStorage,
    seeds: list[str],
    stop_event: threading.Event,
    interval: float = WATCHDOG_INTERVAL,
    stall_seconds: float = WATCHDOG_STALL_SECONDS,
    min_pages: int = WATCHDOG_MIN_PAGES,
):
    """
    Monitora storage.total_saved() em janelas de stall_seconds. Se numa
    janela foram salvas menos que min_pages paginas, limpa as filas do
    frontier e re-enfileira as seeds originais ("restart" sem matar o
    processo).

    _seen e _host_count sao preservados -- nao re-baixamos URLs ja
    visitadas nem reabrimos hosts ja saturados.
    """
    checkpoint_count = storage.total_saved()
    checkpoint_time = time.monotonic()

    while not stop_event.is_set():
        if stop_event.wait(timeout=interval):
            return

        now = time.monotonic()
        window = now - checkpoint_time
        if window < stall_seconds:
            continue

        current = storage.total_saved()
        delta = current - checkpoint_count

        if delta >= min_pages:
            checkpoint_count = current
            checkpoint_time = now
            continue

        logger.warning(
            f"[watchdog] apenas {delta} paginas em {window:.0f}s "
            f"(min={min_pages}). Reiniciando frontier..."
        )
        frontier.clear_queues(forget=seeds)
        re_enqueued = sum(1 for u in seeds if frontier.add(u))
        logger.info(f"[watchdog] {re_enqueued} seeds re-enfileiradas")
        checkpoint_count = storage.total_saved()
        checkpoint_time = time.monotonic()


def load_seeds(path: str) -> list[str]:
    """
    Le seeds de um arquivo OU de um diretorio.
    Se for diretorio, concatena todos os .txt dentro (dedup preservando ordem).
    Ignora linhas vazias e comentarios.
    """
    if os.path.isdir(path):
        files = sorted(
            os.path.join(path, f)
            for f in os.listdir(path)
            if f.endswith(".txt")
        )
    else:
        files = [path]

    seen: set[str] = set()
    seeds: list[str] = []
    for filepath in files:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line in seen:
                    continue
                seen.add(line)
                seeds.append(line)
    return seeds


def main():
    parser = argparse.ArgumentParser(description="Simple polite web crawler.")
    parser.add_argument("-s", "--seeds", required=True, help="Arquivo de seeds.")
    parser.add_argument("-n", "--limit", required=True, type=int, help="Numero de paginas.")
    parser.add_argument("-d", "--debug", action="store_true", help="Modo debug (JSON em stdout).")
    parser.add_argument("-r", "--resume", action="store_true", help="Retoma de onde parou usando data/visited.txt.")
    args = parser.parse_args()

    seeds = load_seeds(args.seeds)
    if not seeds:
        logger.error("ERRO: arquivo de seeds vazio.")
        sys.exit(1)

    logger.info(f"[crawler] {len(seeds)} seeds carregadas")
    logger.info(f"[crawler] alvo: {args.limit} paginas com {NUM_THREADS} threads")
    robots = RobotsCache()
    frontier = Frontier(robots, resume=args.resume)
    storage = WarcStorage(resume=args.resume)
    metrics = Metrics(output_path=METRICS_FILE)
    stop_event = threading.Event()
    start_time = time.time()

    if args.resume:
        visited = frontier.load_visited()
        frontier.mark_visited(visited)
        storage.set_initial_count(len(visited))  
        logger.info(f"[crawler] retomando: {len(visited)} URLs ja processadas")
        if storage.total_saved() >= args.limit: 
            logger.info(f"[crawler] limite ja atingido ({storage.total_saved()}/{args.limit}), nada a fazer")
            storage.close()
            frontier.close()
            sys.exit(0)

    enqueued = 0
    for url in seeds:
        if frontier.add(url):
            enqueued += 1
    logger.info(f"[crawler] {enqueued}/{len(seeds)} seeds enfileiradas")

    if enqueued == 0:
        if args.resume and visited:
            logger.info(f"[crawler] nenhuma seed nova, mas {len(visited)} URLs ja visitadas. "
                        f"Nada a fazer: precisa de seeds novas ou descobrir outlinks. Abortando.")
        else:
            logger.error("ERRO: nenhuma seed valida.")
        sys.exit(1)

    metrics.start(storage, frontier, stop_event)

    watchdog_thread = threading.Thread(
        target=watchdog,
        args=(frontier, storage, seeds, stop_event),
        name="watchdog",
        daemon=True,
    )
    watchdog_thread.start()

    threads = []
    for i in range(NUM_THREADS):
        t = threading.Thread(
            target=worker,
            args=(i, frontier, storage, metrics, stop_event, args.limit, args.debug),
            name=f"worker-{i}",
            daemon=True,
        )
        t.start()
        threads.append(t)

    try:
        while any(t.is_alive() for t in threads):
            for t in threads:
                t.join(timeout=0.2)
    except KeyboardInterrupt:
        logger.warning("\n[crawler] Ctrl+C recebido. Fazendo shutdown limpo...")
        stop_event.set()
        frontier.notify_all()
    
        shutdown_deadline = time.time() + 10.0
        for t in threads:
            remaining = max(0.1, shutdown_deadline - time.time())
            t.join(timeout=remaining)
    
        alive = sum(1 for t in threads if t.is_alive())
        if alive > 0:
            logger.warning(f"[crawler] {alive} threads ainda ativas apos 10s, forcando shutdown")

    storage.close()
    frontier.close()
    metrics.close()
    elapsed = time.time() - start_time
    saved = storage.total_saved()
    rate = saved / elapsed if elapsed > 0 else 0.0
    logger.info(
        f"[crawler] concluido: {saved} paginas em {elapsed:.1f}s ({rate:.1f} pages/s)",
    )


if __name__ == "__main__":
    main()
