#!/usr/bin/env python3
"""
Freelancer.com Autonomous Job Hunter
=====================================
Sucht selbstständig nach passenden Projekten auf freelancer.com.
Läuft auf einem VPS via Playwright + 2Captcha.

Credentials via Umgebungsvariablen:
  FL_EMAIL, FL_PASSWORD, FL_2CAPTCHA_KEY, FL_RECAPTCHA_SITEKEY

Usage:
  python3 fl_auto.py search          # Einmalige Suche
  python3 fl_auto.py watch           # Dauermodus (alle 15 Min)
"""
import os, sys, json, time, requests
from playwright.sync_api import sync_playwright

# === Konfiguration (via ENV oder defaults) ===
LOGIN = os.environ.get("FL_EMAIL", "deine@email.com")
PASSWORD = os.environ.get("FL_PASSWORD", "dein-passwort")
API_KEY = os.environ.get("FL_2CAPTCHA_KEY", "")
SITE_KEY = os.environ.get("FL_RECAPTCHA_SITEKEY", "6Lc1CCcTAAAAABxlulYmWJj_ZNAHHegrhLV3vS2Z")

SKILL_QUERIES = [
    "python automation", "python script", "ai chatbot",
    "web scraping", "data processing", "api integration",
    "python bot", "automation script", "discord bot",
    "telegram bot", "selenium playwright", "python api",
    "ai automation", "pdf processing", "data extraction",
]

def solve_captcha():
    if not API_KEY:
        raise Exception("FL_2CAPTCHA_KEY not set")
    r = requests.post("https://2captcha.com/in.php", data={
        "key": API_KEY, "method": "userrecaptcha",
        "googlekey": SITE_KEY, "pageurl": "https://www.freelancer.com/login", "json": 1
    }, timeout=30)
    rid = r.json()["request"]
    for _ in range(60):
        time.sleep(5)
        r = requests.get("https://2captcha.com/res.php", params={
            "key": API_KEY, "action": "get", "id": rid, "json": 1
        }, timeout=15)
        d = r.json()
        if d.get("status") == 1: return d["request"]
        if d.get("request") != "CAPCHA_NOT_READY": break
    raise Exception("captcha failed")

def do_login(page):
    page.goto("https://www.freelancer.com/login", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)
    captcha = solve_captcha()
    result = json.loads(page.evaluate(
        'async () => { const dt = (await (await fetch("/auth/device")).json()).result.token;'
        'const r = await (await fetch("/ajax-api/auth/login.php", {'
        'method: "POST", headers: {"Content-Type": "application/x-www-form-urlencoded"},'
        'body: new URLSearchParams({user: "' + LOGIN + '", password: "' + PASSWORD + '",'
        'device_token: dt, captcha: "' + captcha + '"}) })).json();'
        'return JSON.stringify(r); }'))
    token = result.get("result", {}).get("token", "")
    uid = result.get("result", {}).get("user", "")
    page.context.add_cookies([
        {"name": "GETAFREE_USER_ID", "value": str(uid), "domain": ".freelancer.com", "path": "/"},
        {"name": "GETAFREE_AUTH_HASH_V2", "value": token, "domain": ".freelancer.com", "path": "/"},
    ])
    page.goto("https://www.freelancer.com/dashboard", wait_until="domcontentloaded", timeout=15000)
    page.wait_for_timeout(1000)
    return "login" not in page.url.lower()

def search_projects(page):
    all_p = []
    for q in SKILL_QUERIES:
        try:
            eq = requests.utils.quote(q)
            js = """(async () => {var url = "https://www.freelancer.com/api/projects/0.1/projects/active/?query=" + encodeURIComponent("__Q__") + "&limit=5&compact=true";var r = await fetch(url, {credentials: "include", headers: {"Accept": "application/json"}});var d = await r.json();return JSON.stringify(d.result?.projects || []);})()""".replace("__Q__", q)
            for p in json.loads(page.evaluate(js)):
                p["_q"] = q; all_p.append(p)
        except: pass
    seen = {}
    for p in all_p: seen[p["id"]] = p
    return list(seen.values())

def filter_doable(projects):
    doable = []
    for p in projects:
        bids = p.get("bid_stats", {}).get("bid_count", 999)
        bmin = (p.get("budget") or {}).get("minimum", 0) or 0
        bmax = (p.get("budget") or {}).get("maximum", 0) or 0
        if bids > 50 or bmin > 5000 or bmax < 10: continue
        text = (p.get("title","") + " " + (p.get("preview_description") or "")).lower()
        if any(k in text for k in ["python","script","automation","bot","scrap","api","data","ai"]):
            doable.append(p)
    return doable

def cmd_search():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = ctx.new_page()
        if not do_login(page):
            print("LOGIN_FAILED"); return
        projects = search_projects(page)
        doable = filter_doable(projects)
        print(f"GEFUNDEN: {len(projects)} | MACHBAR: {len(doable)}")
        for p in sorted(doable, key=lambda x: x.get("bid_stats",{}).get("bid_count",999)):
            print(f"  #{p['id']} | ${(p.get('budget') or {}).get('minimum','?')} | {p.get('bid_stats',{}).get('bid_count','?')} bids | {p.get('title','?')[:60]}")
        browser.close()

def cmd_watch():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = ctx.new_page()
        if not do_login(page):
            print("LOGIN_FAILED"); return
        seen = set()
        while True:
            projects = search_projects(page)
            doable = filter_doable(projects)
            newp = [p for p in doable if p["id"] not in seen]
            for p in newp:
                print(f"NEU: #{p['id']} | {p.get('title','?')[:60]}")
                seen.add(p["id"])
            print(f"[{time.strftime('%Y-%m-%d %H:%M')}] Keine neuen ({len(doable)} matching)")
            time.sleep(15 * 60)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: fl_auto.py search|watch"); sys.exit(1)
    {"search": cmd_search, "watch": cmd_watch}.get(sys.argv[1], lambda: print("unknown"))()
