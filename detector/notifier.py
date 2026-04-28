import requests
from datetime import datetime

WEBHOOK_URL = ""

def send_slack(message: str):
    if not WEBHOOK_URL:
        print(f"[SLACK - no webhook set] {message}", flush=True)
        return
    try:
        requests.post(WEBHOOK_URL, json={"text": message}, timeout=5)
    except Exception as e:
        print(f"Slack error: {e}", flush=True)

def alert_ban(ip, condition, rate, baseline, duration_seconds):
    duration_str = f"{duration_seconds//60} min" if duration_seconds else "PERMANENT"
    msg = (
        f":rotating_light: *BAN* | IP: `{ip}`\n"
        f"Condition: {condition}\n"
        f"Rate: `{rate:.2f} req/s` | Baseline: `{baseline:.2f} req/s`\n"
        f"Duration: {duration_str} | Time: {datetime.utcnow().isoformat()}Z"
    )
    send_slack(msg)

def alert_unban(ip, offense_count):
    msg = (
        f":large_green_circle: *UNBAN* | IP: `{ip}`\n"
        f"Offense #{offense_count} served | Released from block\n"
        f"Time: {datetime.utcnow().isoformat()}Z"
    )
    send_slack(msg)

def alert_global(condition, rate, baseline):
    msg = (
        f":warning: *GLOBAL ANOMALY DETECTED*\n"
        f"Condition: {condition}\n"
        f"Rate: `{rate:.2f} req/s` | Baseline: `{baseline:.2f} req/s`\n"
        f"Time: {datetime.utcnow().isoformat()}Z"
    )
    send_slack(msg)
