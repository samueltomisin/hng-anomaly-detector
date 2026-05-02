# 🛡️ HNG Anomaly Detection Engine

A real-time DDoS detection and auto-blocking daemon built for HNG's cloud.ng Nextcloud platform. It watches every HTTP request, learns what normal traffic looks like, and fights back automatically when something looks wrong, no human needed.

---

## 🌐 Live URLs

| What | Where |
|---|---|
| 📊 Live Metrics Dashboard | http://anormallydashboard.duckdns.org:8080 |
| ☁️ Nextcloud (IP access only) | http://http://34.228.27.80/:8080 |
| 💻 GitHub Repository | https://github.com/samueltomisin/hng-anomaly-detector |

---

## 🧠 What Does This Thing Actually Do?

Imagine you're running a busy cloud storage platform. Thousands of users access it daily. Then suddenly, one attacker starts hammering your server with thousands of requests per second; a classic DDoS attack.

Without protection, your server slows down, legitimate users can't access their files, and your platform goes down.

This tool sits quietly in the background, watching every single HTTP request that hits your server. It learns what "normal" looks like. The moment something deviates; whether it's one aggressive IP or a global traffic spike, it reacts:

- 🚨 Blocks the attacker at the firewall level using `iptables`
- 📢 Sends an instant Slack alert with full details
- 📊 Updates the live dashboard in real time
- ⏱️ Automatically releases the ban on a backoff schedule
- 📝 Logs every action to a structured audit trail

All of this happens within **10 seconds** of detection. Automatically. While you sleep.

---

## 🏗️ Architecture Overview

Here's how all the pieces fit together:

The system is made up of four main layers that work together seamlessly.

**Layer 1 : Traffic Entry**

All incoming HTTP traffic from the internet hits **Nginx** first. Nginx acts as a reverse proxy; it forwards legitimate requests to Nextcloud and simultaneously writes a structured JSON log entry for every single request to a shared Docker volume called `HNG-nginx-logs`.

**Layer 2 : The Application**

**Nextcloud** sits behind Nginx and never directly faces the internet. It handles all the actual cloud storage functionality. It mounts the log volume read-only, just as the task requires.

**Layer 3 : The Detector Daemon**

This is the heart of the system. The detector mounts the same `HNG-nginx-logs` volume and tails the log file in real time. It is made up of seven modules, each with a single responsibility:

- `monitor.py` reads every new log line as it arrives
- `baseline.py` maintains a rolling 30-minute picture of normal traffic
- `detector.py` compares current traffic against the baseline and raises the alarm
- `blocker.py` executes the iptables firewall rule to drop the attacker
- `unbanner.py` manages the automatic release of bans on a backoff schedule
- `notifier.py` sends formatted alerts to Slack
- `dashboard.py` serves the live metrics web UI on port 8080

**Layer 4 : Outputs**

Three things come out of the detector when an anomaly is confirmed. An `iptables DROP` rule that stops the attacker at the kernel level, a `Slack alert` with full context, and an `updated live dashboard`. Every action is also written to a structured audit log.

---


## 🗂️ Repository Structure
```
hng-anomaly-detector/
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
```
---

## 🐍 Language Choice: Why Python?

Python was chosen for three practical reasons:

**1. Built-in tools for everything we needed**

Python's standard library includes `threading` (for running the dashboard and unban timers concurrently), `http.server` (for serving the dashboard without a framework), `subprocess` (for running iptables commands), and `collections.deque` (for the sliding window). No heavy dependencies needed.

**2. Readable systems code**

A daemon that other engineers need to read and maintain should be easy to follow. Python's syntax is close to plain English  `window.popleft()` tells you exactly what it does. This matters in a security tool where clarity reduces the chance of bugs.

**3. Fast to iterate and debug**

The detector went through several debugging cycles (buffering issues, missing methods, path errors). Python's error messages are specific and point directly to the problem. This made fixing issues faster. 

---

## ⚙️ How the Sliding Window Works
Think of the sliding window like a rolling conveyor belt, it only ever holds the **last 60 seconds** of requests, and old ones fall off the back automatically.

Under the hood, we use Python's `deque` (double-ended queue) data structure. Every time a request comes in, we append its timestamp to the deque. Before calculating the rate, we evict any timestamps older than 60 seconds from the left side:

```python
def _evict(self, window):- self.window_seconds  # 60 seconds ago
    cutoff = time.time() - self.window_seconds  # 60 seconds ago
    while window and window[0] < cutoff: old ones
        window.popleft()  # kick out the old ones
```

The current request rate is then simply:

```python
rate = len(window) / 60  # requests per second
```
We maintain **two** of these windows simultaneously:
- One **per IP** : to catch a single aggressive attackerny IPs at once
- One **global** : to catch a distributed attack from many IPs at once
---

## 📈 How the Baseline Learns
The baseline is how the system knows what "normal" looks like. Without it, we'd have no reference point; we wouldn't know if 50 req/s is normal or suspicious.

Here's how it works:

1. Every second, we record how many requests arrived that secondunts
2. We keep a **rolling 30-minute window** of these per-second counts **standard deviation** (how much traffic usually varies)
3. Every **60 seconds**, we recalculate the **mean** (average) and **standard deviation** (how much traffic usually varies) is near zero
4. We set a **floor** of `1.0` for mean and `0.5` for stddev this prevents false alarms during quiet periods when traffic is near zero
The result is a baseline that **adapts to your actual traffic** busy hours get a higher baseline, quiet hours get a lower one. It's never hardcoded.

