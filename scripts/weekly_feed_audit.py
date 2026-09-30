"""Weekly data-feed health audit.

Reviews the already-ingested DB state (no live API calls): per-country stale-signal
counts from the `signals` table, plus whether the daily auto-import scheduler
(schedule_status.json) is actually running. Appends a dated section to
docs/audits/weekly_feed_audit.md and prints a short summary to stdout.

Usage: python scripts/weekly_feed_audit.py
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb

DB_PATH = Path(os.environ.get("DB_PATH", "/mnt/data/db/finance/indicators_machine/signals.duckdb"))
DATA_DIR = Path(os.environ.get("DATA_DIR", "/mnt/data/project_data/finance/indicators_machine"))
SCHEDULE_STATUS_PATH = DATA_DIR / "schedule_status.json"
REPORT_PATH = Path(__file__).resolve().parent.parent / "docs" / "audits" / "weekly_feed_audit.md"

STALE_PCT_WARN = 0.10   # >=10% of a country's signals stale -> amber
STALE_PCT_ALARM = 0.25  # >=25% -> red
SCHEDULER_STALE_DAYS = 2  # daily import hasn't succeeded in this many days -> red


def audit_countries(conn: duckdb.DuckDBPyConnection) -> list[dict]:
    countries = [r[0] for r in conn.execute("SELECT DISTINCT country FROM signals ORDER BY 1").fetchall()]
    rows = []
    for cc in countries:
        df = conn.execute(
            """
            SELECT id, as_of, is_stale, low_history
            FROM signals
            WHERE (id, as_of) IN (
                SELECT id, MAX(as_of) FROM signals WHERE country = ? GROUP BY id
            ) AND country = ?
            """,
            [cc, cc],
        ).df()
        total = len(df)
        stale = df[df["is_stale"] == True]  # noqa: E712
        n_stale = len(stale)
        pct = (n_stale / total) if total else 0.0
        flag = "OK"
        if pct >= STALE_PCT_ALARM:
            flag = "ALARM"
        elif pct >= STALE_PCT_WARN:
            flag = "WARN"
        rows.append(
            {
                "country": cc,
                "total": total,
                "n_stale": n_stale,
                "pct_stale": pct,
                "flag": flag,
                "stale_ids": sorted(stale["id"].tolist()),
                "oldest_as_of": df["as_of"].min() if total else None,
            }
        )
    return rows


def audit_scheduler() -> dict:
    if not SCHEDULE_STATUS_PATH.exists():
        return {"present": False}
    status = json.loads(SCHEDULE_STATUS_PATH.read_text())
    last_finished = status.get("last_finished")
    days_since = None
    flag = "UNKNOWN"
    if last_finished:
        try:
            dt = datetime.fromisoformat(last_finished)
            days_since = (datetime.now() - dt).total_seconds() / 86400
        except ValueError:
            pass
    if days_since is not None:
        flag = "ALARM" if days_since > SCHEDULER_STALE_DAYS else "OK"
    return {"present": True, "days_since_last_run": days_since, "flag": flag, **status}


def render_report(country_rows: list[dict], sched: dict, run_date: date) -> str:
    lines = [f"## {run_date.isoformat()}", ""]

    if not sched.get("present"):
        lines.append("- **Scheduler:** `schedule_status.json` not found — daily auto-import status unknown.")
    elif sched.get("flag") == "ALARM":
        lines.append(
            f"- **Scheduler: ALARM** — last successful run {sched.get('days_since_last_run'):.1f} days ago "
            f"(last_status={sched.get('last_status')}, enabled={sched.get('enabled')})."
        )
    else:
        lines.append(
            f"- **Scheduler: OK** — last run {sched.get('last_finished')}, status={sched.get('last_status')}."
        )
    lines.append("")

    alarms = [r for r in country_rows if r["flag"] == "ALARM"]
    warns = [r for r in country_rows if r["flag"] == "WARN"]
    ok = [r for r in country_rows if r["flag"] == "OK"]

    lines.append(f"**Countries:** {len(ok)} OK, {len(warns)} WARN, {len(alarms)} ALARM (of {len(country_rows)})")
    lines.append("")
    lines.append("| Country | Total | Stale | % Stale | Flag |")
    lines.append("|---|---|---|---|---|")
    for r in sorted(country_rows, key=lambda x: -x["pct_stale"]):
        lines.append(f"| {r['country']} | {r['total']} | {r['n_stale']} | {r['pct_stale']:.0%} | {r['flag']} |")
    lines.append("")

    for r in alarms + warns:
        if r["stale_ids"]:
            lines.append(f"- **{r['country']}** ({r['flag']}) stale signals: {', '.join(r['stale_ids'])}")
    lines.append("")
    return "\n".join(lines)


def render_summary(country_rows: list[dict], sched: dict) -> str:
    alarms = [r["country"] for r in country_rows if r["flag"] == "ALARM"]
    warns = [r["country"] for r in country_rows if r["flag"] == "WARN"]
    bits = []
    if sched.get("flag") == "ALARM":
        bits.append(f"scheduler stalled ({sched.get('days_since_last_run', 0):.1f}d)")
    if alarms:
        bits.append(f"ALARM: {', '.join(alarms)}")
    if warns:
        bits.append(f"WARN: {', '.join(warns)}")
    if not bits:
        return "All 14 country feeds healthy; daily auto-import running on schedule."
    return "Feed audit found issues -> " + "; ".join(bits)


def main() -> None:
    conn = duckdb.connect(str(DB_PATH), read_only=True)
    country_rows = audit_countries(conn)
    sched = audit_scheduler()
    run_date = date.today()

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    section = render_report(country_rows, sched, run_date)
    existing = REPORT_PATH.read_text() if REPORT_PATH.exists() else "# Weekly Feed Audit Log\n\n"
    REPORT_PATH.write_text(existing.rstrip() + "\n\n" + section + "\n")

    print(render_summary(country_rows, sched))
    print(f"\nFull report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
