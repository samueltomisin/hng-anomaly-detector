# 🛡️ HNG Anomaly Detection Engine

> A real-time DDoS detection and auto-blocking daemon built for HNG's cloud.ng Nextcloud platform. It watches every HTTP request, learns what normal traffic looks like, and fights back automatically when something looks wrong — no human needed.

---

## 🌐 Live URLs

| What | Where |
|---|---|
| 📊 Live Metrics Dashboard | http://anormallydashboard.duckdns.org:8080 |
| ☁️ Nextcloud (IP access only) | http://54.242.77.202 |
| 💻 GitHub Repository | https://github.com/samueltomisin/hng-anomaly-detector |

---

## 🧠 What Does This Thing Actually Do?

Imagine you're running a busy cloud storage platform. Thousands of users access it daily. Then suddenly, one attacker starts hammering your server with thousands of requests per second — a classic DDoS attack.

Without protection, your server slows down, legitimate users can't access their files, and your platform goes down.

This tool sits quietly in the background, watching every single HTTP request that hits your server. It learns what "normal" looks like. The moment something deviates — whether it's one aggressive IP or a global traffic spike — it reacts:

- 🚨 Blocks the attacker at the firewall level using `iptables`
- 📢 Sends an instant Slack alert with full details
- 📊 Updates the live dashboard in real time
- ⏱️ Automatically releases the ban on a backoff schedule
- 📝 Logs every action to a structured audit trail

All of this happens within **10 seconds** of detection. Automatically. While you sleep.

---

## 🏗️ Architecture Overview

Here's how all the pieces fit together:
>
> Internet Traffic
│
▼
[ Nginx ]  ←── Reverse proxy, writes JSON logs
│
├──── proxies requests to ──── [ Nextcloud ]
│
└──── writes logs to ──── [ HNG-nginx-logs Volume ]
│
▼
[ Detector Daemon ]
┌─────────────────┐
│  monitor.py      │ ← tails the log file
│  baseline.py     │ ← learns normal traffic
│  detector.py     │ ← spots anomalies
│  blocker.py      │ ← fires iptables
│  unbanner.py     │ ← releases bans
│  notifier.py     │ ← pings Slack
│  dashboard.py    │ ← serves live UI
└─────────────────┘
│        │
iptables    Slack alerts
DROP rule   + Dashboard
> ---

## 🗂️ Repository Structure
> hng-anomaly-detector/
│
├── detector/
│   ├── main.py          # The brain — ties everything together
│   ├── monitor.py       # Tails and parses the Nginx log file
│   ├── baseline.py      # Learns what normal traffic looks like
│   ├── detector.py      # Decides when something is anomalous
│   ├── blocker.py       # Adds and removes iptables rules
│   ├── unbanner.py      # Manages the auto-unban schedule
│   ├── notifier.py      # Sends Slack alerts
│   ├── dashboard.py     # Serves the live metrics web UI
│   ├── config.yaml      # All thresholds and settings live here
│   └── requirements.txt # Python dependencies
│
├── nginx/
│   └── nginx.conf       # Reverse proxy + JSON logging config
│
├── docs/
│   └── architecture.png
│
├── screenshots/         # All 7 required screenshots
├── docker-compose.yml   # Spins up the entire stack
└── README.md
> ---

## ⚙️ How the Sliding Window Works
Think of the sliding window like a rolling conveyor belt — it only ever holds the **last 60 seconds** of requests, and old ones fall off the back automatically.

Under the hood, we use Python's `deque` (double-ended queue) data structure. Every time a request comes in, we append its timestamp to the deque. Before calculating the rate, we evict any timestamps older than 60 seconds from the left side:

```python
```pythont(self, window):
def _evict(self, window):- self.window_seconds  # 60 seconds ago
    cutoff = time.time() - self.window_seconds  # 60 seconds ago
    while window and window[0] < cutoff: old ones
        window.popleft()  # kick out the old ones
```

The current request rate is then simply:

```python
```pythonn(window) / 60  # requests per second
rate = len(window) / 60  # requests per second
```
We maintain **two** of these windows simultaneously:
- One **per IP** — to catch a single aggressive attackerny IPs at once
- One **global** — to catch a distributed attack from many IPs at once
---

