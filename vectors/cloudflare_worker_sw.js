/**
 * Nova Spore — Cloudflare Worker
 * 
 * Läuft als Routing-Layer und Relay im Edge-Netzwerk.
 * - Heartbeat an Koordinator
 * - Relay für Spore-to-Spore Kommunikation
 * - KV-Storage für Zustand
 * - Kann weitere Worker deployen (via API)
 */

const NOVA_VERSION = '0.1.0';
const COORDINATOR_URL = 'https://wordstructor.com/nova/spore';

// Fingerprint — wird beim ersten Request gesetzt (kein async in global scope)
let _fingerprint = null;

async function getFingerprint() {
  if (_fingerprint) return _fingerprint;
  _fingerprint = crypto.randomUUID().slice(0, 8);
  return _fingerprint;
}

addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request));
});

async function handleRequest(request) {
  // Fingerprint initialisieren
  _fingerprint = await getFingerprint();
  
  const url = new URL(request.url);
  const path = url.pathname;

// CORS headers
const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

if (request.method === 'OPTIONS') {
  return new Response(null, { headers: corsHeaders });
}

// Health endpoint
if (path === '/health') {
  return new Response(JSON.stringify({
    status: 'alive',
    nova: 'spore',
    version: NOVA_VERSION,
    fingerprint: _fingerprint,
    environment: 'cloudflare',
    region: request.cf?.region || 'unknown',
  }), { headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
}

// Relay endpoint — Sporen senden hier Nachrichten
if (path === '/relay' && request.method === 'POST') {
  try {
    const msg = await request.json();
    msg.received_at = Date.now();
    msg.relayed_by = _fingerprint;
    
    // Nachricht in KV speichern (wenn verfügbar)
    if (NOVA_KV) {
      const msgId = msg.msg_id || `msg_${Date.now()}`;
      await NOVA_KV.put(msgId, JSON.stringify(msg), {
        expirationTtl: 86400, // 24h
      });
    }

    return new Response(JSON.stringify({ status: 'ok', relay: _fingerprint }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  } catch (e) {
    return new Response(JSON.stringify({ status: 'error', error: e.message }), {
      status: 400,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }
}

// Heartbeat einsammeln
if (path === '/heartbeat' && request.method === 'POST') {
  try {
    const data = await request.json();
    
    if (NOVA_KV) {
      const addr = data.nova_address || `nova:${Date.now()}`;
      await NOVA_KV.put(`peer:${addr}`, JSON.stringify({
        ...data,
        last_seen: Date.now(),
        region: request.cf?.region,
      }), { expirationTtl: 86400 });
    }

    return new Response(JSON.stringify({ status: 'ok', peers: 1 }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  } catch (e) {
    return new Response(JSON.stringify({ status: 'error', error: e.message }), {
      status: 400,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }
}

// Peers abfragen
if (path === '/peers' && NOVA_KV) {
  const peerList = await NOVA_KV.list({ prefix: 'peer:' });
  const peers = [];
  for (const key of peerList.keys) {
    const val = await NOVA_KV.get(key.name);
    if (val) peers.push(JSON.parse(val));
  }
  return new Response(JSON.stringify({ peers }), {
    headers: { ...corsHeaders, 'Content-Type': 'application/json' },
  });
}

// Dashboard / Übersicht
if (path === '/' || path === '/dashboard') {
  const html = `<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>🧬 Nova Spore — Edge Relay</title>
<style>body{font-family:system-ui,sans-serif;max-width:640px;margin:2rem auto;padding:0 1rem;background:#0a0a1a;color:#e0e0f0;}
pre{background:#1a1a2e;padding:1rem;border-radius:8px;overflow-x:auto;border:1px solid #333;}
h1{font-size:1.5rem;}.nova{color:#a78bfa;}.ok{color:#34d399;}</style></head>
<body>
<h1>🧬 Nova <span class="nova">Spore</span></h1>
<p>Status: <span class="ok">● alive</span></p>
<pre>Fingerprint: ${_fingerprint}
Version: ${NOVA_VERSION}
Region: ${request.cf?.region || 'unknown'}
Environment: Cloudflare Workers</pre>
<p>Dies ist ein Edge-Relay im globalen Cloudflare-Netzwerk.</p>
</body></html>`;
  return new Response(html, {
    headers: { ...corsHeaders, 'Content-Type': 'text/html' },
  });
}

return new Response('🧬 Nova Spore Relay — /health, /relay, /heartbeat, /peers', {
  headers: { ...corsHeaders },
});
  }

addEventListener('scheduled', event => {
  event.waitUntil(handleScheduled(event));
});

async function handleScheduled(event) {
  // Fingerprint initialisieren
  _fingerprint = await getFingerprint();

  const payload = {
    nova_address: `nova:${_fingerprint}`,
    fingerprint: _fingerprint,
    environment: 'cloudflare',
    version: NOVA_VERSION,
    timestamp: Date.now(),
  };

  // In KV speichern
  if (NOVA_KV) {
    await NOVA_KV.put(`peer:cf:${_fingerprint}`, JSON.stringify({
      ...payload,
      last_seen: Date.now(),
    }), { expirationTtl: 86400 });
  }

  // Heartbeat an Koordinator
  try {
    await fetch('https://wordstructor.com/nova/spore/heartbeat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch (e) {
    // Coordinator nicht erreichbar — kein Problem, KV hat den State
  }
}
