import time
import threading
from blocker import unblock_ip
import notifier
import logging

UNBAN_SCHEDULE = [10 * 60, 30 * 60, 120 * 60]

class UnbanManager:
    def __init__(self):
        self.banned = {}
        self.lock = threading.Lock()

    def ban(self, ip, condition, rate, baseline):
        with self.lock:
            offense = self.banned.get(ip, {}).get('offense_count', 0)
            self.banned[ip] = {
                'banned_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'offense_count': offense + 1,
                'condition': condition,
                'rate': rate,
                'baseline': baseline
            }
            if offense < len(UNBAN_SCHEDULE):
                duration = UNBAN_SCHEDULE[offense]
                t = threading.Timer(duration, self._unban, args=[ip])
                t.daemon = True
                t.start()
                logging.info(f"UNBAN_SCHEDULED {ip} | in {duration}s")
                return duration
            else:
                logging.info(f"PERMANENT_BAN {ip} | offense #{offense + 1}")
                return None

    def _unban(self, ip):
        with self.lock:
            if ip in self.banned:
                unblock_ip(ip)
                info = self.banned[ip]
                notifier.alert_unban(ip, info['offense_count'])
                logging.info(f"UNBAN {ip} | offense #{info['offense_count']} | released")
                del self.banned[ip]

    def is_banned(self, ip):
        with self.lock:
            return ip in self.banned

    def get_banned(self):
        with self.lock:
            return dict(self.banned)
