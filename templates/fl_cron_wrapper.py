#!/usr/bin/env python3
"""fl_cron_wrapper.py - Cron-Wrapper mit Zeitstempel-Logging"""
import subprocess, os
from datetime import datetime

ts = datetime.now().strftime("%Y%m%d_%H%M")
log_path = f"/tmp/fl_report_{ts}.txt"

# env aus /etc/fl_auto/env.sh laden
env = os.environ.copy()
if os.path.exists("/etc/fl_auto/env.sh"):
    with open("/etc/fl_auto/env.sh") as f:
        for line in f:
            if line.strip() and not line.startswith("#") and "=" in line:
                k, v = line.strip().split("=", 1)
                env[k] = v.strip('"')

result = subprocess.run(
    ["/tmp/playenv/bin/python3", "/usr/local/bin/fl_auto.py", "search"],
    capture_output=True, text=True, timeout=360, env=env
)

with open(log_path, "w") as f:
    f.write(f"=== Freelancer Report {ts} ===\n")
    f.write(result.stdout)
    if result.stderr:
        f.write(f"\n--- STDERR ---\n{result.stderr}")

print(f"Report: {log_path}")
