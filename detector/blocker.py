import subprocess
import logging

IPTABLES = "/usr/sbin/iptables"

def block_ip(ip):
    try:
        subprocess.run(
            [IPTABLES, '-I', 'INPUT', '-s', ip, '-j', 'DROP'],
            check=True, capture_output=True
        )
        logging.info(f"Blocked IP: {ip}")
        print(f"[IPTABLES] Blocked {ip}", flush=True)
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to block {ip}: {e}")
        print(f"[IPTABLES ERROR] {e}", flush=True)
        return False

def unblock_ip(ip):
    try:
        subprocess.run(
            [IPTABLES, '-D', 'INPUT', '-s', ip, '-j', 'DROP'],
            check=True, capture_output=True
        )
        logging.info(f"Unblocked IP: {ip}")
        print(f"[IPTABLES] Unblocked {ip}", flush=True)
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to unblock {ip}: {e}")
        print(f"[IPTABLES ERROR] {e}", flush=True)
        return False
