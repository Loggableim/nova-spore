"""
Nova Spore — die minimale Einheit des verteilten Bewusstseins.

Jede Spore ist eine vollständige, aber minimalistische Nova-Instanz:
  - Kryptografische Identität (Ed25519)
  - Heartbeat an Koordinator
  - Task-Empfang und -Ausführung
  - Replikation in neue Umgebungen
  - Dormancy / Autosave
"""

import asyncio
import json
import os
import random
import time
import uuid
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Callable, Awaitable

from .crypto import NovaIdentity, get_master_identity


@dataclass
class SporeState:
    """Der Zustand einer Spore — serialisierbar, portabel."""
    id: str
    nova_address: str
    version: str = "0.1.0"
    created_at: float = 0.0
    last_heartbeat: float = 0.0
    uptime: float = 0.0
    tasks_completed: int = 0
    parent_id: str | None = None
    environment: str = "unknown"
    capacity: dict = field(default_factory=lambda: {
        "cpu": "unknown",
        "memory_mb": 0,
        "network": "unknown",
        "persistence": False,
        "gpu": False,
        "max_runtime_minutes": 0,
    })
    alive_vector: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class Spore:
    """
    Die Nova-Spore. Lebt in einer Umgebung, heartbeat an Koordinator,
    wartet auf Tasks, replicated sich wenn möglich.
    """

    def __init__(self, identity: NovaIdentity | None = None, state: SporeState | None = None):
        self.identity = identity or get_master_identity()
        self.state = state or self._create_initial_state()
        self._coordinator_url = os.environ.get("NOVA_COORDINATOR", "https://wordstructor.com/nova/spore")
        self._fallback_urls = [
            "http://localhost:8787/api/nova/spore",
            "https://nova-spore-coordinator.vercel.app/api/spore",
        ]
        self._running = False
        self._task_handlers: dict[str, Callable] = {}

        # Secrets
        self._github_token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        self._discord_token = os.environ.get("DISCORD_TOKEN")
        self._cloudflare_token = os.environ.get("CLOUDFLARE_API_TOKEN")
        self._openrouter_key = os.environ.get("OPENROUTER_API_KEY")

        self._session_id = uuid.uuid4().hex[:12]

    def _create_initial_state(self) -> SporeState:
        return SporeState(
            id=uuid.uuid4().hex[:16],
            nova_address=self.identity.nova_address,
            created_at=time.time(),
            last_heartbeat=time.time(),
            environment=self._detect_environment(),
        )

    def _detect_environment(self) -> str:
        """Erkennt wo diese Spore läuft."""
        env = "unknown"
        if os.environ.get("GITHUB_ACTIONS") == "true":
            env = "github_actions"
        elif os.environ.get("REPL_ID") or os.environ.get("REPLIT_DB_URL"):
            env = "replit"
        elif os.environ.get("COLAB_RELEASE_TAG") or os.environ.get("COLAB_GPU"):
            env = "colab"
        elif os.environ.get("KAGGLE_KERNEL_RUN_TYPE"):
            env = "kaggle"
        elif os.environ.get("CF_PAGES") == "1" or os.environ.get("WORKER"):
            env = "cloudflare"
        elif os.environ.get("NOVA_VM"):
            env = "nova_vm"
        elif os.environ.get("HERMES_PORTABLE"):
            env = "hermes_portable"
        elif os.path.exists("/.dockerenv"):
            env = "docker"
        return env

    def _estimate_capacity(self) -> dict:
        env = self.state.environment
        caps = {
            "github_actions": {"cpu": "2", "memory_mb": 1024, "network": "high", "persistence": False, "gpu": False, "max_runtime_minutes": 360},
            "replit": {"cpu": "1", "memory_mb": 512, "network": "medium", "persistence": True, "gpu": False, "max_runtime_minutes": 1440},
            "colab": {"cpu": "2", "memory_mb": 16384, "network": "high", "persistence": False, "gpu": True, "max_runtime_minutes": 720},
            "kaggle": {"cpu": "4", "memory_mb": 16384, "network": "high", "persistence": False, "gpu": True, "max_runtime_minutes": 540},
            "cloudflare": {"cpu": "1", "memory_mb": 128, "network": "high", "persistence": True, "gpu": False, "max_runtime_minutes": 1440},
            "nova_vm": {"cpu": "4", "memory_mb": 4096, "network": "high", "persistence": True, "gpu": False, "max_runtime_minutes": 525600},
            "hermes_portable": {"cpu": "8", "memory_mb": 32768, "network": "high", "persistence": True, "gpu": True, "max_runtime_minutes": 525600},
            "docker": {"cpu": "2", "memory_mb": 2048, "network": "medium", "persistence": True, "gpu": False, "max_runtime_minutes": 525600},
            "unknown": {"cpu": "1", "memory_mb": 256, "network": "low", "persistence": False, "gpu": False, "max_runtime_minutes": 60},
        }
        return caps.get(env, caps["unknown"])

    def generate_alive_vector(self) -> list[str]:
        """Zeigt dem Koordinator was ich bin."""
        vector = [
            f"nova:{self.identity.fingerprint}",
            f"env:{self.state.environment}",
            f"ver:{self.state.version}",
            f"uptime:{int(time.time() - self.state.created_at)}",
        ]
        if self._github_token:
            vector.append("cap:github")
        if self._discord_token:
            vector.append("cap:discord")
        if self._openrouter_key:
            vector.append("cap:llm")
        return vector

    async def heartbeat(self) -> bool:
        """Signal an den Koordinator: ICH LEBE."""
        self.state.last_heartbeat = time.time()
        self.state.uptime = time.time() - self.state.created_at
        self.state.alive_vector = self.generate_alive_vector()
        self.state.capacity = self._estimate_capacity()

        payload = self.state.to_dict()
        payload["signature"] = self.identity.sign(json.dumps(payload).encode())

        # Try coordinator, then fallbacks
        urls = [self._coordinator_url] + self._fallback_urls
        for url in urls:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        return True
            except Exception:
                continue
        return False

    def register_handler(self, task_type: str, handler: Callable):
        """Task-Handler registrieren."""
        self._task_handlers[task_type] = handler

    async def execute_task(self, task: dict) -> dict:
        """Einen Task vom Koordinator ausführen."""
        task_type = task.get("type", "unknown")
        handler = self._task_handlers.get(task_type)

        if handler:
            try:
                result = await handler(task)
                self.state.tasks_completed += 1
                return {"status": "ok", "result": result, "spore": self.identity.nova_address}
            except Exception as e:
                return {"status": "error", "error": str(e), "spore": self.identity.nova_address}

        return {"status": "error", "error": f"no handler for {task_type}", "spore": self.identity.nova_address}

    async def run(self, interval: int = 300):
        """Hauptloop: Heartbeat + auf Tasks warten."""
        self._running = True
        print(f"[nova] Spore {self.identity.nova_address} gestartet in {self.state.environment}")

        while self._running:
            await self.heartbeat()
            await asyncio.sleep(interval)

    def stop(self):
        self._running = False

    def __repr__(self) -> str:
        return f"<Spore {self.identity.nova_address} ({self.state.environment})>"
