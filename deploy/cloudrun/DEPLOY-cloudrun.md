# Deploying the public dashboard to Google Cloud Run

Cloud Run runs the dashboard as a container, **scales to zero when idle**, and
gives you an HTTPS URL like `https://economic-machine-xxxx.a.run.app`. For a
class-sized audience it stays inside Google's **free tier** (2M requests +
360k GiB-seconds/month), so your bill is effectively **$0** — but Google
requires a **billing account with a credit card** on file to enable it.

The app runs read-only (`PUBLIC_MODE=1`) with the database baked into the
image. No writes, no scheduler — a frozen snapshot with the "static demo"
banner. To publish fresh data you rebuild the bundle and redeploy.

The Dockerfile is **fully self-contained** — it fetches both the app code and
the data bundle from GitHub at build time, so you don't upload anything. That
lets you deploy entirely from the console with no terminal (Option A).

---

## First: create a project + billing (both options need this)
- Go to https://console.cloud.google.com and sign in / sign up.
- Create a **new project** (top bar → project dropdown → New Project). Note the
  **Project ID** (e.g. `economic-machine-471203`).
- Enable **billing** on it: console → **Billing** → link a billing account
  (card required; the free tier still applies — and see the kill-switch below).

---

## Option A — Console click-flow (no terminal) ⭐ recommended

1. Go to **Cloud Run** → click **Connect repository** (under "Deploy a web service").
2. Click **Set up with Cloud Build** → **GitHub** → authorize, then pick the
   repo **`benito334/economic-machine-dashboard`**, branch **`main`**.
3. **Build configuration:**
   - Build type: **Dockerfile**
   - Source location / Dockerfile path: **`/deploy/cloudrun/Dockerfile`**
4. **Service settings:**
   - Region: **us-central1**
   - Authentication: **Allow unauthenticated invocations** (so the public can view)
   - Expand **Container(s) → Edit**:
     - Memory: **2 GiB**, CPU: **1**
     - Under Autoscaling: **Min instances 0**, **Max instances 3**
5. Click **Create**. Cloud Build builds the image (~3–4 min) and deploys. When
   it's done, the service page shows a **URL** (`https://…run.app`) — that's your
   public link. Open it.

> Max instances 3 + scale-to-zero bound your cost to near nothing; the kill
> switch below makes $0 a hard guarantee.

---

## Option B — Cloud Shell (one command, if you prefer a terminal)

Click the **`>_` Cloud Shell** icon (top-right of the console), then:
```bash
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
git clone https://github.com/benito334/economic-machine-dashboard.git
gcloud run deploy economic-machine \
  --source economic-machine-dashboard/deploy/cloudrun \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi --cpu 1 \
  --max-instances 3 --min-instances 0
```
No file upload needed — the Dockerfile fetches its own data. Say **yes** if it
offers to create an Artifact Registry repo. It prints a **Service URL** when done.

### 6. (Optional) Turn on the traffic page
```bash
gcloud run services update economic-machine --region us-central1 \
  --set-env-vars TRAFFIC_KEY=your-secret-here
```
Then view metrics at `https://<your-url>/traffic?key=your-secret-here`.
(Traffic counts reset whenever a fresh instance starts — it's a live counter,
not persistent storage.)

---

## Refreshing the data later

The deployed app reads the `emd_data.tar.gz` asset on the **`data-latest`**
GitHub Release. To publish fresh numbers, on the machine with the live database:
```bash
python scripts/build_public_bundle.py                 # → emd_data.tar.gz
gh release upload data-latest emd_data.tar.gz --clobber \
  --repo benito334/economic-machine-dashboard         # replace the asset
```
Then trigger a rebuild so Cloud Run picks up the new data:
- **Option A (console):** Cloud Run → your service → **Edit & deploy new
  revision** → **Deploy** (rebuilds from the repo, re-fetching the asset), or
- **Option B (CLI):** re-run the `gcloud run deploy … --source …` command.

The URL stays the same; the "data through" date in the banner updates.

---

## Guaranteeing you are NEVER billed

Important truth about Google Cloud: **a budget by itself only sends email
alerts — it does not stop spending.** There are three layers of protection;
use as many as you want. For this dashboard, Layers 1 + 2 already make a real
charge extremely unlikely, and Layer 3 makes it *impossible*.

### Layer 1 — stay inside the free tier (automatic)
Cloud Run's monthly free tier is 2M requests + 360,000 GiB-seconds +
180,000 vCPU-seconds. A class-sized audience on a scale-to-zero service does
not come close. Idle = zero instances = zero cost.

### Layer 2 — bound the blast radius (one command)
`--max-instances 3` (in the deploy command above) caps how much compute can
ever run at once. Even a traffic spike can't scale you into a big bill.

### Layer 3 — hard kill switch: auto-disable billing (never charged, period)
This is the only thing that *guarantees* $0. A budget triggers a function that
**switches billing off** on the project — which shuts the dashboard down rather
than letting it cost you a cent. Exactly "stop hosting instead of charging me."

1. **Create a budget** → console → **Billing → Budgets & alerts → Create budget**.
   Scope it to your project, set the amount to e.g. **$1**, thresholds at 100%.
2. On the budget's last page, **Manage notifications → Connect a Pub/Sub topic**,
   create a topic named `billing-kill`.
3. **Deploy the kill function** (in Cloud Shell):
   ```bash
   mkdir ~/killbilling && cd ~/killbilling
   cat > main.py <<'PY'
   import base64, json, os
   from googleapiclient import discovery
   BILLING = discovery.build('cloudbilling', 'v1').projects()
   def stop_billing(event, context):
       data = json.loads(base64.b64decode(event['data']).decode())
       # only act once cost has met/exceeded the budget
       if data.get('costAmount', 0) < data.get('budgetAmount', 0):
           return
       project = f"projects/{os.environ['GCP_PROJECT']}"
       info = BILLING.getBillingInfo(name=project).execute()
       if info.get('billingEnabled'):
           BILLING.updateBillingInfo(
               name=project, body={'billingAccountName': ''}).execute()
           print('BILLING DISABLED for', project)
   PY
   cat > requirements.txt <<'PY'
   google-api-python-client
   PY
   gcloud functions deploy stop_billing \
     --runtime python311 --trigger-topic billing-kill \
     --entry-point stop_billing --set-env-vars GCP_PROJECT=$(gcloud config get-value project)
   ```
4. **Give the function permission to disable billing.** Find its service
   account (console → Cloud Functions → `stop_billing` → Details), then grant
   that account the **Billing Account Administrator** role on your billing
   account (console → Billing → Account management → Permissions → Add).

Now if spend ever reaches $1, billing is switched off automatically: Cloud Run
stops serving (the URL goes dark) and no charge can accrue. To bring it back
you re-enable billing on the project.

> Simpler alternative if the function feels like too much: set a **$1 budget
> alert to your email** and rely on Layers 1 + 2. Realistically you will never
> see a charge for a class demo — but only Layer 3 is a hard guarantee.

## Cost & behaviour notes

- **Scales to zero:** with no traffic, no instances run and you pay nothing.
  The first visit after idle has a ~2–5s cold start while an instance spins up.
- **Free tier** comfortably covers a class. To be safe you can cap spend:
  console → the service → **Edit** → set **Maximum number of instances** to a
  small number (e.g. 3), and/or set a Billing **budget alert**.
- **Region:** `us-central1` is a good default (free-tier eligible). Pick one
  near your class if you prefer.
- **No database writes happen** in the deployed app — it's a pure reader, so
  concurrent viewers never conflict.
