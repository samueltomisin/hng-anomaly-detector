import time

def tail_log(log_path):
    """Continuously yield new lines from the log file as they appear."""
    while True:
        try:
            with open(log_path, 'r') as f:
                f.seek(0, 2)
                while True:
                    line = f.readline()
                    if line:
                        yield line.strip()
                    else:
                        time.sleep(0.05)
        except FileNotFoundError:
            print(f"Waiting for log file at {log_path}...")
            time.sleep(3)
