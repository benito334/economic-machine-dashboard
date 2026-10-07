#!/bin/sh
# Regenerate the GoAccess traffic report from Caddy's access log, on a loop.
#
# Server-side metrics, which is the point: unlike a JS beacon this is not
# defeated by ad blockers (they eat roughly a third of client-side analytics)
# and it sees every request — assets, bots, 404s — not just the page views the
# in-app /traffic counter records.
#
# Geo is COUNTRY ONLY and comes from DB-IP's free IP-to-Country Lite database,
# chosen over MaxMind GeoLite2 because it needs no account or licence key
# (MaxMind returns 401 without one). Note the input IPs are already masked to
# a /24 by Caddy's log filter, which still resolves country correctly — that is
# the whole trade: country yes, stored addresses no.
set -eu

LOG=/var/log/caddy/access.log
OUT=/srv/stats/index.html
GEO_DIR=/geoip
INTERVAL="${REPORT_INTERVAL:-600}"   # seconds between regenerations

fetch_geoip() {
    # DB-IP publishes a new file monthly; keep the current month's copy.
    month=$(date +%Y-%m)
    target="$GEO_DIR/dbip-country-lite-$month.mmdb"
    if [ -f "$target" ]; then
        echo "$target"
        return 0
    fi
    url="https://download.db-ip.com/free/dbip-country-lite-$month.mmdb.gz"
    if wget -q -O "$target.gz" "$url" 2>/dev/null && gunzip -f "$target.gz" 2>/dev/null; then
        # Drop older months so the volume doesn't grow without bound.
        find "$GEO_DIR" -name 'dbip-country-lite-*.mmdb' ! -name "$(basename "$target")" -delete 2>/dev/null || true
        echo "$target"
        return 0
    fi
    rm -f "$target.gz" 2>/dev/null || true
    # Fall back to last month's file if this month's isn't published yet —
    # a slightly stale country database is far better than none.
    prev=$(find "$GEO_DIR" -name 'dbip-country-lite-*.mmdb' 2>/dev/null | sort | tail -1)
    [ -n "$prev" ] && echo "$prev" || echo ""
}

mkdir -p "$GEO_DIR" /srv/stats

while :; do
    if [ -s "$LOG" ]; then
        GEO=$(fetch_geoip)
        set -- \
            --log-format=CADDY \
            --output="$OUT" \
            --html-report-title="Economic Machine Dashboard — traffic" \
            --ignore-crawlers \
            --real-os \
            --anonymize-ip
        [ -n "$GEO" ] && set -- "$@" --geoip-database="$GEO"

        if goaccess "$LOG" "$@" 2>/tmp/goaccess.err; then
            echo "[goaccess] report written $(date -u +%FT%TZ)"
        else
            echo "[goaccess] FAILED: $(tail -2 /tmp/goaccess.err)"
        fi
    else
        echo "[goaccess] no log yet, waiting"
    fi
    sleep "$INTERVAL"
done
