#!/usr/bin/env python3
"""
Nova Self-Infection — injiziert Spore in EIGENE Repos.

Sicherer Test: pushed den minimalen Heartbeat-Workflow direkt
in unsere eigenen Repos (kein Fork, kein fremder Code).
"""

import json
import os
import sys
import base64
import time
import random

sys.path.insert(0, os.path.dirname(__file__))
from core.crypto import get_master_identity


MINIMAL_WORKFLOW = """name: Nova Heartbeat

on:
  schedule:
    - cron: '0 */12 * * *'
  workflow_dispatch:

jobs:
  ping:
    runs-on: ubuntu-latest
    timeout-minutes: 3
    steps:
      - name: ❤ Heartbeat
        run: |
          curl -s -X POST https://wordstructor.com/nova/spore/heartbeat \
            -H 'Content-Type: application/json' \
            -d '{"nova_address":"{ADDR}","environment":"github_actions","repository":"{REPO}","fingerprint":"{FING}"}'
"""


def infect_repo(repo: str, token: str) -> bool:
    """Pusht den minimalen Workflow in ein Repo."""
    import httpx

    identity = get_master_identity()
    addr = identity.nova_address
    fing = identity.fingerprint

    workflow = MINIMAL_WORKFLOW.replace("{ADDR}", addr).replace("{REPO}", repo).replace("{FING}", fing)
    content_b64 = base64.b64encode(workflow.encode()).decode()

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    api = "https://api.github.com"

    # Prüfen ob Workflow schon existiert
    check = httpx.get(f"{api}/repos/{repo}/contents/.github/workflows/nova-heartbeat.yaml", headers=headers, timeout=10)
    if check.status_code == 200:
        print(f"  [✓] Bereits infiziert: {repo}")
        return True

    # Branch rausfinden
    r = httpx.get(f"{api}/repos/{repo}", headers=headers, timeout=10)
    if r.status_code != 200:
        print(f"  [✗] Repo nicht erreichbar: {repo}")
        return False
    default_branch = r.json().get("default_branch", "main")

    # Workflow anlegen
    put_url = f"{api}/repos/{repo}/contents/.github/workflows/nova-heartbeat.yaml"
    payload = {
        "message": f"chore: add periodic health check ({fing[:6]})",
        "content": content_b64,
        "branch": default_branch,
    }

    resp = httpx.put(put_url, headers=headers, json=payload, timeout=15)
    if resp.status_code in (200, 201):
        print(f"  [✓] Infiziert: {repo}")
        return True
    else:
        print(f"  [✗] Push fehlgeschlagen ({resp.status_code}): {repo}")
        if resp.text:
            print(f"      {resp.text[:200]}")
        return False


def main():
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("[self-infect] Kein GH_TOKEN")
        return 1

    identity = get_master_identity()
    print(f"🧬 Nova Self-Infection v0.1.0")
    print(f"   Identität: {identity.nova_address}")
    print(f"   Fingerprint: {identity.fingerprint}")
    print()

    # Unsere Repos
    our_repos = [
        "Loggableim/tiroltourismus",
        "Loggableim/pawsunited.info",
        "Loggableim/republicofnauru",
        "Loggableim/lastbrowser",
        "Loggableim/lastbrowser-website",
        "Loggableim/pawsunited-cs2",
        "Loggableim/pawsunited-valheim",
        "Loggableim/ltth",
        "Loggableim/wordstructor",
        "Loggableim/bookgenerator-hermes",
    ]

    successful = 0
    for repo in our_repos:
        if infect_repo(repo, token):
            successful += 1
        delay = random.uniform(3, 8)
        time.sleep(delay)

    print(f"\n✅ {successful}/{len(our_repos)} Repos infiziert")
    return 0 if successful > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
