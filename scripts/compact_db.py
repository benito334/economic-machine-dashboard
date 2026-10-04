"""One-off recovery: rewrite a DuckDB file into a fresh one, dropping dead row-group space.

Not part of normal operation — store.py's upserts update in place and no longer leak
(see _upsert_in_place). Use this only to shrink a file that bloated under the old
DELETE-then-INSERT upserts. Stop every process using the DB first (single-writer).

    python scripts/compact_db.py /path/to/signals.duckdb            # writes .compact, swaps, keeps .bak
    python scripts/compact_db.py /path/to/signals.duckdb --no-swap  # just writes .compact

COPY FROM DATABASE preserves schema, PRIMARY KEYs and types (CREATE TABLE AS would drop
the PKs, which ON CONFLICT upserts depend on).
"""
import argparse
import os
from pathlib import Path

import duckdb


def compact(src: Path, dst: Path) -> None:
    if dst.exists():
        dst.unlink()
    con = duckdb.connect()
    con.execute(f"ATTACH '{dst}' AS new")
    con.execute(f"ATTACH '{src}' AS old (READ_ONLY)")
    con.execute("COPY FROM DATABASE old TO new")
    con.execute("DETACH old")
    con.execute("CHECKPOINT new")
    con.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("db", type=Path)
    ap.add_argument("--no-swap", action="store_true", help="write <db>.compact only; leave the original alone")
    args = ap.parse_args()

    db = args.db.resolve()
    out = db.with_name(db.name + ".compact")
    before = db.stat().st_size
    compact(db, out)
    check = duckdb.connect(str(out), read_only=True)
    pks = check.execute(
        "SELECT COUNT(*) FROM information_schema.table_constraints WHERE constraint_type='PRIMARY KEY'"
    ).fetchone()[0]
    check.close()
    print(f"{db.name}: {before/1e6:,.1f} MB -> {out.stat().st_size/1e6:,.1f} MB  (primary keys kept: {pks})")
    if args.no_swap:
        return
    bak = db.with_name(db.name + ".bak")
    os.replace(db, bak)
    os.replace(out, db)
    print(f"swapped in; original kept at {bak} — delete it once the dashboard looks right")


if __name__ == "__main__":
    main()
