# The benchmark panel — what each measure can and cannot prove

Registry: `indicators/audit_benchmarks.py`. All FRED IDs endpoint-verified
2026-10-03. **Validation-only: none of these may ever be bound as a signal.**

## The independence caveat you must always state

These benchmarks are **independently constructed, not input-independent.**

- CFNAI is built from 85 series that *include* payrolls, industrial production,
  retail sales and capacity utilisation — four members of our own growth basket.
- Median / trimmed / sticky CPI are alternative aggregations of the same BLS price
  quotes behind our CPI signals.

So a high correlation is **partly mechanical and proves little**. What the panel
genuinely tests is our *aggregation, normalisation and threshold* choices. The
informative outputs are therefore **CONTRADICT verdicts, disagreement episodes and
lead/lag** — not the headline correlation number. Say this in every report; a
report that quotes r = 0.78 as proof of validity is misleading.

## Growth

| key | FRED | kind | What it actually tests |
| --- | --- | --- | --- |
| `cfnai_ma3` | CFNAIMA3 | relative | **Primary.** The only external measure that is standardised, mean-zero AND publisher-thresholded (< −0.70 recession onset, > +0.70 above-trend with building inflation pressure). The sharpest available test of our `gz` calibration. |
| `cfnai` | CFNAI | relative | Unsmoothed. Turning-point timing only — too noisy for level reads. |
| `cfnai_diffusion` | CFNAIDIFF | relative | Breadth of the same 85 inputs. The external analogue of our Chip Direction Agreement metric, not of the score. |
| `wei` | WEI | rate | Weekly; claims, retail, steel, fuel, electricity. The **most input-independent** growth measure here. Leads monthly data. |
| `gdpnow` | GDPNOW | rate | Atlanta Fed current-quarter nowcast. LEVEL axis only. |
| `stl_nowcast` | STLENI | rate | Second independent nowcasting model. Cross-check on GDPNow. |
| `real_gdp_growth` | A191RL1Q225SBEA | rate | The realised outcome, revised, published late. Ground truth for "was it growing". |
| `sahm` | SAHMREALTIME | flag | Fires ≥ 0.50. Inverted. Derived from unemployment — overlaps `growth.unemployment`. |
| `recession_prob` | RECPROUSM156N | flag | Chauvet model, percent. Inverted. Read as a call above 50%. |
| `nber_recession` | USREC | flag | **The historical arbiter.** Genuinely independent of our data, but dated retrospectively — useless for the current month, essential for lead/lag scoring in historical mode. |

## Inflation

No external inflation measure is standardised, so all are graded on the level axis
plus a rolling Z of their own history.

| key | FRED | kind | What it actually tests |
| --- | --- | --- | --- |
| `median_cpi` | MEDCPIM158SFRBCLE | rate | Robust central tendency. Monthly annualised, so smoothed 12m to compare with our YoY signals. |
| `trimmed_cpi` | TRMMEANCPIM158SFRBCLE | rate | 16% trimmed mean. Smoothed 12m. |
| `trimmed_pce` | PCETRIM12M159SFRBDAL | rate | Already a 12-month rate. The Fed's own preferred underlying-trend measure. |
| `sticky_core_cpi` | CORESTICKM159SFRBATL | rate | Partitioned by price-change frequency. Proxies **persistence** — what the Disinflation chip is really claiming to detect. Smoothed 12m. |
| `mich_1y` | MICH | expect | Household survey. Genuinely independent data, poor forecaster, heavily level-biased. Weak corroboration only. |

## Rejected candidates — do not re-add without re-verifying

| Candidate | Why rejected |
| --- | --- |
| `USALOLITONOSTSAM` (OECD US CLI) | Dead on FRED — ends 2024-01. Consistent with the other OECD feed deaths documented in `docs/Guidance/data_source_wishlist.md`. |
| `USSLIND` | Dead — ends 2020-02. |
| `ADSBCI` (Philly Fed ADS) | Does not exist on FRED. |
| `EXPINF1YR` (Cleveland Fed 1y expected inflation) | **Circular.** Already ingested as the bound signal `market.exp_infl_1y` in `config/us_bindings.yaml`. Not in the inflation basket, but a series inside our own system cannot be presented as independent corroboration. Caught by the circularity test. |
| Conference Board LEI | Proprietary, not free. |
| 5y/10y breakevens | Already in our inflation basket as `inflation.breakeven_avg`. Circular. |

## How states are assigned

`_benchmark_state()` in `audit_benchmarks.py`:

1. **Publisher thresholds win** where they exist — the entire reason CFNAI-MA3 and
   the recession flags are in the panel.
2. Otherwise **rolling Z vs ±0.5 sigma**, the same yardstick the chip's own default
   `gz`/`iz` use, so both sides of the comparison are graded alike.
3. `orientation = −1` inverts Sahm / recession-probability / NBER, where a high
   reading means *weak* growth.
4. **A regime flag that has not fired reads Neutral, not Above.** A flag carries
   information only when it fires; absence of a recession call is not a growth call.
5. Unavailable or insufficient history → `Unknown`, graded `UNKNOWN`. Never zero.

Verdicts come from a fixed grid in `_verdict()` — no judgement calls, so the tally
is reproducible run to run:

| | Above | Neutral | Below |
| --- | --- | --- | --- |
| Growth / Inflation chip | AGREE | PARTIAL | CONTRADICT |
| Transition chip | PARTIAL | AGREE | PARTIAL |
| Retraction / Disinflation chip | CONTRADICT | PARTIAL | AGREE |

## Lead/lag convention

`best_lag()` scans ±6 months by Spearman. `ours.shift(k)` moves our readings later,
so **positive `best_lag` means our composite LED the benchmark** by that many
months. Leading by 1–2 is a feature. Lagging by 3+ is a finding worth a punch-list
item.

## Disagreement episodes

Runs of ≥ 3 consecutive months where both sides exceed ±0.5 sigma and point
opposite ways. These are where the real information is. Pick the largest one per
axis and either explain it or state plainly that you cannot.
