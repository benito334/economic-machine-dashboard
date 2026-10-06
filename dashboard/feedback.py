"""Feedback dialog — posts straight from the browser to a Google Apps Script
web app, which appends a row to a Google Sheet.

Why it bypasses the server entirely: a feedback form is a WRITE SURFACE on a
public site, which is exactly what PUBLIC_MODE exists to eliminate (see
tests/test_public_mode_gating.py). Routing it through the dashboard would
reintroduce the thing we just spent a session removing. So the VM stores
nothing: the browser POSTs directly to Apps Script and the data lands in a
Sheet the operator owns.

Collected: the message, an optional email, and context the user would
otherwise have to describe by hand (page, country, look-back windows, theme,
viewport, app version, user agent). Deliberately NOT collected: IP address and
geolocation — an explicit decision, consistent with dashboard/traffic.py's
"no IP or geolocation is ever recorded".

The endpoint and token come from the environment (FEEDBACK_ENDPOINT /
FEEDBACK_TOKEN). Both are visible to anyone who views source — unavoidable for
a browser-side POST, and the reason the token is described as abuse friction
rather than access control. Receiver + deployment notes: deploy/feedback/.
"""
from __future__ import annotations

import os
import subprocess

import dash_bootstrap_components as dbc
from dash import dcc, html

ENDPOINT = os.environ.get("FEEDBACK_ENDPOINT", "").strip()
TOKEN = os.environ.get("FEEDBACK_TOKEN", "").strip()

# Mirrors MAX_MESSAGE in deploy/feedback/Code.gs. Enforced both sides: here so
# the user sees the limit, there because a browser control proves nothing.
MAX_MESSAGE = 4000


def _app_version() -> str:
    """Short git SHA, so a report can be tied to the exact deployed code.

    Resolved once at import. Falls back to the APP_VERSION env var, because the
    Docker image does not always carry a .git directory — without that fallback
    this silently reported an empty string, which is how the column shipped
    blank on the first end-to-end test.
    """
    env = os.environ.get("APP_VERSION", "").strip()
    if env:
        return env[:40]
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5,
                             cwd=os.path.dirname(os.path.dirname(__file__)))
        if out.returncode == 0:
            return out.stdout.strip()[:40]
    except Exception:
        pass
    return ""


APP_VERSION = _app_version()


def enabled() -> bool:
    """Feedback is only offered when an endpoint is actually configured.

    A button that silently discards what someone typed is worse than no button,
    so with no FEEDBACK_ENDPOINT the control is not rendered at all.
    """
    return bool(ENDPOINT and TOKEN)


def nav_button() -> "html.Div | None":
    """Sidebar entry. Styled to match the Settings button above it."""
    if not enabled():
        return None
    return html.Div(
        dbc.Button(
            [html.Span("💬", className="nav-icon",
                       style={"minWidth": "22px", "display": "inline-block",
                              "textAlign": "center", "fontSize": "1.1em"}),
             html.Span(" Feedback", className="sidebar-text")],
            id="feedback-btn",
            color="link",
            size="sm",
            className="sidebar-nav-link",
            style={"color": "var(--muted-color)", "fontSize": "0.875rem",
                   "padding": "4px 12px", "width": "100%", "textAlign": "left",
                   "display": "flex", "alignItems": "center"},
        ),
    )


_LABEL = {"fontWeight": "700", "fontSize": "0.82rem", "color": "var(--font-color)",
          "marginBottom": "4px"}
_HINT = {"fontSize": "0.72rem", "color": "var(--muted-color)", "marginTop": "4px"}


