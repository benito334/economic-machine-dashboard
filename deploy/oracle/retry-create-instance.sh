#!/usr/bin/env bash
# Retries launching the economic-machine-dashboard VM until Oracle's Ampere
# A1 Always Free capacity frees up in one of your region's ADs. Oracle's
# "out of host capacity" error is extremely common for this shape in popular
# regions and typically clears within minutes to days — this just automates
# the "keep clicking Create" workaround everyone ends up doing by hand.
#
# Safe to re-run: checks for an existing instance with the same display name
# first and exits immediately if one already exists, so it never launches a
# duplicate.
#
# Config is tenancy-specific (OCIDs), so it's never hardcoded here — copy
# retry-create-instance.env.local.example to retry-create-instance.env.local
# (gitignored) next to this script and fill in your own values, or export
# the same variables before running.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_ENV="$SCRIPT_DIR/retry-create-instance.env.local"
[ -f "$LOCAL_ENV" ] && source "$LOCAL_ENV"

: "${OCI_CLI_BIN:=$HOME/.oci-retry/venv/bin/oci}"
: "${DISPLAY_NAME:=economic-machine-dashboard}"
: "${SLEEP_SECONDS:=60}"
: "${LOG_FILE:=$HOME/.oci-retry/retry.log}"

required=(COMPARTMENT_ID SHAPE SHAPE_CONFIG_JSON IMAGE_ID SUBNET_ID SSH_KEY_FILE AVAILABILITY_DOMAINS)
for var in "${required[@]}"; do
    if [ -z "${!var:-}" ]; then
        echo "Missing required config: $var (set it in $LOCAL_ENV or export it)" >&2
        exit 1
    fi
done
read -ra ADS <<< "$AVAILABILITY_DOMAINS"

OCI="$OCI_CLI_BIN"

log() { echo "$(date -Is) $*" | tee -a "$LOG_FILE"; }

notify_telegram() {
    local msg="$1"
    [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ] || return 0
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_CHAT_ID}" --data-urlencode "text=${msg}" >/dev/null || true
}

# Idempotency: don't launch a second instance if one already exists.
existing=$("$OCI" compute instance list \
    --compartment-id "$COMPARTMENT_ID" \
    --display-name "$DISPLAY_NAME" \
    --lifecycle-state RUNNING \
    --query "data[0].id" --raw-output 2>/dev/null)
if [ -n "$existing" ] && [ "$existing" != "null" ]; then
    log "Instance already exists and is running: $existing — nothing to do."
    exit 0
fi

attempt=0
while true; do
    for ad in "${ADS[@]}"; do
        attempt=$((attempt + 1))
        log "Attempt $attempt: trying $ad ..."
        output=$("$OCI" compute instance launch \
            --availability-domain "$ad" \
            --compartment-id "$COMPARTMENT_ID" \
            --shape "$SHAPE" \
            --shape-config "$SHAPE_CONFIG_JSON" \
            --image-id "$IMAGE_ID" \
            --subnet-id "$SUBNET_ID" \
            --assign-public-ip true \
            --ssh-authorized-keys-file "$SSH_KEY_FILE" \
            --display-name "$DISPLAY_NAME" \
            --wait-for-state RUNNING --max-wait-seconds 300 2>&1)
        status=$?

        if [ $status -eq 0 ]; then
            instance_id=$(echo "$output" | python3 -c "import json,sys; print(json.load(sys.stdin)['data']['id'])" 2>/dev/null)
            public_ip=$("$OCI" compute instance list-vnics \
                --instance-id "$instance_id" \
                --query "data[0].\"public-ip\"" --raw-output 2>/dev/null)
            log "SUCCESS in $ad — instance $instance_id, public IP $public_ip"
            notify_telegram "Economic Machine Dashboard VM is up in $ad. Public IP: $public_ip"
            exit 0
        fi

        if echo "$output" | grep -qi "out of host capacity"; then
            log "$ad: out of capacity, moving on."
        else
            log "$ad: unexpected error, logging and continuing:"
            echo "$output" | tee -a "$LOG_FILE"
        fi
    done
    log "Full round done, sleeping ${SLEEP_SECONDS}s before next round."
    sleep "$SLEEP_SECONDS"
done
