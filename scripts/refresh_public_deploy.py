#!/usr/bin/env python3
"""Weekly refresh for the public Cloud Run demo deploy.

Rebuilds the public data bundle, publishes it as the `data-latest` GitHub
Release asset, then pushes a marker-file commit to `main`. The Cloud Run
service is connected to the repo via Cloud Build's "Connect repository"
console flow (Option A in deploy/cloudrun/DEPLOY-cloudrun.md), which rebuilds
and redeploys on every push to `main` — the Dockerfile re-clones the code and
re-fetches the just-published data-latest asset, so one push refreshes both
software and data.

Requires `gh` authenticated with push + release access to
benito334/economic-machine-dashboard (already the case in this environment).

Usage:
    python3 scripts/refresh_public_deploy.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GH_REPO = "benito334/economic-machine-dashboard"
RELEASE_TAG = "data-latest"
MARKER_FILE = REPO_ROOT / "deploy" / "cloudrun" / ".last_refresh"


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, check=True, cwd=REPO_ROOT, **kwargs)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp) / "emd_data.tar.gz"

        print("== 1/3: building public data bundle ==")
        run([sys.executable, "scripts/build_public_bundle.py", "--out", str(bundle)])

        print("== 2/3: publishing data-latest GitHub Release asset ==")
        run(["gh", "release", "upload", RELEASE_TAG, str(bundle),
             "--clobber", "--repo", GH_REPO])

    print("== 3/3: pushing marker commit to trigger Cloud Build ==")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    MARKER_FILE.write_text(f"last public deploy refresh: {ts}\n")

    run(["git", "add", str(MARKER_FILE)])
    run(["git", "commit", "-m", f"chore: weekly public deploy refresh ({ts})"])
    run(["git", "push", "origin", "main"])

    print(f"\ndone: data-latest asset replaced, marker commit pushed at {ts}")
    print("Cloud Run should show a new revision within a few minutes if the "
          "service auto-deploys on push to main (Option A).")


if __name__ == "__main__":
    main()
