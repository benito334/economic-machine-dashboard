# Manual-Load Data (roadmap D4)

Some of the big-cycle ORDER layer's sources publish **no free API** — only
bulk file downloads. Rather than screen-scrape or poll fragile URLs, these
run on a **drop-folder pattern**:

1. You download the raw file from the publisher (links below).
2. You run the matching `scripts/prepare_*.py` converter, which writes
   per-country `date,value` CSVs into the drop folder.
3. The pipeline's **Pass 3.8 (Manual-load series)** ingests whatever CSVs are
   present. A missing file is a **pending `[SLOT]`** — logged, counted
   separately in the run summary, and never treated as a failure.

Drop folder (bind-mounted into the containers like the rest of DATA_DIR):

```
/mnt/data/project_data/all_weather/indicators_machine/manual_data/
```

Override with the `MANUAL_DATA_DIR` env var. A copy of this document lives in
the drop folder as `README.md`.

## File format

One CSV per signal, exactly two columns:

```csv
date,value
1990,0.796      # bare years allowed (annual sources) — parsed as year-end
2024-03-01,1.42 # or ISO dates (monthly sources)
```

The binding (provider `Manual`) names its CSV in `series_id`. A file that is
present but malformed **fails loudly** — only absence is tolerated.

## Sources

### V-Dem — `order.governance` (annual, 0–1)

- **What:** Liberal Democracy Index (`v2x_libdem`) — Ray's internal-order
  read: institutional erosion precedes internal conflict.
- **Download:** https://v-dem.net/data/the-v-dem-dataset/ → "V-Dem-CY-Core"
  (Country-Year core, ~30 MB zipped CSV, free, updated every March).
- **Convert:** `python scripts/prepare_vdem.py /path/to/V-Dem-CY-Core-vXX.csv`
- **Produces:** `vdem_{us,cn,in,de,gb,jp,kr,lu}.csv` (no EZ aggregate exists).

### GPR — `order.geopolitical_risk` (monthly index)

- **What:** Caldara–Iacoviello country Geopolitical Risk indices
  (`GPRC_{ISO3}` — share of newspaper articles, monthly since 1985) — Ray's
  external-conflict read.
- **Download:** https://www.matteoiacoviello.com/gpr_files/data_gpr_export.xls
  (~2 MB, free, updated monthly). Reading the legacy `.xls` needs `xlrd`.
- **Convert:** `python scripts/prepare_gpr.py /path/to/data_gpr_export.xls`
- **Produces:** `gpr_{us,cn,in,de,gb,jp,kr}.csv` — **Luxembourg is not in the
  GPR country set** (no binding, honest gap).

### EM-DAT — `climate.disaster_loss` (slot only, not yet bound)

The `climate.disaster_loss` deferred slot in `us_bindings.yaml` predates this
infrastructure and stays `verified: false`. When EM-DAT access is sorted
(registration required), convert to the same pattern: set
`provider: Manual`, name a CSV, flip `verified: true`.

## Freshness expectations

These are **slow structural reads** (`lead_lag: structural`, feed no
composite). V-Dem updates annually (March); GPR monthly. The signals will
show `is_stale` by the normal staleness rules if the drops aren't refreshed —
that is working as intended, not a bug. Re-run the converter + pipeline
whenever you refresh a download.
