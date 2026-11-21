"""Measure vault operations on a synthetic dataset.

Usage (Windows or Linux)::

    python tools/bench_vault.py --records 1000
    python tools/bench_vault.py --records 10000 --fast-kdf

The script writes only to a temporary directory and never touches a real vault.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import config  # noqa: E402
from app.database.database import Database  # noqa: E402
from app.security.key_manager import KeyManager  # noqa: E402
from app.services.password_service import PasswordService  # noqa: E402

WORDS = (
    "alpha bravo charlie delta echo foxtrot golf hotel india juliet "
    "kilo lima mike november oscar papa quebec romeo sierra tango"
).split()


def timed(function, repeat: int = 5) -> float:
    samples: list[float] = []
    for _ in range(repeat):
        started = time.perf_counter()
        function()
        samples.append((time.perf_counter() - started) * 1000)
    return statistics.median(samples)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, default=1000)
    parser.add_argument(
        "--fast-kdf",
        action="store_true",
        help="use cheap Argon2id parameters (not representative for unlock timing)",
    )
    args = parser.parse_args()
    if args.records < 1:
        parser.error("--records must be at least 1")

    if args.fast_kdf:
        config.ARGON2_MEMORY_KIB = 8 * 1024
        config.ARGON2_TIME_COST = 1
        config.ARGON2_PARALLELISM = 2

    with tempfile.TemporaryDirectory() as directory:
        os.environ["PM_DATA_DIR"] = directory
        path = Path(directory) / "bench-vault.db"

        started = time.perf_counter()
        database = Database(path)
        keys = KeyManager(database)
        keys.create_vault("Benchmark-Master-Password!42")
        create_ms = (time.perf_counter() - started) * 1000

        service = PasswordService(database, keys)
        started = time.perf_counter()
        service.load()
        load_ms = (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        for index in range(args.records):
            service.create_record(
                title=f"{WORDS[index % len(WORDS)].title()} {index}",
                username=f"user{index}",
                password="Benchmark-Secret!42",
                url=f"https://service{index}.example",
                category_id="other",
            )
        insert_ms = (time.perf_counter() - started) * 1000

        search_ms = timed(lambda: service.list_records(search="user777"))
        stats_ms = timed(service.stats)
        list_ms = timed(service.list_records)

        print(f"records:          {args.records}")
        print(f"vault create:     {create_ms:8.1f} ms")
        print(f"load:             {load_ms:8.1f} ms")
        print(f"insert all:       {insert_ms:8.1f} ms ({insert_ms / args.records:.2f} ms/record)")
        print(f"search (median):  {search_ms:8.1f} ms")
        print(f"stats (median):   {stats_ms:8.1f} ms")
        print(f"list all (median): {list_ms:8.1f} ms")
        keys.close()


if __name__ == "__main__":
    main()
