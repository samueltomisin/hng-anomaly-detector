
import json, time, yaml, os, logging, threading, sys
from collections import defaultdict
from monitor import tail_log
from baseline import BaselineTracker
from detector import AnomalyDetector
from blocker import block_ip
from unbanner import UnbanManager
import notifier
from dashboard import start_dashboard, state

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)

# ── Load config ──
with open('config.yaml') as f:
    config = yaml.safe_load(f)

# ── Slack webhook from env or config ──
notifier.WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL', config.get('slack_webhook_url', ''))

# ── Audit log ──
os.makedirs('/var/log/detector', exist_ok=True)
logging.basicConfig(
    filename=config['audit_log_path'],
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%SZ'
)

# ── Core components ──
baseline = BaselineTracker(
    window_minutes=config['baseline_window_minutes'],
    recalc_interval=config['baseline_recalc_interval_seconds']
)
detector = AnomalyDetector(config, baseline)
unbanner = UnbanManager()

# ── Start dashboard ──
start_dashboard(config.get('dashboard_port', 8080))

# ── Per-second counter ──
second_counts = defaultdict(int)
second_lock = threading.Lock()

def count_flusher():
    while True:
        time.sleep(1)
        with second_lock:
            counts = dict(second_counts)
            second_counts.clear()
        total = sum(counts.values())
        baseline.record(time.time(), total)

        state['global_rps'] = detector.get_global_rate()
        state['baseline_mean'] = baseline.mean
        state['baseline_stddev'] = baseline.stddev
        state['banned_ips'] = unbanner.get_banned()

        ip_rates = [(ip, detector.get_ip_rate(ip)) for ip in list(detector.ip_windows.keys())]
        state['top_ips'] = sorted(ip_rates, key=lambda x: -x[1])[:10]

        if baseline.mean > 1.0:
            logging.info(f"BASELINE_RECALC | mean={baseline.mean:.4f} | stddev={baseline.stddev:.4f}")

threading.Thread(target=count_flusher, daemon=True).start()

# ── Alert cooldown tracker ──
recently_alerted = set()
alert_lock = threading.Lock()

def cooldown_clear(key, delay):
    time.sleep(delay)
    with alert_lock:
        recently_alerted.discard(key)

print("==> Detector running. Watching logs...", flush=True)
print(f"==> Log path: {config['log_path']}", flush=True)
print(f"==> Slack webhook set: {bool(notifier.WEBHOOK_URL)}", flush=True)

line_count = 0

# ── Main loop ──
for line in tail_log(config['log_path']):
    line_count += 1
    print(f"==> Line #{line_count}: {line[:80]}", flush=True)

    try:
        entry = json.loads(line)
        raw_ip = entry.get('source_ip', '') or ''
        ip = raw_ip.split(',')[0].strip()
        status = int(entry.get('status', 200))

        if not ip or ip == '-':
            ip = '0.0.0.0'

        print(f"==> Parsed: ip={ip} status={status}", flush=True)

        detector.record_request(ip, time.time(), status)
        with second_lock:
            second_counts[ip] += 1

        # ── Per-IP anomaly check ──
        if not unbanner.is_banned(ip):
            is_anomalous, reason = detector.check_ip(ip)
            with alert_lock:
                already = ip in recently_alerted
            if is_anomalous and not already:
                rate = detector.get_ip_rate(ip)
                block_ip(ip)
                duration = unbanner.ban(ip, reason, rate, baseline.mean)
                notifier.alert_ban(ip, reason, rate, baseline.mean, duration)
                logging.info(
                    f"BAN {ip} | {reason} | "
                    f"rate={rate:.4f} | baseline={baseline.mean:.4f} | "
                    f"duration={duration}"
                )
                print(f"[BAN] {ip} | {reason}", flush=True)
                with alert_lock:
                    recently_alerted.add(ip)
                threading.Thread(target=cooldown_clear, args=[ip, 30], daemon=True).start()

        # ── Global anomaly check ──
        is_global, global_reason = detector.check_global()
        with alert_lock:
            global_alerted = 'GLOBAL' in recently_alerted
        if is_global and not global_alerted:
            rate = detector.get_global_rate()
            notifier.alert_global(global_reason, rate, baseline.mean)
            logging.info(
                f"GLOBAL_ANOMALY | {global_reason} | "
                f"rate={rate:.4f} | baseline={baseline.mean:.4f}"
            )
            print(f"[GLOBAL] {global_reason}", flush=True)
            with alert_lock:
                recently_alerted.add('GLOBAL')
            threading.Thread(target=cooldown_clear, args=['GLOBAL', 60], daemon=True).start()

    except (json.JSONDecodeError, ValueError, KeyError) as e:
        print(f"==> Parse error: {e} | line: {line[:80]}", flush=True)
        continue