---

## 🚨 How Anomaly Detection Makes a Decision

Once we have the current rate and the baseline, the detector runs two checks whichever fires first triggers the response:

**Check 1 : Z-score** (is this statistically unusual?)

`z = (current_rate - baseline_mean) / baseline_stddev`

`If z > 3.0 → ANOMALY`

**A z-score of 3.0 means the current rate is 3 standard deviations above normal statistically, that happens less than 0.3% of the time by chance. So if it's firing, something is almost certainly wrong.**

**Check 2 : Rate multiplier** (is this just way too fast?)

`If current_rate > baseline_mean × 5 → ANOMALY`

**This catches sudden spikes even before the baseline has enough data to produce a reliable z-score.**

**Bonus : Error surge tightening:**
If an IP is already sending lots of 4xx/5xx errors (3x the normal error rate), we tighten its z-score threshold from `3.0` down to `1.8`  we become more suspicious of it automatically.

---

## 🔨 How iptables Blocks an IP

`iptables` is Linux's built-in firewall. When the detector flags an IP as malicious, it runs this command:

```bash
iptables -I INPUT -s ATTACKER_IP -j DROP
```

Breaking that down:
- `-I INPUT` : insert a rule at the top of the INPUT chain (all incoming traffic)
- `-s ATTACKER_IP` : match traffic from this specific IP address
- `-j DROP` : silently drop the packet — the attacker gets no response at all

The attacker's requests never even reach Nginx or Nextcloud. They're stopped at the kernel level (the lowest possible layer).

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

## 🚀 Setup Instructions (Fresh VPS)

Follow these steps exactly to go from a blank server to a fully running stack.

### Step 1: Provision Your Server

You need a Linux VPS with:
- Minimum 2 vCPU, 2 GB RAM
- Ubuntu 22.04 LTS
- Ports 22, 80, 443, and 8080 open in your firewall or security group

### Step 2: Connect to Your Server

```bash
chmod 400 ~/Downloads/your-key.pem
ssh -i ~/Downloads/your-key.pem ubuntu@YOUR_SERVER_IP
```

### Step 3: Install Dependencies

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose
sudo apt install docker-compose-plugin -y

# Install supporting tools
sudo apt install python3 python3-pip iptables -y

# Create audit log directory
sudo mkdir -p /var/log/detector
sudo chmod 777 /var/log/detector
```

### Step 4: Clone the Repository

```bash
git clone https://github.com/samueltomisin/hng-anomaly-detector.git
cd hng-anomaly-detector
```

### Step 5: Set Your Slack Webhook

Go to https://api.slack.com/apps, create an app, enable Incoming Webhooks, and copy your webhook URL. Then:

```bash
# Open docker-compose.yml and replace the SLACK_WEBHOOK_URL value
vim docker-compose.yml
```

However, never hardcode your webhook URL directly in docker-compose.yml. GitHub will detect it and block your push. Use a `.env` file instead.

Create a `.env` file in the project root:

```bash
cat > .env << 'EOF'
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
EOF
```

Make sure `.env` is in your `.gitignore` so it is never committed:

```bash
echo ".env" >> .gitignore
```

### Step 6: Point a Domain at Your Server

For the dashboard to be accessible at a domain (required for submission), point a subdomain or DuckDNS domain at your server IP. DuckDNS is free:

1. Go to https://www.duckdns.org
2. Create a subdomain
3. Set the IP to your server's public IP
4. Your dashboard will be at `http://your-subdomain.duckdns.org:8080`

### Step 7: Launch the Full Stack

```bash
docker compose up -d --build
```

This builds and starts three containers: Nginx, Nextcloud, and the Detector daemon.

### Step 8: Verify Everything is Running

```bash
# All three containers should show 'Up'
docker compose ps

# Dashboard should be listening
sudo ss -tlnp | grep 8080

# Nginx should be responding
curl http://localhost/

# Detector should be watching logs
docker compose logs detector --tail=20
```

### Step 9: Test Detection

```bash
# Install Apache Bench
sudo apt install apache2-utils -y

# Simulate a DDoS attack
ab -n 2000 -c 100 http://localhost/
```

Within 10 seconds you should see a ban alert in Slack, the IP appear on your dashboard, and a DROP rule in iptables:

```bash
sudo iptables -L INPUT -n
```

---

## 📋 Audit Log

Every ban, unban, and baseline recalculation is recorded automatically.

To view it:
```bash
docker exec hng-detector-detector-1 cat /var/log/detector/audit.log
```

```
[2026-04-28T10:00:00Z] BAN 1.2.3.4 | z-score=5.23 | rate=8.3200 | baseline=1.0000 | duration=600
[2026-04-28T10:10:00Z] UNBAN 1.2.3.4 | offense #1 | released
[2026-04-28T10:01:00Z] BASELINE_RECALC | mean=1.2400 | stddev=0.5000
```
---

## 📝 Blog Post

Read the full beginner-friendly breakdown of how this was built:

👉 (https://medium.com/@samueltomisin31/how-i-built-a-real-time-ddos-detection-engine-from-scratch-and-what-i-learned-doing-it-dfe532572f2e)

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

- **Python 3.11** : daemon, detection logic, dashboard
- **Docker & Docker Compose** : container orchestration
- **Nginx** : reverse proxy and JSON access logging
- **iptables** : kernel-level IP blocking
- **Slack Webhooks** : real-time alerting
- **psutil** : CPU and memory monitoring

---

*Built for HNG Internship Stage 3