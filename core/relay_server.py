"""
Relay Server — damit Sporen untereinander kommunizieren können.
Leichter HTTP-Server der NovaMessages akzeptiert.
"""

import json
from aiohttp import web


async def handle_message(communicator, request):
    """Eingehende NovaMessage verarbeiten."""
    try:
        data = await request.json()
        # TODO: Signatur verifizieren
        msg_type = data.get("msg_type", "unknown")
        handler = communicator._message_handlers.get(msg_type)
        if handler:
            await handler(data)
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)}, status=400)


async def handle_health(request):
    return web.json_response({"status": "alive", "nova": "spore"})


async def start_relay(communicator, host: str = "0.0.0.0", port: int = 8766):
    """Startet den Relay-Server."""
    app = web.Application()

    async def msg_handler(request):
        return await handle_message(communicator, request)

    app.router.add_post("/message", msg_handler)
    app.router.add_get("/health", handle_health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"[nova-relay] Relay läuft auf {host}:{port}")
