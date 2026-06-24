### Quick‑Answer  
| Series | Typical “force” (mean‑re‑centering) Z‑score | Typical “momentum” (change‑based) Z‑score |
|--------|-------------------------------------------|------------------------------------------|
| **Monthly** | 36 – 60 months (3 – 5 years) | 6 – 12 months |
| **Quarterly** | 8 – 12 quarters (2 – 3 years) | 2 – 4 quarters |
| **Daily / Intraday** | 252 – 504 days (1 – 2 years) | 20 – 60 days |

These ranges are a starting point; you’ll want to fine‑tune them for each indicator after you test how the choice affects signal stability and predictive power.

---

## Why the Two Numbers Differ  

| Concept | Force Z‑score | Momentum Z‑score |
|---------|---------------|-----------------|
| **What it measures** | How far an observation is from its *long‑run* average (captures “regime‑level” bias). | How fast the series is moving *relative to recent history* (captures short‑term turning points). |
| **Sensitivity to outliers** | Low – a long window smooths extreme spikes. | High – a short window magnifies recent swings. |
| **Lag vs. responsiveness** | More lag (good for identifying persistent regimes). | Less lag (good for spotting early shifts). |

Because they serve different purposes, you usually keep the two windows separate rather than forcing a single look‑back length for both.

---

## Practical Steps to Choose the Right Horizon  

1. **Start with a rule‑of‑thumb**  
   - For a *force* score, pick a window that covers at least **three full business cycles** (≈ 3 years for monthly data).  
   - For a *momentum* score, pick a window that captures **one full cycle’s worth of swing** (≈ 6 months for monthly data).

2. **Check the data’s stability**  
   - If the indicator is highly seasonal (e.g., payrolls), strip seasonality first, then apply the Z‑score.  
   - If the series has frequent structural breaks (e.g., policy changes), shorten the force window slightly (e.g., 36 → 30 months) and add a “break‑adjustment” filter.

3. **Run a sensitivity grid**  
   ```
   force_window = [24, 36, 48, 60] months
   momentum_window = [3, 6, 9, 12] months
   ```
   Back‑test each combination on a hold‑out sample and compare:
   - Signal‑to‑noise ratio (average absolute Z‑score / standard deviation)
   - Predictive power (correlation of Z‑score sign with next‑month returns)
   - Stability of regime classification (how often the same regime persists across adjacent periods)

4. **Apply a decay or weighting scheme**  
   - Even within the chosen window, give the most recent observations a higher weight (exponential weighting with half‑life ≈ half the window length). This keeps the Z‑score “fresh” without completely abandoning the long‑run perspective.

5. **Monitor confidence**  
   - When the rolling‑window mean and SD become unstable (e.g., variance jumps > 50 % from the previous quarter), temporarily increase the window length or switch to a robust estimator (median‑based Z‑score).

---

## Example Implementation (Python‑style pseudocode)

```python
import pandas as pd
import numpy as np

def z_score_force(series, window=48):
    """Mean‑centered Z‑score over a long rolling window."""
    roll_mean = series.rolling(window, min_periods=window//2).mean()
    roll_std  = series.rolling(window, min_periods=window//2).std()
    return (series - roll_mean) / roll_std

def z_score_momentum(series, window=12, alpha=0.5):
    """Momentum Z‑score on the change series, with optional exponential weighting."""
    # First compute the change (e.g., log‑return or percent change)
    change = series.diff()
    # Exponential weights (half‑life = window/2)
    weights = np.exp(-np.arange(window)[::-1] / (window/2))
    weights /= weights.sum()
    # Rolling weighted mean & std
    def ewma_z(x):
        m = np.dot(weights, x[-window:])
        s = np.sqrt(np.dot(weights, (x[-window:] - m)**2))
        return (x[-1] - m) / s
    return change.rolling(window).apply(ewma_z, raw=True)
```

Adjust `window` for each indicator based on the steps above, then feed the resulting Z‑scores into your “force‑and‑momentum” composite.

---

## Bottom Line  

- **Force Z‑scores:** Use a **longer look‑back** (3‑5 years for monthly data) to anchor the signal to the underlying regime.  
- **Momentum Z‑scores:** Use a **shorter look‑back** (6‑12 months for monthly data) to capture the recent acceleration or deceleration.  
- **Validate** the chosen horizons with back‑testing, confidence checks, and robustness to structural breaks.  
- **Blend** the two scales (e.g., a weighted average of the two Z‑scores) only after you’re comfortable that each component is behaving as intended.

By following this systematic approach you’ll avoid over‑reacting to the brief “boom‑or‑bust” months you observed in early‑2025 while still preserving the ability to capture genuine regime shifts when they persist beyond a couple of months.