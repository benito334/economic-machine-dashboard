"""Global Overview — cross-country macro summary table."""
from __future__ import annotations

import os

import duckdb
from dash import html

_DB = os.getenv("DB_PATH", "/mnt/data/db/all_weather/indicators_machine/signals.duckdb")

_COUNTRY_NAMES: dict[str, str] = {
    "us": "United States",
    "ez": "Euro Area",
    "jp": "Japan",
    "gb": "United Kingdom",
    "kr": "South Korea",
    "cn": "China",
    "in": "India",
    "br": "Brazil",
    "sa": "Saudi Arabia",
    "ru": "Russia",
    "ca": "Canada",
    "de": "Germany",
    "fr": "France",
    "it": "Italy",
}

_COUNTRY_ORDER = ["us", "ez", "jp", "gb", "kr", "cn", "in", "br", "sa", "ru"]

# ── Column definitions ──────────────────────────────────────────────────────
# color keys: warn_le, warn_ge → orange   |   high_ge → blue   |   pos_ge, pos_le → green
_COLUMNS: list[dict] = [
    {
        "header": "GDP",
        "sub": "Billion USD",
        "concept": "master.gdp_level_bn",
        "multiplier": 1.0,
        "fmt": lambda v: f"{v:,.0f}",
        "color": {"high_ge": 5_000},
    },
    {
        "header": "GDP Growth",
        "sub": "%",
        "concept": "master.gdp_real",
        "multiplier": 100.0,           # decimal → %
        "fmt": lambda v: f"{v:.2f}",
        "color": {"warn_le": 0.0, "pos_ge": 2.5},
    },
    {
        "header": "Interest Rate",
        "sub": "%",
        "concept": "policy.fed_funds_target",
        "multiplier": 1.0,
        "fmt": lambda v: f"{v:.2f}",
        "color": {"warn_ge": 8.0},
    },
    {
        "header": "Inflation Rate",
        "sub": "%",
        "concept": "inflation.cpi_headline",
        "multiplier": 100.0,           # decimal → %
        "fmt": lambda v: f"{v:.2f}",
        "color": {"warn_ge": 5.0},
    },
    {
        "header": "Jobless Rate",
        "sub": "%",
        "concept": "growth.unemployment",
        "multiplier": 1.0,
        "fmt": lambda v: f"{v:.2f}",
        "color": {"warn_ge": 7.0, "pos_le": 3.0},
    },
    {
        "header": "Gov. Budget",
        "sub": "% GDP",
        "concept": "fiscal.budget_balance_gdp",
        "multiplier": 1.0,
        "fmt": lambda v: f"{v:.2f}",
        "color": {"warn_le": -6.0, "pos_ge": 0.0},
    },
    {
        "header": "Debt/GDP",
        "sub": "%",
        "concept": "credit.gov_debt_gdp",
        "multiplier": 1.0,
        "fmt": lambda v: f"{v:.2f}",
        "color": {"high_ge": 110.0},
    },
    {
        "header": "Current Account",
        "sub": "% GDP",
        "concept": "external.current_account_gdp",
        "multiplier": 1.0,
        "fmt": lambda v: f"{v:.2f}",
        "color": {"warn_le": -4.0, "pos_ge": 4.0},
    },
    {
        "header": "Population",
        "sub": "Million",
        "concept": "demo.population_total_mn",
        "multiplier": 1e-6,            # persons → millions
        "fmt": lambda v: f"{v:.2f}",
        "color": {"high_ge": 1_000.0},
    },
]


# ── Helpers ─────────────────────────────────────────────────────────────────

def _color_class(value: float, spec: dict) -> str:
    """Return a CSS class name based on threshold spec, or empty string."""
    # Check warn first (takes priority over pos if both defined)
    if spec.get("warn_le") is not None and value <= spec["warn_le"]:
        return "ov-cell-warn"
    if spec.get("warn_ge") is not None and value >= spec["warn_ge"]:
        return "ov-cell-warn"
    if spec.get("high_ge") is not None and value >= spec["high_ge"]:
        return "ov-cell-high"
    if spec.get("pos_ge") is not None and value >= spec["pos_ge"]:
        return "ov-cell-pos"
    if spec.get("pos_le") is not None and value <= spec["pos_le"]:
        return "ov-cell-pos"
    return ""


