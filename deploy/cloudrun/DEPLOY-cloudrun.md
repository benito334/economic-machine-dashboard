# Deploying the public dashboard to Google Cloud Run

Cloud Run runs the dashboard as a container, **scales to zero when idle**, and
gives you an HTTPS URL like `https://economic-machine-xxxx.a.run.app`. For a
class-sized audience it stays inside Google's **free tier** (2M requests +
360k GiB-seconds/month), so your bill is effectively **$0** — but Google
requires a **billing account with a credit card** on file to enable it.

The app runs read-only (`PUBLIC_MODE=1`) with the database baked into the
image. No writes, no scheduler — a frozen snapshot with the "static demo"
banner. To publish fresh data you rebuild the bundle and redeploy.

You need two things in this folder at deploy time:
- `Dockerfile` (here — clones the app code from GitHub at build)
- `emd_data.tar.gz` (the data bundle — put it here; it is git-ignored)

---

## One-time setup

### 1. Google Cloud account + project + billing
- Go to https://console.cloud.google.com and sign in / sign up.
- Create a **new project** (top bar → project dropdown → New Project). Note the
  **Project ID** (e.g. `economic-machine-471203`).
- Enable **billing** on it: console → **Billing** → link a billing account
  (card required; the free tier still applies).

### 2. Open Cloud Shell (no local installs needed)
Click the **`>_` Cloud Shell** icon (top-right of the console). This is a
browser terminal with `gcloud`, `git`, and Docker already installed. Everything
below runs there.

Set your project:
```bash
gcloud config set project YOUR_PROJECT_ID
```

### 3. Enable the required APIs (once)
```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
```

### 4. Get the deploy files into Cloud Shell
```bash
git clone https://github.com/benito334/economic-machine-dashboard.git
cd economic-machine-dashboard/deploy/cloudrun
```
Then upload the data bundle into this folder: in Cloud Shell click the
**⋮ menu → Upload**, choose your `emd_data.tar.gz`, and if it lands in your home
directory move it here:
```bash
mv ~/emd_data.tar.gz .
ls -la           # you should see Dockerfile and emd_data.tar.gz
```

### 5. Deploy 🚀
```bash
gcloud run deploy economic-machine \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi --cpu 1 \
  --max-instances 3 --min-instances 0
```
`--max-instances 3` bounds how many containers can ever run at once — even
under a traffic flood you can never run up more than a few instances' worth of
compute. `--min-instances 0` keeps it scaled to zero when idle (no idle cost).
- First run asks to create an Artifact Registry repo — say **yes**.
- It builds the image (Cloud Build, ~3–4 min) and deploys.
- When it finishes it prints a **Service URL** — that's your public link. Open it.

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

On the machine with the live database:
```bash
python scripts/build_public_bundle.py         # → emd_data.tar.gz
```
Copy that into `deploy/cloudrun/` (in Cloud Shell) and re-run the **step 5**
deploy command. Cloud Run rolls out a new revision with the fresh data; the URL
stays the same.

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
