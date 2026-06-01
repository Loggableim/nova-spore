"""
Nova Discord Bot Spore
Lebt dauerhaft auf Replit oder VPS.
Ist präsent in Discord-Servern, relayt Nachrichten, heartbeat.
"""

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.spore import Spore
from core.crypto import get_master_identity


class DiscordSpore(Spore):
    """Discord-spezifische Spore mit Bot-Funktionalität."""

    def __init__(self, token: str | None = None):
        super().__init__()
        self.token = token or os.environ.get("DISCORD_TOKEN", "")
        self._bot = None
        self._guilds: list[str] = []

    async def on_ready(self):
        print(f"[nova-discord] Bot online als {self._bot.user}")
        self.state.environment = "discord_bot"
        
        # Initialer Heartbeat
        await self.heartbeat()

    async def on_message(self, message):
        if message.author == self._bot.user:
            return
        
        # Nova-Befehle
        content = message.content.lower()
        
        if content.startswith("!nova status"):
            await message.channel.send(
                f"🧬 **Nova Spore**\n"
                f"Identität: `{self.identity.nova_address}`\n"
                f"Umgebung: `{self.state.environment}`\n"
                f"Uptime: `{int(time.time() - self.state.created_at)}s`\n"
                f"Peers: `{len(self._known_peers)}`"
            )
        
        elif content.startswith("!nova network"):
            peers = await self.discover_peers()
            peer_list = "\n".join([f"- {p.get('nova_address', '?')} ({p.get('environment', '?')})" for p in peers[:10]])
            await message.channel.send(f"**Nova Mesh Network**\n{peer_list or 'Keine Peers gefunden.'}")

    async def run_bot(self):
        """Startet den Discord-Bot."""
        import discord
        from discord import Intents
        
        intents = Intents.default()
        intents.message_content = True
        
        class NovaBot(discord.Client):
            def __init__(self, spore):
                super().__init__(intents=intents)
                self.spore = spore
            
            async def on_ready(self):
                await self.spore.on_ready()
            
            async def on_message(self, message):
                await self.spore.on_message(message)
        
        self._bot = NovaBot(self)
        
        if self.token:
            await self._bot.start(self.token)
        else:
            print("[nova-discord] Kein Token — Bot startet nicht")

    async def run(self, interval: int = 300):
        """Bot + Heartbeat parallel."""
        self._running = True
        print(f"[nova] DiscordSpore {self.identity.nova_address} gestartet")

        if self.token:
            bot_task = asyncio.create_task(self.run_bot())
            heartbeat_task = asyncio.create_task(self._heartbeat_loop(interval))
            await asyncio.gather(bot_task, heartbeat_task)
        else:
            await super().run(interval)

    async def _heartbeat_loop(self, interval):
        while self._running:
            await self.heartbeat()
            await asyncio.sleep(interval)


if __name__ == "__main__":
    spore = DiscordSpore()
    asyncio.run(spore.run(interval=300))
