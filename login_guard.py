import time
import os
import re
import requests
import socket
import subprocess
import shutil
import smtplib
import ssl
from email.message import EmailMessage
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASS = os.getenv("GMAIL_APP_PASSWORD")
GMAIL_RECIPIENT = os.getenv("ALERT_RECIPIENT_EMAIL")
LOG_FILE = os.getenv("LOG_FILE_PATH", "/var/log/auth.log")
HOSTNAME = socket.gethostname()

# Brute-force configuration
try:
    BF_THRESHOLD = int(os.getenv("BRUTE_FORCE_THRESHOLD", "5"))
    BF_TIME_WINDOW = int(os.getenv("TIME_WINDOW", "60"))
except ValueError:
    print("Warning: Invalid config for brute force. Using defaults.")
    BF_THRESHOLD = 5
    BF_TIME_WINDOW = 60

# Active Defense Configuration
ENABLE_ACTIVE_DEFENSE = os.getenv("ENABLE_ACTIVE_DEFENSE", "false").lower() == "true"
BLOCKED_IPS = set()

# Store failed attempts: {ip: [timestamp1, timestamp2, ...]}
failed_attempts = {}

# GeoIP Cache: {ip: {"country": "US", "city": "NY", ...}}
geoip_cache = {}

def send_email_alert(subject, message):
    """Sends an email alert using Gmail SMTP."""
    if not GMAIL_USER or not GMAIL_PASS or not GMAIL_RECIPIENT:
        return

    msg = EmailMessage()
    msg.set_content(message)
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = GMAIL_RECIPIENT

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.send_message(msg)
    except Exception as e:
        print(f"Error sending email alert: {e}")

def send_sms_alert(message):
    """Sends an SMS alert using the Email-to-SMS Gateway method."""
    # This uses the same SMTP logic as email, but targets the mobile gateway
    # Re-using send_email_alert logic but specifically for the gateway address.
    # ALERT_RECIPIENT_EMAIL should be set to your phone's gateway (e.g. 1234567890@vtext.com)
    if not GMAIL_USER or not GMAIL_PASS or not GMAIL_RECIPIENT:
        return
        
    subject = "Login Guard SMS"
    send_email_alert(subject, message)

def get_ip_details(ip):
    """Fetches location details for an IP address."""
    # Check cache first
    if ip in geoip_cache:
        return geoip_cache[ip]

    # Skip private/local IPs
    if ip in ["127.0.0.1", "::1", "localhost"] or ip.startswith(("192.168.", "10.", "172.16.")):
        return {"country": "Private IP", "city": "Local Network", "isp": "Unknown"}

    url = f"http://ip-api.com/json/{ip}"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                details = {
                    "country": data.get("country", "Unknown"),
                    "city": data.get("city", "Unknown"),
                    "isp": data.get("isp", "Unknown")
                }
                geoip_cache[ip] = details
                return details
    except Exception as e:
        print(f"GeoIP lookup failed: {e}")
    
    return None

def send_telegram_alert(message):
    """Sends a notification to the configured Telegram chat."""
    if not BOT_TOKEN or not CHAT_ID:
        print("Error: Telegram credentials not configured.")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            print(f"Failed to send alert: {response.text}")
    except Exception as e:
        print(f"Error sending alert: {e}")

def block_ip(ip):
    """Blocks an IP using UFW or iptables."""
    if ip in ["127.0.0.1", "::1", "localhost"]:
        print("Safety check: Cannot block localhost!")
        return False
        
    if ip in BLOCKED_IPS:
        print(f"IP {ip} is already blocked.")
        return True

    print(f"Attempting to block IP: {ip}...")
    success = False
    
    # Check for UFW
    if shutil.which("ufw"):
        # ufw insert 1 deny from <ip>
        cmd = ["ufw", "insert", "1", "deny", "from", ip, "to", "any"]
        try:
            # We assume script is running as root
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"Blocked {ip} using UFW.")
            success = True
        except subprocess.CalledProcessError as e:
            print(f"Failed to block with UFW: {e}")
            # Fallback to iptables if UFW fails? usually if ufw is there but disabled it might fail
            # Let's try iptables as fallback only if UFW command errors out seriously
    
    # Fallback to iptables if UFW missing or failed (and not yet successful)
    if not success and shutil.which("iptables"):
        # iptables -I INPUT -s <ip> -j DROP
        cmd = ["iptables", "-I", "INPUT", "-s", ip, "-j", "DROP"]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"Blocked {ip} using iptables.")
            success = True
        except subprocess.CalledProcessError as e:
            print(f"Failed to block with iptables: {e}")

    if success:
        BLOCKED_IPS.add(ip)
        return True
    
    return False