def modal() -> dbc.Modal:
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Send feedback", style={"fontSize": "1rem"})),
        dbc.ModalBody([
            html.P(
                "Found something wrong, confusing, or missing? This goes straight "
                "to the maintainer.",
                style={"fontSize": "0.8rem", "color": "var(--muted-color)",
                       "marginBottom": "14px"},
            ),

            html.Label("What's on your mind?", style=_LABEL),
            dbc.Textarea(
                id="feedback-message",
                placeholder="A bug, a confusing chart, a signal you think is wrong…",
                maxLength=MAX_MESSAGE,
                style={"minHeight": "130px", "fontSize": "0.85rem"},
            ),

            html.Label("Email (optional)", style={**_LABEL, "marginTop": "14px"}),
            dbc.Input(
                id="feedback-email",
                type="email",
                placeholder="only if you'd like a reply",
                style={"fontSize": "0.85rem"},
            ),
            html.Div(
                "Leave it blank to stay anonymous — the message still gets through.",
                style=_HINT,
            ),

            html.Details([
                html.Summary(
                    "What gets sent with this",
                    style={"fontSize": "0.74rem", "color": "var(--muted-color)",
                           "cursor": "pointer", "marginTop": "16px"},
                ),
                html.Div(
                    "The page you're on, the selected country, your look-back window "
                    "settings, theme, screen size, app version and browser "
                    "identification — so a report can be reproduced without a "
                    "back-and-forth. No IP address and no location are collected.",
                    style={**_HINT, "marginTop": "6px", "lineHeight": "1.5"},
                ),
            ]),

            html.Div(id="feedback-status", style={"marginTop": "12px",
                                                  "fontSize": "0.8rem",
                                                  "minHeight": "20px"}),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="feedback-cancel", color="secondary",
                       size="sm", outline=True),
            dbc.Button("Send", id="feedback-send", color="warning", size="sm"),
        ]),
    ], id="feedback-modal", is_open=False, size="md")


def stores() -> list:
    """Config handed to the clientside callback.

    Kept in a Store rather than baked into the JS string so the endpoint is in
    one place and the callback body stays readable.
    """
    return [
        dcc.Store(id="feedback-config",
                  data={"endpoint": ENDPOINT, "token": TOKEN,
                        "max": MAX_MESSAGE, "version": APP_VERSION}),
        # Flipped true by the clientside submit; the server-side toggle watches
        # it to close the dialog once a send has happened.
        dcc.Store(id="feedback-sent", data=False),
    ]


# Clientside so the POST leaves the visitor's browser, never the server. Notes
# that matter and are easy to get wrong:
#
#   * Content-Type "text/plain;charset=utf-8" keeps this a CORS *simple
#     request*. With application/json the browser sends a preflight OPTIONS,
#     which Apps Script web apps cannot answer, and the POST never happens.
#   * mode "no-cors" means the response is opaque and unreadable. That is
#     accepted deliberately: reading it would require CORS headers Apps Script
#     does not reliably set, and the alternative — showing the user an error
#     when the write actually succeeded — is worse than optimistic confirmation.
#   * Apps Script answers with a 302 to a result URL. Browsers follow that as a
#     GET automatically, which is correct; the doPost has already run.
SUBMIT_JS = """
function(n, msg, email, cfg, page, country, gw, iw, dw, theme, session) {
    var NU = window.dash_clientside.no_update;
    if (!n) { return [NU, NU, NU]; }

    var warn = {marginTop: '12px', fontSize: '0.8rem', minHeight: '20px',
                color: '#E8A317'};
    var bad  = {marginTop: '12px', fontSize: '0.8rem', minHeight: '20px',
                color: '#d9534f'};
    var good = {marginTop: '12px', fontSize: '0.8rem', minHeight: '20px',
                color: '#2e9e5b'};

    var text = (msg || '').trim();
    if (!text) {
        return ['Please enter a message first.', warn, false];
    }
    if (!cfg || !cfg.endpoint) {
        return ['Feedback is not configured on this deployment.', bad, false];
    }

    var win = function (v, suffix) { return v ? (v + suffix) : 'Full'; };
    var payload = {
        token:    cfg.token,
        message:  text.slice(0, cfg.max || 4000),
        email:    (email || '').trim(),
        page:     page || '/',
        country:  country || '',
        windows:  win(gw, 'm') + '/' + win(iw, 'm') + '/' + win(dw, 'm'),
        theme:    theme || '',
        viewport: (window.innerWidth || 0) + 'x' + (window.innerHeight || 0),
        version:  (cfg.version || ''),
        ua:       (navigator.userAgent || '').slice(0, 300),
        session:  session || ''
    };

    try {
        fetch(cfg.endpoint, {
            method: 'POST',
            mode: 'no-cors',
            headers: { 'Content-Type': 'text/plain;charset=utf-8' },
            body: JSON.stringify(payload)
        });
    } catch (e) {
        return ['Could not send - please try again.', bad, false];
    }

    return ['Thanks - your feedback was sent.', good, true];
}
"""
