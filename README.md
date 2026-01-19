# Login Guard 🛡️

Login Guard is a lightweight Python-based security tool for Linux systems. It monitors authentication logs (`/var/log/auth.log`) in real-time and sends instant Telegram alerts when unauthorized login attempts are detected.

## ✨ Features

- **Real-time Monitoring**: Watches system authentication logs continuously.
- **Instant Alerts**: Sends detailed notifications to your Telegram via bot API.
- **Detailed Info**: Alerts include username, IP address, and timestamp of the failed attempt.
- **Systemd Integration**: Runs as a background service with auto-restart capabilities.
- **Lightweight**: Minimal resource usage, suitable for servers and laptops.

## 📋 Prerequisites

- Linux system (Debian/Ubuntu based recommended)
- Python 3.6+
- Root/Sudo privileges (to read `/var/log/auth.log` and install services)
- A Telegram Bot Token and Chat ID

## 🚀 Installation

An automated installation script is provided for convenience.

1.  **Clone or Download** this repository.
2.  **Make the script executable**:
    ```bash
    chmod +x install.sh
    ```
3.  **Run the installer** (requires sudo):
    ```bash
    sudo ./install.sh
    ```

The installer will:
- specific installation directory `/opt/login_guard`
- Create a virtual environment and install dependencies
- Install and start the systemd service

## ⚙️ Configuration

After installation, you **must** configure your Telegram credentials.

1.  Open the configuration file:
    ```bash
    sudo nano /opt/login_guard/.env
    ```
2.  Fill in your details:
    ```ini
    TELEGRAM_BOT_TOKEN=your_bot_token_here
    TELEGRAM_CHAT_ID=your_chat_id_here
    # Optional: Brute Force Settings
    BRUTE_FORCE_THRESHOLD=5
    TIME_WINDOW=60
    # Optional: Active Defense (Block IPs) - CAREFUL!
    ENABLE_ACTIVE_DEFENSE=true
    ```
3.  Restart the service to apply changes:
    ```bash
    sudo systemctl restart login_guard
    ```

## 🧪 Testing

You can verify the system works without waiting for a real attack.

1.  **Stop the service** (if running):
    ```bash
    sudo systemctl stop login_guard
    ```
2.  **Generate Dummy Logs**:
    Open a terminal and run the test generator:
    ```bash
    python3 test_gen.py
    ```
    This will start writing fake failed login attempts to `dummy_auth.log`.

3.  **Run Login Guard Locally**:
    In another terminal, run the monitor pointing to the dummy log:
    ```bash
    # Create a local .env file first if you haven't already, or export var
    export LOG_FILE_PATH=dummy_auth.log
    # Ensure you are in the project dir and have dependencies installed
    # (If using the installed venv: /opt/login_guard/venv/bin/python3 login_guard.py)
    python3 login_guard.py
    ```

4.  **Observe**: You should see "Alert triggered" messages in the console and receive Telegram notifications (if credentials are valid).
