
from http.server import HTTPServer, BaseHTTPRequestHandler
import time
import threading
import psutil

state = {
    "banned_ips": {},
    "global_rps": 0.0,
    "top_ips": [],
    "baseline_mean": 0.0,
    "baseline_stddev": 0.0,
    "start_time": time.time()
}

def build_html(global_rps, mean, stddev, ban_count, cpu, mem, uptime_short, uptime_full, ban_rows, top_rows, rps_class, ban_class):
    return """<!DOCTYPE html>
<html>
<head>
<title>HNG Anomaly Detector</title>
<meta http-equiv="refresh" content="3">
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:monospace;background:#0d1117;color:#c9d1d9;padding:24px}
  h1{color:#58a6ff;font-size:20px;margin-bottom:16px}
  h2{color:#8b949e;font-size:14px;margin:20px 0 8px;text-transform:uppercase;letter-spacing:1px}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:20px}
  .card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px}
  .card .val{font-size:28px;font-weight:bold;color:#58a6ff;margin-top:4px}
  .card .val.danger{color:#f85149}
  .card .val.warn{color:#d29922}
  .card .label{font-size:11px;color:#8b949e;text-transform:uppercase}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th{background:#161b22;color:#8b949e;padding:8px 12px;text-align:left;border-bottom:1px solid #30363d}
  td{padding:8px 12px;border-bottom:1px solid #21262d}
  tr:hover td{background:#161b22}
  .banned{color:#f85149;font-weight:bold}
  .footer{margin-top:24px;font-size:11px;color:#484f58}
</style>
</head>
<body>
<h1>HNG Anomaly Detection Engine</h1>
<div class="grid">
  <div class="card"><div class="label">Global req/s</div><div class="val """ + rps_class + """">""" + f"{global_rps:.2f}" + """</div></div>
  <div class="card"><div class="label">Baseline mean</div><div class="val">""" + f"{mean:.2f}" + """</div></div>
  <div class="card"><div class="label">Baseline stddev</div><div class="val">""" + f"{stddev:.2f}" + """</div></div>
  <div class="card"><div class="label">Banned IPs</div><div class="val """ + ban_class + """">""" + str(ban_count) + """</div></div>
  <div class="card"><div class="label">CPU usage</div><div class="val">""" + str(cpu) + """%</div></div>
  <div class="card"><div class="label">Memory usage</div><div class="val">""" + str(mem) + """%</div></div>
  <div class="card"><div class="label">Uptime</div><div class="val">""" + uptime_short + """</div></div>
</div>
<h2>Banned IPs (""" + str(ban_count) + """)</h2>
<table>
  <tr><th>IP</th><th>Offense #</th><th>Condition</th><th>Rate</th><th>Banned at</th></tr>
  """ + ban_rows + """
</table>
<h2>Top 10 Source IPs</h2>
<table>
  <tr><th>IP</th><th>Rate (req/s)</th></tr>
  """ + top_rows + """
</table>
<div class="footer">Auto-refreshes every 3s | HNG Anomaly Detector | Uptime: """ + uptime_full + """</div>
</body></html>"""

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        uptime_secs = int(time.time() - state['start_time'])
        h, rem = divmod(uptime_secs, 3600)
        m, s = divmod(rem, 60)
        uptime_short = f"{h}h{m}m"
        uptime_full = f"{h}h {m}m {s}s"

        ban_rows = "".join(
            f"<tr><td class='banned'>{ip}</td>"
            f"<td>{v['offense_count']}</td>"
            f"<td>{v['condition']}</td>"
            f"<td>{v['rate']:.2f} req/s</td>"
            f"<td>{v['banned_at']}</td></tr>"
            for ip, v in state['banned_ips'].items()
        ) or "<tr><td colspan='5' style='color:#8b949e'>No banned IPs</td></tr>"

        top_rows = "".join(
            f"<tr><td>{ip}</td><td>{rate:.2f}</td></tr>"
            for ip, rate in state['top_ips']
        ) or "<tr><td colspan='2' style='color:#8b949e'>No traffic yet</td></tr>"

        rps = state['global_rps']
        rps_class = "danger" if rps > state['baseline_mean'] * 3 else ""
        ban_class = "danger" if state['banned_ips'] else ""

        html = build_html(
            rps, state['baseline_mean'], state['baseline_stddev'],
            len(state['banned_ips']), psutil.cpu_percent(),
            psutil.virtual_memory().percent,
            uptime_short, uptime_full, ban_rows, top_rows,
            rps_class, ban_class
        )

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, *args):
        pass

def start_dashboard(port=8080):
    server = HTTPServer(('0.0.0.0', port), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(f"Dashboard running on port {port}")

