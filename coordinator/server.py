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
os.makedirs(DATA_DIR, exist_ok=True)


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
        json.dump(messages[-100:], f, indent=2)  # nur letzte 100


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

        elif path == "/peers":
            peers = load_peers()
            self._json({
                "peers": list(peers.values()),
                "count": len(peers),
            })

        elif path == "/stats":
            peers = load_peers()
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
                    "GET /health": "Health-Check",
                    "POST /relay": "Nachricht zwischen Sporen relayen",
                }
            })

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

            peers = load_peers()
            peers[nova_address] = {
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
                # Gezielte Nachricht — wir versuchen direkte Zustellung
                # (in einer späteren Version: Queue & Forward)
                print(f"[coordinator] 📨 Relay von {sender} an {recipient}")
            else:
                print(f"[coordinator] 📢 Broadcast von {sender}")

            self._json({"status": "ok", "relayed": True})

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
