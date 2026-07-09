---
title: Economic Machine Dashboard
emoji: 🌍
colorFrom: indigo
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Read 14 economies the Ray Dalio way — the three clocks, live.
---

# Economic Machine Dashboard

A diagnostic, cross-country macro-regime dashboard in the Ray Dalio "Economic
Machine" tradition. It reads 14 major economies on three clocks — the
short-term growth/inflation regime, the long-term debt cycle, and the
big-cycle order — from free public data (FRED, World Bank, IMF, BIS).

**This is a diagnostic, not financial advice.** It tells you *where economies
are in their cycles*, not what to buy.

This Space runs the dashboard in **public read-only mode**: every operator
control that writes shared state (the data scheduler, weight calibration,
saved chart views) is hidden. Each visitor still gets their own theme,
country selection, and view settings (stored in their own browser).

Source code: https://github.com/benito334/economic-machine-dashboard
