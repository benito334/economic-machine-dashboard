#!/usr/bin/env python3
"""Build the public-deploy data bundle for Hugging Face Spaces.

Compacts the working DuckDB (which bloats to multiple GB from in-place updates)
down to a fresh, minimal file, then tars it together with the read-cache and
snapshots into ``emd_data.tar.gz``. Upload that one file to the Space (see
``deploy/hf/DEPLOY.md``) to publish fresh data.

Usage:
    python scripts/build_public_bundle.py [--out PATH]

Reads the same env vars the app uses (DB_PATH / DATA_DIR / RAW_CACHE_DIR /
SNAPSHOTS_DIR), falling back to the locked-in project paths.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from store.store import compact_database  # noqa: E402

_DEF_DB = "/mnt/data/db/finance/indicators_machine/signals.duckdb"
_DEF_DATA = "/mnt/data/project_data/finance/indicators_machine"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="emd_data.tar.gz",
                    help="output tarball path (default: ./emd_data.tar.gz)")
    args = ap.parse_args()

    db_path = Path(os.environ.get("DB_PATH", _DEF_DB))
    data_dir = Path(os.environ.get("DATA_DIR", _DEF_DATA))
    raw_cache = Path(os.environ.get("RAW_CACHE_DIR", data_dir / "raw_cache"))
    snapshots = Path(os.environ.get("SNAPSHOTS_DIR", data_dir / "snapshots"))
    out = Path(args.out).resolve()

    if not db_path.exists():
        raise SystemExit(f"database not found: {db_path}")

    src_mb = db_path.stat().st_size / 1e6
    print(f"source DB: {db_path}  ({src_mb:,.0f} MB)")

    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        compact = stage / "signals.duckdb"
        print("compacting…")
        compact_database(db_path, dest=compact)
        print(f"compacted DB: {compact.stat().st_size / 1e6:,.1f} MB")

        # raw_cache (drill-down / yield-curve parquet + FRED meta) and snapshots
        if raw_cache.exists():
            shutil.copytree(raw_cache, stage / "raw_cache")
        (stage / "snapshots").mkdir(exist_ok=True)
        if snapshots.exists():
            for p in snapshots.iterdir():
                if p.is_file():
                    shutil.copy2(p, stage / "snapshots" / p.name)

        print(f"writing {out} …")
        with tarfile.open(out, "w:gz") as tar:
            for name in ("signals.duckdb", "raw_cache", "snapshots"):
                p = stage / name
                if p.exists():
                    tar.add(p, arcname=name)

    print(f"done: {out}  ({out.stat().st_size / 1e6:,.1f} MB)")
    print("Upload this file to your Hugging Face Space (see deploy/hf/DEPLOY.md).")


if __name__ == "__main__":
    main()