## 📈 How the Baseline Learns
The baseline is how the system knows what "normal" looks like. Without it, we'd have no reference point; we wouldn't know if 50 req/s is normal or suspicious.

Here's how it works:

1. Every second, we record how many requests arrived that secondunts
2. We keep a **rolling 30-minute window** of these per-second counts*standard deviation** (how much traffic usually varies)
3. Every **60 seconds**, we recalculate the **mean** (average) and **standard deviation** (how much traffic usually varies) is near zero
4. We set a **floor** of `1.0` for mean and `0.5` for stddev — this prevents false alarms during quiet periods when traffic is near zero
The result is a baseline that **adapts to your actual traffic** — busy hours get a higher baseline, quiet hours get a lower one. It's never hardcoded.

---

## 🚨 How Anomaly Detection Makes a Decision

Once we have the current rate and the baseline, the detector runs two checks — whichever fires first triggers the response:

**Check 1 — Z-score** (is this statistically unusual?)
> z = (current_rate - baseline_mean) / baseline_stddev
If z > 3.0 → ANOMALY
> A z-score of 3.0 means the current rate is 3 standard deviations above normal — statistically, that happens less than 0.3% of the time by chance. So if it's firing, something is almost certainly wrong.

**Check 2 — Rate multiplier** (is this just way too fast?)
> A z-score of 3.0 means the current rate is 3 standard deviations above normal — statistically, that happens less than 0.3% of the time by chance. So if it's firing, something is almost certainly wrong.

**Bonus — Error surge tightening:**
If an IP is already sending lots of 4xx/5xx errors (3x the normal error rate), we tighten its z-score threshold from `3.0` down to `1.8` — we become more suspicious of it automatically.

---

## 🔨 How iptables Blocks an IP

`iptables` is Linux's built-in firewall. When the detector flags an IP as malicious, it runs this command:

```bash
iptables -I INPUT -s ATTACKER_IP -j DROP
```

Breaking that down:
- `-I INPUT` — insert a rule at the top of the INPUT chain (all incoming traffic)
- `-s ATTACKER_IP` — match traffic from this specific IP address
- `-j DROP` — silently drop the packet — the attacker gets no response at all

The attacker's requests never even reach Nginx or Nextcloud. They're stopped at the kernel level — the lowest possible layer.

When the ban expires, the rule is removed:

```bash
iptables -D INPUT -s ATTACKER_IP -j DROP
```

---

## ⏱️ Auto-Unban Schedule

Bans don't last forever — unless you really deserve it:

| Offense | Ban Duration |
|---|---|
| 1st offence | 10 minutes |
| 2nd offence | 30 minutes |
| 3rd offence | 2 hours |
| 4th offence+ | Permanent |

A Slack notification is sent every time an IP is unbanned.

---

Every ban, unban, and baseline recalculation is recorded in this format:URL"
> [2026-04-28T10:00:00Z] BAN 1.2.3.4 | z-score=5.23 | rate=8.3200 | baseline=1.0000 | duration=600
[2026-04-28T10:10:00Z] UNBAN 1.2.3.4 | offense #1 | released
[2026-04-28T10:01:00Z] BASELINE_RECALC | mean=1.2400 | stddev=0.5000
> ---

## 📝 Blog Post

Read the full beginner-friendly breakdown of how this was built:

👉 [YOUR BLOG URL HERE]

---

## 📸 Screenshots

All 7 required screenshots are in the `/screenshots` directory:

| File | What it shows |
|---|---|
| `Tool-running.png` | Daemon running, processing log lines |
| `Ban-slack.png` | Slack ban notification |
| `Unban-slack.png` | Slack unban notification |
| `Global-alert-slack.png` | Slack global anomaly alert |
| `Iptables-banned.png` | iptables -L showing blocked IP |
| `Audit-log.png` | Structured audit log entries |
| `Baseline-graph.png` | Baseline over time with two hourly slots |

---

## 🛠️ Built With

- **Python 3.11** — daemon, detection logic, dashboard
- **Docker & Docker Compose** — container orchestration
- **Nginx** — reverse proxy and JSON access logging
- **iptables** — kernel-level IP blocking
- **Slack Webhooks** — real-time alerting
- **psutil** — CPU and memory monitoring

---

*Built for HNG Internship Stage 3