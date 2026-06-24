"""
Theme definitions for the Dash charting app.

Three themes: Carbon (default dark), Slate (cool dark), Dawn (light).
Each theme is a dict of Plotly figure properties + CSS var values.
"""
from __future__ import annotations

THEMES: dict[str, dict] = {
    "carbon": {
        "name": "Carbon",
        # Plotly figure props
        "paper_bgcolor": "#1c1c1c",
        "plot_bgcolor": "#191919",
        "font_color": "#e8e8e8",
        "grid_color": "#2d2d2d",
        # CSS custom property values
        "page_bg": "#1c1c1c",
        "card_bg": "#262626",
        "border_color": "#3a3a3a",
        "muted_color": "#888888",
        "header_bg": "#141414",
        "cell_bg": "#1c1c1c",
        # Sidebar series-selector label color — softer than the main font
        "series_label_color": "#aaaaaa",
    },
    "slate": {
        "name": "Slate",
        "paper_bgcolor": "#22272e",
        "plot_bgcolor": "#1c2128",
        "font_color": "#cdd9e5",
        "grid_color": "#373e47",
        "page_bg": "#22272e",
        "card_bg": "#2d333b",
        "border_color": "#444c56",
        "muted_color": "#768390",
        "header_bg": "#161b22",
        "cell_bg": "#22272e",
        "series_label_color": "#96afc4",
    },
    "dawn": {
        "name": "Dawn",
        "paper_bgcolor": "#f0f2f5",
        "plot_bgcolor": "#ffffff",
        "font_color": "#212529",
        "grid_color": "#dee2e6",
        "page_bg": "#f0f2f5",
        "card_bg": "#ffffff",
        "border_color": "#ced4da",
        "muted_color": "#6c757d",
        "header_bg": "#e9ecef",
        "cell_bg": "#ffffff",
        "series_label_color": "#495057",
    },
}

DEFAULT_THEME = "carbon"


def _build_css_vars() -> dict[str, dict]:
    """Build per-theme dicts of CSS custom property name → value for clientside use."""
    _slider_accent = {
        "carbon": "#E8A317",   # warm amber — readable on dark charcoal
        "slate":  "#F4C842",   # brighter gold — pops on slate blue-grey
        "dawn":   "#4C6EF5",   # indigo — visible on light background
    }
    result: dict[str, dict] = {}
    for key, t in THEMES.items():
        result[key] = {
            "--page-bg": t["page_bg"],
            "--card-bg": t["card_bg"],
            "--font-color": t["font_color"],
            "--border-color": t["border_color"],
            "--muted-color": t["muted_color"],
            "--header-bg": t["header_bg"],
            "--cell-bg": t["cell_bg"],
            "--grid-color": t["grid_color"],
            "--series-label-color": t["series_label_color"],
            "--slider-accent": _slider_accent.get(key, "#E8A317"),
            # Bootstrap 5 CSS vars (used by dbc components)
            "--bs-body-bg": t["page_bg"],
            "--bs-body-color": t["font_color"],
            "--bs-card-bg": t["card_bg"],
            "--bs-border-color": t["border_color"],
            "--bs-secondary-bg": t["card_bg"],
            "--bs-tertiary-bg": t["header_bg"],
        }
    return result


THEME_CSS_VARS: dict[str, dict] = _build_css_vars()


def figure_layout(theme_name: str, title: str = "") -> dict:
    """Return a Plotly layout dict for the given theme name."""
    t = THEMES.get(theme_name, THEMES[DEFAULT_THEME])
    return {
        "paper_bgcolor": t["paper_bgcolor"],
        "plot_bgcolor": t["plot_bgcolor"],
        "font": {"color": t["font_color"], "size": 12},
        "xaxis": {"gridcolor": t["grid_color"], "showgrid": True},
        "yaxis": {"gridcolor": t["grid_color"], "showgrid": True},
        "margin": {"l": 55, "r": 20, "t": 40, "b": 30},
        "title": {"text": title, "font": {"size": 13}, "x": 0.5} if title else {},
    }
