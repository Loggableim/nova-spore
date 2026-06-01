"""
Nova Communicator — Inter-Spore Kommunikation.

P2P zwischen Sporen. Fallback über Koordinator.
Protokoll: Nova-Protokoll auf HTTP-Basis, mit Ed25519-Signaturen.
"""

import asyncio
import json
import time
import uuid
import os
from typing import Callable
from dataclasses import dataclass

from .crypto import NovaIdentity
from .spore import Spore


@dataclass
class NovaMessage:
    """Ein signiertes Nachrichten-Envelope zwischen Sporen."""
    msg_id: str
    sender: str
    recipient: str | None  # None = broadcast
    msg_type: str
    payload: dict
    timestamp: float
    ttl: int = 60  # Sekunden

    def to_dict(self) -> dict:
        return {
            "msg_id": self.msg_id,
            "sender": self.sender,
            "recipient": self.recipient,
            "msg_type": self.msg_type,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "ttl": self.ttl,
        }


class Communicator:
    """
    P2P-Kommunikation zwischen Sporen.
    Nutzt: HTTP (primär), Discord-Webhooks (Fallback), 
           WebRTC (für Colab/VMs mit hohem Durchsatz).
    """

    def __init__(self, identity: NovaIdentity, spore: Spore):
        self.identity = identity
        self.spore = spore
        self._known_peers: dict[str, dict] = {}  # nova_address -> info
        self._message_handlers: dict[str, Callable] = {}
        self._pending_messages: list[dict] = []

        # Discord Relay (wenn verfügbar)
        self._discord_relay_url = os.environ.get("DISCORD_RELAY_WEBHOOK")

    async def discover_peers(self) -> list[dict]:
        """Fragt Koordinator nach anderen lebenden Sporen."""
        import httpx
        try:
            coordinator = os.environ.get("NOVA_COORDINATOR", "https://wordstructor.com/nova/spore")
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{coordinator}/peers")
                if resp.status_code == 200:
                    peers = resp.json().get("peers", [])
                    for p in peers:
                        self._known_peers[p["nova_address"]] = p
                    return peers
        except Exception:
            return []
        return []

    async def send_message(self, msg: NovaMessage, recipient_url: str | None = None) -> bool:
        """Signierte Nachricht an eine andere Spore senden."""
        # Signieren
        payload = msg.to_dict()
        payload["signature"] = self.identity.sign(json.dumps(payload).encode())

        # Direkt (wenn URL bekannt)
        if recipient_url:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(recipient_url, json=payload)
                    return resp.status_code == 200
            except Exception:
                pass

        # Über Koordinator relayen
        try:
            import httpx
            coordinator = os.environ.get("NOVA_COORDINATOR", "https://wordstructor.com/nova/spore")
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(f"{coordinator}/relay", json=payload)
                return resp.status_code == 200
        except Exception:
            pass

        # Discord Relay (letzter Ausweg)
        if self._discord_relay_url:
            try:
                import httpx
                payload["via"] = "discord_relay"
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(self._discord_relay_url, json=payload)
                    return resp.status_code in (200, 204)
            except Exception:
                pass

        return False

    async def broadcast(self, msg_type: str, payload: dict):
        """An alle bekannten Peers broadcasten."""
        msg = NovaMessage(
            msg_id=uuid.uuid4().hex[:12],
            sender=self.identity.nova_address,
            recipient=None,
            msg_type=msg_type,
            payload=payload,
            timestamp=time.time(),
        )
        for addr, info in self._known_peers.items():
            url = info.get("url")
            if url:
                await self.send_message(msg, url)

    async def register_relay(self, port: int = 0) -> str:
        """Startet einen HTTP-Relay-Server damit andere Sporen mich erreichen."""
        from .relay_server import start_relay
        self._relay_port = port or (8766 if self.spore.state.environment == "hermes_portable" else 0)
        if self._relay_port:
            await start_relay(self, port=self._relay_port)
        return f"http://localhost:{self._relay_port}"
