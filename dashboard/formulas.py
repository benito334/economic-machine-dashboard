"""Code-backed formula reference page for the Dash dashboard."""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from indicators.composites import build_formula_catalog


def _formula_card(spec: dict[str, object]) -> dbc.Card:
    parameters = spec.get("parameters", [])
    return dbc.Card(
        dbc.CardBody([
            html.Div(str(spec["group"]).upper(), style={
                "fontSize": "0.64rem", "letterSpacing": "0.1em",
                "fontWeight": "700", "color": "var(--muted-color)",
            }),
            html.H4(str(spec["title"]), style={"fontSize": "1.05rem", "marginTop": "4px"}),
            dcc.Markdown(
                f"$${spec['equation']}$$", mathjax=True,
                style={"fontSize": "1.02rem", "overflowX": "auto", "padding": "8px 0"},
            ),
            html.P(str(spec["description"]), style={
                "fontSize": "0.82rem", "color": "var(--font-color)", "marginBottom": "8px",
            }),
            html.Ul(
                [html.Li(str(item)) for item in parameters],
                style={"fontSize": "0.76rem", "color": "var(--muted-color)", "paddingLeft": "20px"},
            ),
            html.Code(str(spec["source"]), style={
                "fontSize": "0.68rem", "color": "var(--muted-color)",
                "overflowWrap": "anywhere",
            }),
        ]),
        style={"height": "100%", "backgroundColor": "var(--card-bg)", "borderColor": "var(--border-color)"},
    )


def get_layout() -> html.Div:
    """Build the page from the live formula catalog and active config values."""
    formulas = build_formula_catalog()
    return html.Div([
        html.Div([
            html.H2("Formula Reference", style={"fontSize": "1.35rem", "marginBottom": "4px"}),
            html.P(
                "These equations and parameter values are generated from the calculation code and active composites configuration.",
                style={"color": "var(--muted-color)", "fontSize": "0.82rem"},
            ),
        ], className="pt-3 pb-1"),
        dbc.Row(
            [dbc.Col(_formula_card(spec), md=6, className="mb-3") for spec in formulas],
            className="g-3",
        ),
    ], className="pe-2", style={"maxWidth": "1400px", "margin": "0 auto"})
