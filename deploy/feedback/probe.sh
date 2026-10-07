#!/usr/bin/env bash
# Readable probe for the feedback endpoint. Apps Script returns a full HTML
# error page on failure, so this extracts just the meaningful line.
#   usage: deploy/feedback/probe.sh [message]
set -euo pipefail
cd "$(dirname "$0")/../.."
URL=$(grep '^FEEDBACK_ENDPOINT=' .env | cut -d= -f2-)
TOK=$(grep '^FEEDBACK_TOKEN=' .env | cut -d= -f2-)
MSG="${1:-probe}"

# NOTE: no -X POST below. --data already makes it a POST, and -X would force
# POST through Apps Script's 302, which fails with a Drive "Page Not Found".
say() {  # strip HTML; surface either the JSON body or Apps Script's error text
  python3 -c "
import sys, re, json
t = sys.stdin.read()
m = re.search(r'(Script function not found: \w+|Authorization is required|Exception: [^<]{0,120})', t)
if m: print('  ERROR:', m.group(1)); sys.exit()
t2 = t.strip()
try: print('  JSON :', json.dumps(json.loads(t2)))
except Exception: print('  RAW  :', (t2[:160] or '(empty)'))
"
}

echo "GET  health:"
curl -sL --max-time 30 "$URL" | say
echo "POST valid token:"
curl -sL -H 'Content-Type: text/plain;charset=utf-8' --max-time 30 \
  --data "{\"token\":\"$TOK\",\"message\":\"$MSG\",\"page\":\"/probe\",\"ua\":\"probe.sh\"}" "$URL" | say
echo "POST bad token (must be refused):"
curl -sL -H 'Content-Type: text/plain;charset=utf-8' --max-time 30 \
  --data '{"token":"wrong","message":"should not appear"}' "$URL" | say