def _load_data() -> dict[str, dict[str, tuple[float, str]]]:
    """Return {country_code: {concept: (display_value, as_of_str)}}."""
    concepts = [c["concept"] for c in _COLUMNS]
    like_clauses = " OR ".join(f"id LIKE '%.{concept}'" for concept in concepts)
    try:
        con = duckdb.connect(_DB, read_only=True)
        rows = con.execute(f"""
            SELECT id, value, as_of
            FROM signals
            WHERE ({like_clauses})
            QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY as_of DESC) = 1
        """).fetchall()
        con.close()
    except Exception:
        return {}

    result: dict[str, dict[str, tuple[float, str]]] = {}
    for (id_, value, as_of) in rows:
        # id format: "{country}.{force}.{concept_tail}" e.g. "us.master.gdp_level_bn"
        parts = id_.split(".", 1)
        if len(parts) < 2:
            continue
        country, concept = parts[0], parts[1]
        result.setdefault(country, {})[concept] = (float(value), str(as_of)[:7])
    return result


def _make_row(country_code: str, country_data: dict[str, tuple[float, str]]) -> html.Tr:
    name = _COUNTRY_NAMES.get(country_code, country_code.upper())
    cells: list = [html.Td(name, className="ov-country-name")]

    for col in _COLUMNS:
        concept = col["concept"]
        if concept not in country_data:
            cells.append(html.Td("—", className="ov-cell-missing"))
            continue
        raw_val, as_of = country_data[concept]
        val = raw_val * col["multiplier"]
        text = col["fmt"](val)
        cls = _color_class(val, col["color"])
        cells.append(html.Td(
            [
                html.Span(text, className=cls or "ov-cell-default"),
                html.Br(),
                html.Span(as_of, className="ov-cell-date"),
            ],
            className="ov-cell-num",
        ))
    return html.Tr(cells, className="ov-row")


# ── Layout ──────────────────────────────────────────────────────────────────

def get_layout() -> html.Div:
    data = _load_data()
    # Show countries in rollout order; append any extras
    country_codes = [c for c in _COUNTRY_ORDER if c in data]
    for c in sorted(data):
        if c not in country_codes:
            country_codes.append(c)

    header = html.Tr([
        html.Th("Country", className="ov-th-country"),
        *[
            html.Th(
                [html.Div(col["header"]), html.Div(col["sub"], className="ov-th-sub")],
                className="ov-th-num",
            )
            for col in _COLUMNS
        ],
    ])

    table = html.Table(
        [html.Thead(header), html.Tbody([_make_row(c, data[c]) for c in country_codes])],
        className="ov-table",
    )

    legend = html.Div([
        html.Span("■ ", style={"color": "#E8853A", "fontSize": "0.9rem"}),
        html.Span("Elevated / Concerning  ", className="ov-legend-label"),
        html.Span("■ ", style={"color": "#4C9BE8", "fontSize": "0.9rem"}),
        html.Span("Notable / High  ", className="ov-legend-label"),
        html.Span("■ ", style={"color": "#5CB85C", "fontSize": "0.9rem"}),
        html.Span("Positive / Favourable", className="ov-legend-label"),
    ], style={"marginTop": "14px", "paddingLeft": "2px"})

    return html.Div([
        html.Div([
            html.H4("Global Overview", style={"marginBottom": "2px", "fontSize": "1.1rem"}),
            html.P(
                "Latest available value per country. Dates below each figure show the most recent observation in the database.",
                style={"color": "var(--muted-color)", "fontSize": "0.74rem", "marginBottom": "16px"},
            ),
        ], className="pt-3"),
        html.Div(table, style={"overflowX": "auto"}),
        legend,
    ], className="pe-2", style={"maxWidth": "1400px", "margin": "0 auto"})
