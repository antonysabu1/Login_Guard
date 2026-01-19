import time
import os

LOG_FILE = "dummy_auth.log"

print(f"Writing dummy failed logins to {LOG_FILE}...")
print("Press Ctrl+C to stop.")

try:
    with open(LOG_FILE, "a") as f:
        while True:
            # Simulate a standard Linux auth failure
            log_line = "Jan 15 10:23:45 kali sshd[1234]: Failed password for invalid user hacker from 192.168.1.100 port 5555 ssh2\n"
            f.write(log_line)
            f.flush()
            print("Logged failed attempt.")
            time.sleep(5)
except KeyboardInterrupt:
    print("\nStopped.")