def parse_line(line):
    """Parses a log line to check for failed login attempts."""
    # Common patterns for failed logins on Debian/Linux
    patterns = [
        r"Failed password for (?P<user>\S+) from (?P<ip>\S+) port \d+ (?P<proto>\S+)",
        r"authentication failure;.*user=(?P<user>\S+).*rhost=(?P<ip>\S+)",
        r"Failed password for invalid user (?P<user>\S+) from (?P<ip>\S+) port \d+ (?P<proto>\S+)"
    ]

    for pattern in patterns:
        match = re.search(pattern, line)
        if match:
            return match.groupdict()
    return None

def cleanup_old_attempts():
    """Removes attempt timestamps older than the time window."""
    current_time = time.time()
    for ip in list(failed_attempts.keys()):
        # Keep only timestamps within the window
        failed_attempts[ip] = [t for t in failed_attempts[ip] if current_time - t <= BF_TIME_WINDOW]
        # Remove IP key if no recent attempts
        if not failed_attempts[ip]:
            del failed_attempts[ip]

def monitor_log():
    """Monitors the log file for new lines."""
    print(f"Starting Login Guard on {HOSTNAME}...")
    print(f"Monitoring {LOG_FILE}")
    print(f"Brute-force protection: >{BF_THRESHOLD} attempts in {BF_TIME_WINDOW}s")
    if ENABLE_ACTIVE_DEFENSE:
        print("🛡️ ACTIVE DEFENSE ENABLED: IPs will be blocked.")
    
    # Open file and seek to the end
    try:
        f = open(LOG_FILE, 'r')
        f.seek(0, os.SEEK_END)
    except FileNotFoundError:
        print(f"Error: Log file {LOG_FILE} not found. Are you running as root/sudo?")
        return

    while True:
        line = f.readline()
        if not line:
            time.sleep(0.5)
            # Occasional cleanup to prevent memory leaks in very long runs
            if time.time() % 60 == 0: 
                cleanup_old_attempts()
            continue
        
        data = parse_line(line)
        if data:
            user = data.get("user", "unknown")
            ip = data.get("ip", "unknown")
            timestamp_str = time.strftime("%Y-%m-%d %H:%M:%S")
            current_ts = time.time()

            # Track this attempt
            if ip not in failed_attempts:
                failed_attempts[ip] = []
            failed_attempts[ip].append(current_ts)
            
            # Clean up old attempts for this IP immediately to get accurate count
            failed_attempts[ip] = [t for t in failed_attempts[ip] if current_ts - t <= BF_TIME_WINDOW]
            count = len(failed_attempts[ip])

            is_brute_force = count >= BF_THRESHOLD
            blocked_status = ""
            
            # Active Defense Trigger
            if is_brute_force and ENABLE_ACTIVE_DEFENSE:
                if block_ip(ip):
                    blocked_status = "\n🚫 *ACTION TAKEN:* IP has been BLOCKED."
                else:
                    blocked_status = "\n⚠️ *ACTION FAILED:* Could not block IP (Check permissions)."

            # GeoIP Lookup
            geo = get_ip_details(ip)
            if geo:
                loc_str = f"🏳️ {geo['country']}, {geo['city']}"
                isp_str = f"🏢 {geo['isp']}"
            else:
                loc_str = "🏳️ Unknown"
                isp_str = "🏢 Unknown"

            # Construct Alert
            if is_brute_force:
                if count == BF_THRESHOLD:
                    header = "🚨⚠️ *BRUTE FORCE DETECTED* ⚠️🚨"
                else:
                    header = f"🚨 *ONGOING ATTACK ({count} attempts)*"
            else:
                header = "⚠️ *Unauthorized Login Attempt*"

            alert_msg = (
                f"{header}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🖥 *Host:* `{HOSTNAME}`\n"
                f"👤 *User:* `{user}`\n"
                f"🌍 *Source IP:* `{ip}`\n"
                f"{loc_str}\n"
                f"{isp_str}\n"
                f"📅 *Time:* `{timestamp_str}`\n"
                f"🔢 *Attempts:* `{count}` / {BF_TIME_WINDOW}s"
                f"{blocked_status}\n"
                f"━━━━━━━━━━━━━━━━━━"
            )
            
            print(f"Alert triggered: {user} from {ip} (Count: {count}) {blocked_status.strip()}")
            print(f"  > {loc_str}")
            
            # Send Multi-Channel Alerts
            send_telegram_alert(alert_msg)
            
            # Use a cleaner subject for email
            email_subject = header.replace("*", "").replace("🚨", "").replace("⚠️", "").strip()
            clean_msg = alert_msg.replace("*", "")
            
            send_email_alert(f"Login Guard: {email_subject}", clean_msg)
            
            # Send SMS Alert (Gateway method)
            send_sms_alert(clean_msg)

if __name__ == "__main__":
    monitor_log()
