"""Convert the V-Dem Country-Year dataset into per-country manual-load CSVs.

D4 manual-load converter (see manual_data/README.md). V-Dem publishes a free
bulk CSV with no API — download "V-Dem-CY-Core" (Country-Year, ~30 MB zipped)
from https://v-dem.net/data/the-v-dem-dataset/ and run:

    python scripts/prepare_vdem.py /path/to/V-Dem-CY-Core-v15.csv

Writes vdem_{cc}.csv (columns: date,value) into MANUAL_DATA_DIR for every
country that has an order.governance binding. Measure: v2x_libdem (Liberal
Democracy Index, 0–1) — chosen as the single headline governance read; the
full dataset carries hundreds of alternatives if that choice is ever revisited.

Re-run after each annual V-Dem release, then re-run the pipeline.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1]))
from indicators.loader import MANUAL_DATA_DIR  # noqa: E402

MEASURE = "v2x_libdem"

# Internal code → V-Dem country_text_id (ISO3). EZ has no V-Dem aggregate.
COUNTRIES = {
    "us": "USA", "cn": "CHN", "in": "IND", "de": "DEU",
    "gb": "GBR", "jp": "JPN", "kr": "KOR", "lu": "LUX",
}

# V-Dem pre-1900 readings exist but predate every other series in the system;
# 1900 keeps the expanding Z-scores comparable without dropping real signal.
START_YEAR = 1900


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(f"Usage: python {sys.argv[0]} /path/to/V-Dem-CY-Core-vXX.csv")
    src = Path(sys.argv[1])
    if not src.exists():
        sys.exit(f"Not found: {src}")

    print(f"Reading {src} (only the 3 needed columns)…")
    df = pd.read_csv(src, usecols=["country_text_id", "year", MEASURE], low_memory=False)
    df = df[df["year"] >= START_YEAR]

    MANUAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for cc, iso3 in COUNTRIES.items():
        sub = (
            df[df["country_text_id"] == iso3][["year", MEASURE]]
            .dropna()
            .sort_values("year")
            .rename(columns={"year": "date", MEASURE: "value"})
        )
        if sub.empty:
            print(f"  ✘ {iso3}: no rows — check the dataset variant")
            continue
        out = MANUAL_DATA_DIR / f"vdem_{cc}.csv"
        sub.to_csv(out, index=False)
        print(f"  ✔ {out.name}: {len(sub)} rows "
              f"{int(sub['date'].iloc[0])}→{int(sub['date'].iloc[-1])} "
              f"(last {MEASURE}={sub['value'].iloc[-1]:.3f})")

    print("\nDone. Re-run the pipeline to ingest (Pass 3.8).")


if __name__ == "__main__":
    main()
