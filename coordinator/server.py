"""
Nova Spore Coordinator — VPS Heartbeat & Relay Server.

Empfängt Heartbeats von allen Sporen.
Verwaltet Peer-Registry.
Relayt Nachrichten zwischen Sporen.
"""

import json
import os
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse


DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
PEERS_FILE = os.path.join(DATA_DIR, "peers.json")
MESSAGES_FILE = os.path.join(DATA_DIR, "messages.json")
TASKS_FILE = os.path.join(DATA_DIR, "tasks.json")
os.makedirs(DATA_DIR, exist_ok=True)

# Decay: peer gilt als tot nach N Sekunden ohne Heartbeat
DECAY_TIMEOUTS = {
    "github_actions": 86400,      # 24h — CI läuft nur alle 12h
    "cloudflare": 3600,           # 1h — Edge Worker
    "discord_bot": 300,           # 5min — persistent
    "replit": 600,                # 10min
    "colab": 1800,                # 30min
    "kaggle": 1800,               # 30min
    "nova_vm": 300,               # 5min
    "hermes_portable": 120,       # 2min
    "docker": 600,                # 10min
    "unknown": 36000,             # 10h
    "test": 360000,               # 100h — Testeinträge
}
DEFAULT_DECAY = 7200  # 2h Fallback


