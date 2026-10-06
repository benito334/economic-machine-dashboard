/**
 * Economic Machine Dashboard — feedback receiver.
 *
 * Paste this into the Apps Script project bound to the feedback Sheet, then
 * deploy as a Web app with:
 *     Execute as:      Me
 *     Who has access:  Anyone          <-- NOT "Anyone with a Google account"
 *
 * "Anyone with a Google account" makes anonymous visitors hit a sign-in page,
 * which is what the first deployment did (verified: GET redirected to
 * accounts.google.com, POST returned 401).
 *
 * Design constraints this satisfies (see docs/worklog.md 2026-10-05):
 *   - The dashboard VM writes NOTHING. All feedback lands here, in the Sheet.
 *   - No IP address and no geolocation is collected, by decision.
 *   - The browser must POST with Content-Type "text/plain;charset=utf-8" so
 *     the request stays a CORS "simple request" and never triggers a preflight
 *     OPTIONS, which Apps Script web apps cannot answer.
 */

// ─────────────────────────────────────────────────────────────────────────────
// FILL THESE IN when pasting into Apps Script. They are placeholders here on
// purpose: this repository is PUBLIC, and the /exec URL is necessarily public
// too (any visitor can read it out of the dashboard's page source). A token
// published alongside it would provide no friction at all.
//
// The deployed copy therefore holds the real values and this file does not.
// If you ever re-paste from here, re-enter them.
//
// Hardening option, if the endpoint ever gets abused: move both into Script
// Properties (Project Settings -> Script Properties) and read them with
//   PropertiesService.getScriptProperties().getProperty('SHARED_TOKEN')
// so they live outside the code entirely.
// ─────────────────────────────────────────────────────────────────────────────
var SHEET_ID = 'PASTE_YOUR_SHEET_ID_HERE';
var SHEET_NAME = 'Feedback';

// Must match FEEDBACK_TOKEN in the dashboard's .env. Not a security boundary —
// it stops drive-by junk from anything that stumbles onto the endpoint without
// the dashboard's payload.
var SHARED_TOKEN = 'PASTE_YOUR_SHARED_TOKEN_HERE';

var MAX_MESSAGE = 4000;   // characters; anything longer is truncated, not rejected
var MAX_FIELD = 300;      // every other field
var RATE_LIMIT_PER_HOUR = 12;   // per session id

function doGet() {
  // Health check only — never returns feedback content.
  return _json({ ok: true, service: 'emd-feedback' });
}

function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return _json({ ok: false, error: 'empty body' });
    }

    var body;
    try {
      body = JSON.parse(e.postData.contents);
    } catch (err) {
      return _json({ ok: false, error: 'bad json' });
    }

    if (String(body.token || '') !== SHARED_TOKEN) {
      return _json({ ok: false, error: 'bad token' });
    }

    var message = _clean(body.message, MAX_MESSAGE);
    if (!message) {
      return _json({ ok: false, error: 'empty message' });
    }

    // Crude per-session throttle. CacheService is best-effort and resets, which
    // is fine — this is abuse friction, not an access control.
    var session = _clean(body.session, 64) || 'anon';
    if (_overRateLimit(session)) {
      return _json({ ok: false, error: 'rate limited' });
    }

    var sheet = SpreadsheetApp.openById(SHEET_ID).getSheetByName(SHEET_NAME);
    if (!sheet) {
      return _json({ ok: false, error: 'sheet not found' });
    }

    sheet.appendRow([
      new Date(),                              // Timestamp (sheet timezone)
      message,                                 // Message
      _clean(body.email, MAX_FIELD),           // Email (optional)
      _clean(body.page, MAX_FIELD),            // Page
      _clean(body.country, MAX_FIELD),         // Country
      _clean(body.windows, MAX_FIELD),         // Windows (G/I/D)
      _clean(body.theme, MAX_FIELD),           // Theme
      _clean(body.viewport, MAX_FIELD),        // Viewport
      _clean(body.version, MAX_FIELD),         // App version
      _clean(body.ua, MAX_FIELD)               // User agent
    ]);

    return _json({ ok: true });
  } catch (err) {
    // Never leak a stack trace to the caller.
    console.error(err);
    return _json({ ok: false, error: 'server error' });
  }
}

/** Trim, cap length, and strip control characters and leading formula markers. */
function _clean(value, maxLen) {
  if (value === null || value === undefined) return '';
  var s = String(value).replace(/[\x00-\x1F\x7F]/g, ' ').trim();
  if (s.length > maxLen) s = s.slice(0, maxLen);
  // A cell beginning with = + - @ is executed as a formula by Sheets (and by
  // Excel on export). Prefix with an apostrophe so it is stored as text.
  if (/^[=+\-@]/.test(s)) s = "'" + s;
  return s;
}

function _overRateLimit(session) {
  try {
    var cache = CacheService.getScriptCache();
    var key = 'fb_' + session;
    var n = parseInt(cache.get(key) || '0', 10);
    if (n >= RATE_LIMIT_PER_HOUR) return true;
    cache.put(key, String(n + 1), 3600);
    return false;
  } catch (err) {
    return false;   // never block real feedback because the cache misbehaved
  }
}

function _json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
