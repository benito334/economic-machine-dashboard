"""Convert the Caldara–Iacoviello GPR export into per-country manual-load CSVs.

D4 manual-load converter (see manual_data/README.md). The Geopolitical Risk
index is published as a spreadsheet with no API — download
https://www.matteoiacoviello.com/gpr_files/data_gpr_export.xls (~2 MB,
updated monthly) and run:

    python scripts/prepare_gpr.py /path/to/data_gpr_export.xls

Writes gpr_{cc}.csv (columns: date,value) into MANUAL_DATA_DIR for every
country that has an order.geopolitical_risk binding, using the country-
specific GPRC_{ISO3} columns (share of newspaper articles mentioning
geopolitical risk for that country, monthly since 1985). Luxembourg is not
in the GPR country set — no file is produced for it by design.

Re-run after downloading a fresh export, then re-run the pipeline.
Requires xlrd (legacy .xls): pip install xlrd
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1]))
from indicators.loader import MANUAL_DATA_DIR  # noqa: E402

# Internal code → GPR column. LU/EZ have no GPR series.
COUNTRIES = {
    "us": "GPRC_USA", "cn": "GPRC_CHN", "in": "GPRC_IND", "de": "GPRC_DEU",
    "gb": "GPRC_GBR", "jp": "GPRC_JPN", "kr": "GPRC_KOR",
}


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(f"Usage: python {sys.argv[0]} /path/to/data_gpr_export.xls")
    src = Path(sys.argv[1])
    if not src.exists():
        sys.exit(f"Not found: {src}")

    print(f"Reading {src}…")
    df = pd.read_excel(src)  # engine auto-detected (.xls needs xlrd)
    date_col = next((c for c in df.columns if str(c).lower() in ("month", "date")), None)
    if date_col is None:
        sys.exit(f"No month/date column found — columns: {list(df.columns)[:10]}…")
    dates = pd.to_datetime(df[date_col])

    MANUAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for cc, col in COUNTRIES.items():
        if col not in df.columns:
            print(f"  ✘ {col}: column not in export — check the file version")
            continue
        sub = pd.DataFrame({"date": dates.dt.strftime("%Y-%m-%d"),
                            "value": pd.to_numeric(df[col], errors="coerce")}).dropna()
        if sub.empty:
            print(f"  ✘ {col}: no usable rows")
            continue
        out = MANUAL_DATA_DIR / f"gpr_{cc}.csv"
        sub.to_csv(out, index=False)
        print(f"  ✔ {out.name}: {len(sub)} rows {sub['date'].iloc[0]}→{sub['date'].iloc[-1]} "
              f"(last {col}={sub['value'].iloc[-1]:.2f})")

    print("\nDone. Re-run the pipeline to ingest (Pass 3.8).")


if __name__ == "__main__":
    main()
