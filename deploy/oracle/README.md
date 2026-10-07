# Deploying the live system to Oracle Cloud

This runs the **full stack** (pipeline + scheduler + charting, writable
DuckDB) on an Oracle Cloud "Always Free" VM — not the read-only public demo
(that's `deploy/cloudrun/`, a separate frozen-snapshot deploy path). This is
meant to replace/supplement the NAS as the place the live system runs.

Two pieces, both already in the repo:
- `docker-compose.yml` reads `HOST_DATA_DIR`/`HOST_DB_DIR` from `.env` (falls
  back to the NAS's locked-in paths if unset) — the *same* compose file runs
  on the NAS and on this VM, no divergence to maintain.
- `pull-and-deploy.sh` + the `indicators-deploy.{service,timer}` systemd units
  in this folder — a timer that checks `origin/main` every 15 minutes and
  rebuilds/restarts only if it moved. No webhook, no exposed port for this —
  the VM reaches out to GitHub, nothing reaches in.
  **These are NOT installed, by decision (2026-10-06).** Deploys are manual:
  now that the VM serves the live public site, auto-deploying every commit to
  main would put a mistake in front of visitors within 15 minutes. The script
  itself is kept correct and current (it now uses both compose files) so it
  works if ever enabled — prefer triggering on a release tag, not every commit.
  Nightly DATA imports run regardless, inside the scheduler container.

---

## The VM that is actually running (as of 2026-10-07)

The sections below are the from-scratch build. The live instance predates
some of them and differs in two ways that matter the moment you try to
deploy — both verified against the running box, not assumed:

| | Running VM | What sections 1-4 say |
| :--- | :--- | :--- |
| SSH user | `opc` | `ubuntu` (section 1 assumes an Ubuntu image) |
| Repo path | `/home/opc/economic-machine-dashboard` | `/opt/economic-machine-dashboard` |

Deploy (manual, by decision — see the note above):

```bash
ssh -i ~/.ssh/oracle_economic_machine opc@dashboard.creovalabs.com
cd ~/economic-machine-dashboard
git pull --ff-only origin main
sudo docker compose -f docker-compose.yml -f deploy/oracle/docker-compose.caddy.yml build charting pipeline scheduler
sudo docker compose -f docker-compose.yml -f deploy/oracle/docker-compose.caddy.yml up -d caddy charting scheduler goaccess
```

Both `-f` flags, every time: without the second file Caddy and GoAccess
aren't in the project definition at all, and `up -d` would tear them down.
Build all three services — they are separate image tags off the same
Dockerfile, so building only `charting` leaves `pipeline`/`scheduler`
running stale code at the next nightly import.

`REPO_DIR` in `pull-and-deploy.sh` and `indicators-deploy.service` still
defaults to `/opt/...`; if that automation is ever enabled on THIS box,
override it to the real path first or the unit fails on its first `cd`.

---

## 1. Provision the VM (Oracle Cloud console)

- Create an Always Free **Ampere A1** instance (ARM, up to 4 OCPU / 24GB RAM
  free) running **Ubuntu 22.04/24.04**.
- Note its public IP. In the instance's **VCN security list / Network
  Security Group**, open:
  - **22/tcp** (SSH) — ideally restricted to your own IP, not `0.0.0.0/0`
  - **8502/tcp** (the dashboard) — only if you want it reachable directly;
    otherwise leave closed and reach it over an SSH tunnel
- Oracle's own host-level firewall (`iptables`/`netfilter` via `oci-utils`) is
  separate from the VCN security list — both must allow a port, or Ubuntu's
  `ufw` if you enable it.

**Ampere A1 out of capacity?** This is extremely common for the free ARM
shape in popular regions (Ashburn especially) — it can take minutes to days
to clear. Rather than repeatedly re-clicking Create, use
`retry-create-instance.sh`: copy `retry-create-instance.env.local.example` to
`retry-create-instance.env.local` (gitignored) in this folder, fill in your
tenancy's OCIDs (the comments in the file say where to find each one via the
`oci` CLI), then run the script — it loops across your ADs until one
succeeds, and is safe to leave running unattended (checks for an existing
instance first, so it never double-launches). Needs the `oci` CLI configured
(`~/.oci/config` + an API signing key added via console → My profile →
Tokens and keys → API keys — separate from your SSH key, this one
authenticates CLI calls).

## 2. Install Docker + Compose

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# log out/in (or `newgrp docker`) for the group change to apply
docker compose version   # compose v2 ships with the Docker Engine install above
```

## 3. Clone the repo + configure `.env`

```bash
sudo mkdir -p /opt/economic-machine-dashboard
sudo chown $USER:$USER /opt/economic-machine-dashboard
git clone https://github.com/benito334/economic-machine-dashboard.git /opt/economic-machine-dashboard
cd /opt/economic-machine-dashboard
cp .env.example .env
```

Edit `.env`:
- Fill in `FRED_API_KEY` (and any other provider keys you use).
- Set `HOST_DATA_DIR` / `HOST_DB_DIR` to real paths on this VM's own disk,
  e.g. `/opt/economic-machine-dashboard-data` and
  `/opt/economic-machine-dashboard-db` — create those directories first
  (`mkdir -p`). Do **not** leave them pointed at `/mnt/data/...`; that path
  only exists on the NAS.
- Fill in `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` and, optionally,
  `HEALTHCHECK_PING_URL` for failed/missed-sync alerts (see the comments in
  `.env.example` for how to get each).
- Set `AUTO_IMPORT_ENABLED=1` and `AUTO_IMPORT_TIME` if you want the daily
  import running headless (no dashboard UI needed to configure it here).

```bash
docker compose up -d --build
```

First run imports all data from scratch — same as any fresh install.

## 4. Install the auto-deploy timer — SKIP on the public VM

**Do not run this on the instance serving dashboard.creovalabs.com.** Deploys
there are manual by decision (see the note at the top of this file): a timer
would put any mistake on main in front of visitors within 15 minutes. These
steps are kept for a staging/private instance, or for the day this is
switched to trigger on a release tag instead of every commit.

```bash
sudo cp deploy/oracle/indicators-deploy.service deploy/oracle/indicators-deploy.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now indicators-deploy.timer
```

Check it: `systemctl list-timers indicators-deploy.timer`. Logs from any run
(including failures): `journalctl -u indicators-deploy -n 50`.

To change the poll interval, edit `OnUnitActiveSec=` in the `.timer` file,
`daemon-reload`, and restart the timer.

## 5. Verify alerts

- Force a failed import to test the Telegram path: temporarily set an
  invalid `FRED_API_KEY` in `.env`, run `docker compose restart scheduler`,
  trigger "Update now" from the dashboard Settings page (or wait for the
  schedule) — a Telegram message should arrive. Restore the real key after.
- If using healthchecks.io, its dashboard should show a green "last ping"
  after the next successful import, and will email/alert you if a full day
  passes with no ping.
