# Manual-Load Data (roadmap D4) — Operator Runbook

Two big-cycle ORDER-layer sources publish **no free API**, only bulk file
downloads: the **V-Dem** governance dataset and the **GPR** geopolitical-risk
index. They run on a **drop-folder pattern** — you download the file, run a
converter, re-run the pipeline. This document is the step-by-step; nothing
here is automated because the downloads are behind a click, not a URL a script
can reliably fetch.

Until you do this, the pipeline reports these as pending `[SLOT]`s (never an
error) and the Command Center big-cycle card says "governance/GPR pending
manual load". Doing it is **~15 minutes** and needs **no code changes**.

---

## TL;DR — the whole procedure

```bash
# 0. one-time: the GPR file is a legacy .xls, so install the reader
pip install xlrd

# 1. download the two files by hand (see "Where to click" below), then:
python scripts/prepare_vdem.py ~/Downloads/V-Dem-CY-Core-v15.csv
python scripts/prepare_gpr.py  ~/Downloads/data_gpr_export.xls

# 2. re-run the pipeline (stop charting first — single-writer DB lock)
docker compose stop charting
python -m indicators.pipeline
docker compose up -d charting
```

That's it. The converters write per-country CSVs into the drop folder; Pass 3.8
ingests them on the next run; the Command Center card fills in automatically.

Drop folder (bind-mounted into the containers like the rest of `DATA_DIR`):

```
/mnt/data/project_data/all_weather/indicators_machine/manual_data/
```

Override with the `MANUAL_DATA_DIR` env var. A copy of this file lives in that
folder as `README.md`.

---

## Step 1 — Download V-Dem (governance)

1. Go to **https://v-dem.net/data/the-v-dem-dataset/**.
2. Download the **"Country-Year: V-Dem Core"** dataset in **CSV** format
   (there are also Country-Date and full versions — you want **Country-Year
   Core**). It's a free download; some years it asks for a name/email first.
   The file is ~30 MB zipped and unzips to a CSV named like
   `V-Dem-CY-Core-v15.csv` (the version number changes each March release).
3. Unzip it. Note the path to the `.csv`.

Run the converter (point it at wherever you saved the CSV):

```bash
python scripts/prepare_vdem.py ~/Downloads/V-Dem-CY-Core-v15.csv
```

Expected output — one line per country, e.g.:

```
  ✔ vdem_us.csv: 125 rows 1900→2024 (last v2x_libdem=0.792)
  ✔ vdem_de.csv: 125 rows 1900→2024 (last v2x_libdem=0.861)
  ... (8 countries: us cn in de gb jp kr lu)
```

The measure pulled is **`v2x_libdem`** (Liberal Democracy Index, 0–1). There is
no EZ aggregate in V-Dem, so the euro-area code gets no file (by design).

## Step 2 — Download GPR (geopolitical risk)

1. Go to **https://www.matteoiacoviello.com/gpr.htm** (Caldara–Iacoviello's
   page). The direct file link is
   **https://www.matteoiacoviello.com/gpr_files/data_gpr_export.xls**
   — clicking it downloads the spreadsheet (~2 MB, updated monthly).
2. Note the path to `data_gpr_export.xls`.

Run the converter:

```bash
python scripts/prepare_gpr.py ~/Downloads/data_gpr_export.xls
```

Expected output:

```
  ✔ gpr_us.csv: 490 rows 1985-01-01→2025-10-01 (last GPRC_USA=1.42)
  ... (7 countries: us cn in de gb jp kr)
```

The columns pulled are the country-specific **`GPRC_{ISO3}`** series.
**Luxembourg is not in the GPR country set**, so it gets no GPR file and no
binding — that is an honest gap, not a bug.

> If Step 2 errors with `Missing optional dependency 'xlrd'`, run
> `pip install xlrd` (the file is the legacy `.xls` format, which pandas needs
> `xlrd` to read) and retry.

## Step 3 — Re-run the pipeline

The pipeline is the single DB writer, so stop the charting container first (it
holds read connections), then run and bring it back:

```bash
docker compose stop charting
python -m indicators.pipeline        # Pass 3.8 now shows [OK] instead of [SLOT]
docker compose up -d charting
```

In the run log, the `Manual-load series` section for each country flips from
`[SLOT ] order.governance  ... pending` to `[OK ] order.governance ... (N rows)`,
and the per-country summary's "Pending slots: 2" drops to 0 (1→0 for LU).

---

## Verifying it worked

- **Pipeline log:** the summary line for each country should read
  `Pending slots: 0` (or omit the phrase entirely).
- **Command Center** (`/country`): the "Big-cycle position" card should now show
  `V-Dem 0.79 · GPR 1.4` instead of "... pending manual load".
- **Quick DB check:**
  ```bash
  python -c "import duckdb; from store.store import DB_PATH; \
  print(duckdb.connect(str(DB_PATH), read_only=True).execute( \
  \"SELECT id, as_of, value FROM signals WHERE id LIKE '%order.governance%' \
  OR id LIKE '%order.geopolitical_risk%' ORDER BY id\").fetchall())"
  ```

## Refreshing later

These are **slow structural reads** (`lead_lag: structural`; they feed no
composite). V-Dem releases once a year (March); GPR updates monthly. When a
signal goes `is_stale` because the drop is old, that's the normal staleness
rule working — not a bug. To refresh: re-download, re-run the same two
converter commands, re-run the pipeline. Old rows are upserted, not
duplicated.

## File format (reference)

Each converter writes one CSV per signal with exactly two columns; the binding
(`provider: Manual`) names its file in `series_id`:

```csv
date,value
1990,0.796      # bare years (annual sources) → parsed as year-end
2024-03-01,1.42 # or ISO dates (monthly sources)
```

A file that is **present but malformed fails loudly** (missing columns, all-null
values); only a **missing** file is tolerated (as a pending slot). If you ever
hand-edit a drop file, keep the `date,value` header exactly.

## Not yet wired: EM-DAT (`climate.disaster_loss`)

The `climate.disaster_loss` slot in `us_bindings.yaml` predates this
infrastructure and stays `verified: false`. EM-DAT (disaster losses) needs a
free registration to download. When you want it, the pattern is identical:
write a `scripts/prepare_emdat.py`, set the binding to `provider: Manual` with
a CSV name, and flip `verified: true`.
