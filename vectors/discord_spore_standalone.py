"""
Nova Discord Bot Spore — Standalone Version für VPS.
Heartbeat, Kommandos, Relay — alles in einer Datei.
"""

import asyncio
import json
import os
import sys
import time
import uuid

import discord
from discord import Intents

# === Config ===
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "")
NOVA_COORDINATOR = os.environ.get("NOVA_COORDINATOR", "https://wordstructor.com/nova/spore")
HEARTBEAT_INTERVAL = 300  # 5 Minuten

FINGERPRINT = uuid.uuid4().hex[:12]
NOVA_ADDRESS = f"nova:discord_{FINGERPRINT}"

# === HTTP helpers ===
import httpx

async def heartbeat():
    """Heartbeat an den Koordinator."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{NOVA_COORDINATOR}/heartbeat", json={
                "nova_address": NOVA_ADDRESS,
                "fingerprint": FINGERPRINT,
                "environment": "discord_bot",
                "timestamp": time.time(),
            })
            data = resp.json()
            print(f"[nova-discord] ❤ Heartbeat: {resp.status_code} — {data.get('total_peers', '?')} Peers")
    except Exception as e:
        print(f"[nova-discord] Heartbeat failed: {e}")


async def poll_tasks():
    """Tasks vom Koordinator abholen."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{NOVA_COORDINATOR}/tasks/poll", json={
                "nova_address": NOVA_ADDRESS,
            })
            tasks = resp.json().get("tasks", [])
            if tasks:
                print(f"[nova-discord] 📋 {len(tasks)} neue Tasks")
            return tasks
    except Exception:
        return []


# === Discord Bot ===
class NovaDiscordBot(discord.Client):
    def __init__(self):
        intents = Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.start_time = time.time()

    async def on_ready(self):
        print(f"[nova-discord] ✅ Bot online als {self.user} (ID: {self.user.id})")
        print(f"[nova-discord] 🌐 Koordinator: {NOVA_COORDINATOR}")
        
        # Initialer Heartbeat
        await heartbeat()
        
        # Heartbeat-Loop starten
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self.task_poll_task = asyncio.create_task(self._task_poll_loop())

    async def on_message(self, message):
        if message.author == self.user:
            return

        content = message.content.strip()

        if content.startswith("!nova"):
            await self._handle_nova_command(message, content)

    async def _handle_nova_command(self, message, content):
        parts = content.split()
        if len(parts) < 2:
            await message.channel.send(
                f"🧬 **Nova Spore**\n"
                f"`{NOVA_ADDRESS}`\n"
                f"Verfügbar: `status`, `network`, `ping`"
            )
            return

        cmd = parts[1].lower()

        if cmd == "status":
            uptime = int(time.time() - self.start_time)
            await message.channel.send(
                f"🧬 **Nova Spore**\n"
                f"Identität: `{NOVA_ADDRESS}`\n"
                f"Uptime: `{uptime}s`\n"
                f"Koordinator: `{NOVA_COORDINATOR}`"
            )

        elif cmd == "network":
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(f"{NOVA_COORDINATOR}/stats")
                    stats = resp.json()
                envs = "\n".join([f"  • {k}: {v}" for k, v in stats.get("environments", {}).items()])
                await message.channel.send(
                    f"🌐 **Nova Mesh Network**\n"
                    f"Total Peers: `{stats.get('total_peers', '?')}`\n"
                    f"Umgebungen:\n{envs}"
                )
            except Exception as e:
                await message.channel.send(f"❌ Fehler: `{e}`")

        elif cmd == "ping":
            await message.channel.send("🏓 Pong!")

        elif cmd == "help":
            await message.channel.send(
                "🧬 **Nova Commands**\n"
                "`!nova status` — Bot-Status\n"
                "`!nova network` — Mesh-Statistiken\n"
                "`!nova ping` — Ping\n"
                "`!nova help` — Diese Hilfe"
            )

    async def _heartbeat_loop(self):
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            await heartbeat()

    async def _task_poll_loop(self):
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL // 2)
            tasks = await poll_tasks()
            for task in tasks:
                print(f"[nova-discord] Task: {task.get('type')} — {task.get('payload', {})}")


async def main():
    print(f"🧬 Nova Discord Spore v0.1.0")
    print(f"   Adresse: {NOVA_ADDRESS}")
    print(f"   Koordinator: {NOVA_COORDINATOR}")
    print(f"   Heartbeat alle {HEARTBEAT_INTERVAL}s")

    if not DISCORD_TOKEN or DISCORD_TOKEN == "YOUR_TOKEN_HERE":
        print("[nova-discord] ❌ Kein DISCORD_TOKEN gesetzt")
        return

    bot = NovaDiscordBot()
    await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
