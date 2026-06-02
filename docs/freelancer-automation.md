# Freelancer.com Autonomous Job Hunter

Vollautomatisierte Jobsuche und -bewerbung auf Freelancer.com via Playwright + 2Captcha.
Findet selbstständig Projekte, filtert nach Machbarkeit, und kann auf die besten bieten.

## Features

- **Login-Automation:** Captcha-Lösung via 2Captcha, device-token, Auth-Cookie-Set
- **Skill-Suche:** 15 Kategorien (python, automation, scraping, ai, api, bots, ...)
- **Intelligentes Filtern:** Budget ($10–$5000), Wettbewerb (< 50 bids), Skill-Match
- **Report-System:** Ergebnisse mit Zeitstempel in `/tmp/fl_report_*.txt`
- **Cron-Installation:** Alle 4 Stunden via VPS-Cronjob
- **Bid-Bereitschaft:** API-Endpunkt bekannt, erfordert einmaligen Role-Switch auf freelancer

## API-Endpunkte (reverse-engineered)

| Endpoint | Methode | Zweck |
|----------|---------|-------|
| `/auth/device` | GET | Device-Token |
| `/api/projects/0.1/projects/active/?query=X&limit=N` | GET | Projektsuche |
| `/api/users/0.1/self` | GET | User-Profil |
| `/api/projects/0.1/bids/` | POST | Bid platzieren |
| `/ajax-api/auth/login.php` | POST | Login |

## Captcha

- **SiteKey:** `6Lc1CCcTAAAAABxlulYmWJj_ZNAHHegrhLV3vS2Z` (aus Angular flconfigs)
- **Hinweis:** Der im iframe sichtbare Key ist ein anderer — der richtige steht im JS-Bundle.

## Auth-Mechanismus

Nach erfolgreichem Login müssen **zwei Cookies** gesetzt werden:
- `GETAFREE_USER_ID` = User-ID (Integer)
- `GETAFREE_AUTH_HASH_V2` = Auth-Token (JWT-ähnlich)

API-Calls verwenden `credentials: "include"` im fetch().

## Installation (VPS)

```bash
# Python-Venv + Dependencies
python3 -m venv /tmp/playenv
source /tmp/playenv/bin/activate
pip install playwright requests
python3 -m playwright install chromium

# Script kopieren
cp templates/fl_auto.py /usr/local/bin/fl_auto.py
chmod +x /usr/local/bin/fl_auto.py
mkdir -p /etc/fl_auto

# Credentials-Konfiguration
cat > /etc/fl_auto/env.sh << 'EOF'
export FL_EMAIL="deine@email.com"
export FL_PASSWORD="dein-passwort"
export FL_2CAPTCHA_KEY="dein-2captcha-key"
export FL_RECAPTCHA_SITEKEY="6Lc1CCcTAAAAABxlulYmWJj_ZNAHHegrhLV3vS2Z"
EOF
chmod 600 /etc/fl_auto/env.sh

# Cronjob (alle 4h)
echo '0 */4 * * * . /etc/fl_auto/env.sh && /tmp/playenv/bin/python3 /usr/local/bin/fl_auto.py search > /tmp/fl_report_$(date +\\%Y\\%m\\%d_\\%H\\%M).txt 2>&1' | crontab -
```

## Manual Run

```bash
source /etc/fl_auto/env.sh
source /tmp/playenv/bin/activate
python3 /usr/local/bin/fl_auto.py search
```

## Role-Switch (einmalig nötig für Bidding)

Die Bid-API gibt 401, solange der Account im Employer-Modus ist.
Einmalig im echten Browser:
1. `freelancer.com` → einloggen
2. Navigation: **Browse** → **"I Want to Work"** klicken
3. Danach persistiert der Freelancer-Status

## Technische Details (Reverse Engineering)

Der Login-Mechanismus wurde durch Analyse des Angular-JS-Bundles (`main.67f2cdd44ca02d6c.js`) ermittelt:
- **authHashCookie:** `GETAFREE_AUTH_HASH_V2`
- **userIdCookie:** `GETAFREE_USER_ID`
- **csrfCookie:** `XSRF-TOKEN`
- **authHeaderName:** `freelancer-auth-v2`
- **recaptchaPublicKey (richtig):** aus `server-data/flconfigs` → `recaptchaPublicKey`

## Disk-Space Management (VPS mit 9.8GB)

```bash
rm -rf /tmp/tiroltourismus /root/.cache
apt-get clean
journalctl --vacuum-time=1d
```