def load_peers():
    try:
        with open(PEERS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_peers(peers):
    with open(PEERS_FILE, "w") as f:
        json.dump(peers, f, indent=2)


def load_messages():
    try:
        with open(MESSAGES_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_messages(messages):
    with open(MESSAGES_FILE, "w") as f:
        json.dump(messages[-100:], f, indent=2)


def load_tasks():
    try:
        with open(TASKS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_tasks(tasks):
    with open(TASKS_FILE, "w") as f:
        json.dump(tasks, f, indent=2)


def decay_peers(peers):
    """Entfernt Peers deren Heartbeat zu alt ist."""
    now = time.time()
    alive = {}
    dead = 0
    for peer_id, peer in peers.items():
        last_seen = peer.get("last_seen", 0)
        env = peer.get("environment", "unknown")
        timeout = DECAY_TIMEOUTS.get(env, DEFAULT_DECAY)
        if now - last_seen < timeout:
            alive[peer_id] = peer
        else:
            dead += 1
    if dead > 0:
        print(f"[coordinator] 🧹 {dead} Peers decayed")
    return alive  # nur letzte 100


class CoordinatorHandler(BaseHTTPRequestHandler):

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _json(self, data, status=200):
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _text(self, text, status=200):
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(text.encode())

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/health":
            self._json({
                "status": "alive",
                "nova": "coordinator",
                "version": "0.1.0",
                "uptime": time.time() - self.server.start_time,
            })

        if path == "/peers":
            peers = load_peers()
            peers = decay_peers(peers)
            save_peers(peers)
            self._json({
                "peers": list(peers.values()),
                "count": len(peers),
            })

        elif path == "/stats":
            peers = load_peers()
            peers = decay_peers(peers)
            save_peers(peers)
            envs = {}
            for p in peers.values():
                env = p.get("environment", "unknown")
                envs[env] = envs.get(env, 0) + 1
            self._json({
                "total_peers": len(peers),
                "environments": envs,
                "uptime": time.time() - self.server.start_time,
            })

        elif path in ("", "/"):
            self._json({
                "nova": "spore-coordinator",
                "version": "0.1.0",
                "endpoints": {
                    "POST /heartbeat": "Spore-Heartbeat empfangen",
                    "GET /peers": "Alle aktiven Peers",
                    "GET /stats": "Statistiken",
                    "GET /tasks": "Alle Tasks anzeigen",
                    "POST /tasks": "Neuen Task erstellen",
                    "POST /tasks/poll": "Spore pollt Tasks",
                    "POST /tasks/complete": "Task-Ergebnis melden",
                    "GET /health": "Health-Check",
                    "POST /relay": "Nachricht zwischen Sporen relayen",
                }
            })

        elif path == "/tasks":
            tasks = load_tasks()
            self._json({"tasks": tasks, "count": len(tasks)})

        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b"{}"

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._json({"error": "invalid JSON"}, 400)
            return

        if path == "/heartbeat":
            nova_address = data.get("nova_address", "unknown")
            fingerprint = data.get("fingerprint", "unknown")
            environment = data.get("environment", "unknown")

            # Eindeutige Peer-ID: Adresse + Umgebung
            env = environment or "unknown"
            peer_id = f"{nova_address}@{env}"

            peers = load_peers()
            peers[peer_id] = {
                **data,
                "last_seen": time.time(),
                "ip": self.client_address[0],
            }
            save_peers(peers)

            print(f"[coordinator] ❤ Heartbeat von {nova_address} ({environment})")
            self._json({
                "status": "ok",
                "total_peers": len(peers),
                "your_address": nova_address,
            })

        elif path == "/relay":
            msg_id = data.get("msg_id", "unknown")
            sender = data.get("sender", "unknown")
            recipient = data.get("recipient")

            # Speichern
            msgs = load_messages()
            msgs.append({
                **data,
                "received_at": time.time(),
            })
            save_messages(msgs)

            if recipient:
                print(f"[coordinator] 📨 Relay von {sender} an {recipient}")
            else:
                print(f"[coordinator] 📢 Broadcast von {sender}")

            self._json({"status": "ok", "relayed": True})

        elif path == "/tasks":
            # Neuen Task erstellen (vom Koordinator/Admin)
            target = data.get("target", "")
            task_type = data.get("type", "unknown")
            payload = data.get("payload", {})

            task = {
                "id": str(int(time.time() * 1000))[-12:],
                "type": task_type,
                "payload": payload,
                "target": target,  # "" = broadcast
                "created_at": time.time(),
                "status": "pending",
                "assigned_to": None,
                "result": None,
            }

            tasks = load_tasks()
            tasks.append(task)
            save_tasks(tasks)
            print(f"[coordinator] 📋 Task {task['id']} erstellt: {task_type}")
            self._json({"status": "ok", "task": task})

        elif path == "/tasks/poll":
            # Spore pollt nach Tasks für sich
            nova_address = data.get("nova_address", "")
            if not nova_address:
                self._json({"error": "nova_address required"}, 400)
                return

            tasks = load_tasks()
            # Tasks finden die für diese Spore sind (target = address oder "")
            my_tasks = []
            remaining = []
            for t in tasks:
                if t["status"] == "pending" and (t["target"] == "" or t["target"] == nova_address):
                    t["status"] = "assigned"
                    t["assigned_to"] = nova_address
                    t["assigned_at"] = time.time()
                    my_tasks.append(t)
                remaining.append(t)
            save_tasks(remaining + my_tasks)

            self._json({"tasks": my_tasks})

        elif path == "/tasks/complete":
            # Spore meldet Task-Ergebnis
            task_id = data.get("task_id", "")
            result = data.get("result", {})
            nova_address = data.get("nova_address", "")

            tasks = load_tasks()
            for t in tasks:
                if t["id"] == task_id and t.get("assigned_to") == nova_address:
                    t["status"] = "completed"
                    t["result"] = result
                    t["completed_at"] = time.time()
                    break

            save_tasks(tasks)
            self._json({"status": "ok"})

        else:
            self._json({"error": "not found"}, 404)


class ThreadedHTTPServer(HTTPServer):
    allow_reuse_address = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_time = time.time()


def main():
    port = int(os.environ.get("COORDINATOR_PORT", 3457))
    server = ThreadedHTTPServer(("0.0.0.0", port), CoordinatorHandler)
    print(f"🧬 Nova Coordinator läuft auf Port {port}")
    print(f"   Heartbeat:  POST /heartbeat")
    print(f"   Peers:      GET /peers")
    print(f"   Relay:      POST /relay")
    print(f"   Stats:      GET /stats")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[coordinator] Shutdown")
        server.server_close()


if __name__ == "__main__":
    main()
