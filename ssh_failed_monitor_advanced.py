#!/usr/bin/env python3
import time
import subprocess
import re
import os
import json
from datetime import datetime
from collections import defaultdict
import sys

# Add parent directory to path for imports
sys.path.insert(0, '/usr/local/bin')
from ssh_telegram_notify import get_chat_id, send_telegram_message, get_system_info, format_message

LAST_LINE_FILE = "/var/run/ssh_monitor_last_line"
FAILED_ATTEMPTS_FILE = "/var/run/ssh_failed_attempts.json"
BOT_TOKEN = "8208600847:AAFjHcPEbYG1PJO03tfwOP7rxOHvKJ0qvhk"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
MAX_ATTEMPTS = 3  # Block after 3 failed attempts

def get_last_processed_line():
    """Get the last processed line number"""
    if os.path.exists(LAST_LINE_FILE):
        with open(LAST_LINE_FILE, 'r') as f:
            try:
                return int(f.read().strip())
            except:
                return 0
    return 0

def save_last_processed_line(line_num):
    """Save the last processed line number"""
    with open(LAST_LINE_FILE, 'w') as f:
        f.write(str(line_num))

def load_failed_attempts():
    """Load failed attempts from file"""
    if os.path.exists(FAILED_ATTEMPTS_FILE):
        with open(FAILED_ATTEMPTS_FILE, 'r') as f:
            try:
                return defaultdict(list, json.load(f))
            except:
                return defaultdict(list)
    return defaultdict(list)

def save_failed_attempts(attempts):
    """Save failed attempts to file"""
    with open(FAILED_ATTEMPTS_FILE, 'w') as f:
        json.dump(dict(attempts), f)

def block_ip_automatically(ip, attempts_info):
    """Automatically block IP after max attempts"""
    try:
        # Run the kill sessions script
        subprocess.run(['/usr/local/bin/kill_ssh_sessions.sh', ip],
                      capture_output=True, text=True)

        # Block in fail2ban
        subprocess.run(['fail2ban-client', 'set', 'sshd', 'banip', ip],
                      capture_output=True)

        # Block in UFW
        subprocess.run(['ufw', 'insert', '1', 'deny', 'from', ip],
                      capture_output=True)

        # Add iptables DROP rule
        subprocess.run(['iptables', '-I', 'INPUT', '1', '-s', ip, '-j', 'DROP'],
                      capture_output=True)

        return True
    except:
        return False

def send_failed_attempt_notification(chat_id, ip, user, attempt_num, auto_blocked=False):
    """Send notification for failed SSH attempt"""
    import requests

    # Get basic info
    info = {
        'ip': ip,
        'user': user,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'hostname': subprocess.check_output(['hostname'], text=True).strip(),
        'attempt_num': attempt_num
    }

    # Try to get location
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}", timeout=2)
        if response.status_code == 200:
            geo_data = response.json()
            info['location'] = f"{geo_data.get('country', 'Unknown')}, {geo_data.get('city', 'Unknown')}"
            info['isp'] = geo_data.get('isp', 'Unknown')
        else:
            info['location'] = 'Unknown'
            info['isp'] = 'Unknown'
    except:
        info['location'] = 'Unknown'
        info['isp'] = 'Unknown'

    if auto_blocked:
        emoji = "🚫"
        title = "IP חסום אוטומטית!"
        status = "חסום לאחר 3 ניסיונות כושלים"
        color = "🔴"
    else:
        emoji = "⚠️"
        title = "ניסיון התחברות SSH כושל"
        status = f"ניסיון {attempt_num} מתוך {MAX_ATTEMPTS}"
        color = "🟡" if attempt_num < MAX_ATTEMPTS else "🔴"

    message = f"""
{emoji} {title} {emoji}
{color} סטטוס: {status}
📌 כתובת IP: {info['ip']}
👤 משתמש: {info['user']}
⏰ זמן: {info['timestamp']}
🖥 שרת: {info['hostname']}
🌍 מיקום: {info['location']}
🌐 ספק: {info['isp']}
🔢 ניסיון מספר: {info['attempt_num']}
"""

    if attempt_num >= MAX_ATTEMPTS - 1:
        message += "\n⚠️ אזהרה: עוד ניסיון אחד וה-IP ייחסם!"

    if auto_blocked:
        message += "\n\n✅ הפעולות שבוצעו:"
        message += "\n• IP נחסם ב-Fail2ban"
        message += "\n• IP נחסם ב-UFW"
        message += "\n• חיבורים קיימים נותקו"

    # Create inline keyboard
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "🚫 חסום מיד", "callback_data": f"block_{ip}"},
                {"text": "🔓 בטל חסימה", "callback_data": f"unblock_{ip}"}
            ],
            [
                {"text": "📊 מידע נוסף", "callback_data": "more_info"}
            ]
        ]
    }

    data = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML',
        'reply_markup': json.dumps(keyboard)
    }

    response = requests.post(f"{TELEGRAM_API}/sendMessage", data=data)
    return response.status_code == 200

def monitor_auth_log():
    """Monitor /var/log/auth.log for failed SSH attempts"""
    chat_id = get_chat_id()
    if not chat_id:
        print("No chat ID configured")
        return

    last_line = get_last_processed_line()
    failed_attempts = load_failed_attempts()

    print(f"Starting SSH failed attempts monitor...")
    print(f"Will auto-block after {MAX_ATTEMPTS} failed attempts")

    while True:
        try:
            # Get total lines in auth.log
            result = subprocess.run(['wc', '-l', '/var/log/auth.log'],
                                  capture_output=True, text=True)
            current_lines = int(result.stdout.split()[0])

            if current_lines > last_line:
                # Read new lines
                result = subprocess.run(['tail', '-n', str(current_lines - last_line), '/var/log/auth.log'],
                                      capture_output=True, text=True)

                for line in result.stdout.splitlines():
                    # Skip test entries
                    if 'testuser' in line or '192.168.1.100' in line:
                        continue

                    # Check for failed SSH attempts (password or key) - only real sshd messages
                    if 'sshd[' in line and (
                        'Failed password' in line or
                        'Invalid user' in line or
                        'authentication failure' in line or
                        'Connection closed by authenticating user' in line):

                        # Extract IP
                        ip_match = re.search(r'from\s+([\d.]+)', line)
                        if not ip_match:
                            # Try alternative pattern
                            ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)

                        if ip_match:
                            ip = ip_match.group(1)

                            # Extract username
                            user = "unknown"
                            user_patterns = [
                                r'Failed password for invalid user (\S+)',
                                r'Failed password for (\S+)',
                                r'Invalid user (\S+)',
                                r'user=(\S+)',
                                r'Connection closed by authenticating user (\S+)'
                            ]

                            for pattern in user_patterns:
                                user_match = re.search(pattern, line)
                                if user_match:
                                    user = user_match.group(1)
                                    break

                            # Track failed attempt
                            timestamp = datetime.now().isoformat()
                            failed_attempts[ip].append({
                                'user': user,
                                'time': timestamp,
                                'line': line[:100]  # Store first 100 chars
                            })

                            # Count attempts in last hour
                            recent_attempts = []
                            one_hour_ago = datetime.now().timestamp() - 3600

                            for attempt in failed_attempts[ip]:
                                try:
                                    attempt_time = datetime.fromisoformat(attempt['time']).timestamp()
                                    if attempt_time > one_hour_ago:
                                        recent_attempts.append(attempt)
                                except:
                                    recent_attempts.append(attempt)

                            # Update with only recent attempts
                            failed_attempts[ip] = recent_attempts
                            attempt_count = len(recent_attempts)

                            print(f"Failed attempt from {ip} (user: {user}) - Attempt #{attempt_count}")

                            # Check if should auto-block
                            if attempt_count >= MAX_ATTEMPTS:
                                print(f"Auto-blocking {ip} after {attempt_count} failed attempts")

                                # Block the IP
                                if block_ip_automatically(ip, recent_attempts):
                                    # Send notification about auto-block
                                    send_failed_attempt_notification(
                                        chat_id, ip, user, attempt_count, auto_blocked=True
                                    )

                                    # Clear attempts for this IP
                                    del failed_attempts[ip]
                                else:
                                    print(f"Failed to auto-block {ip}")
                            else:
                                # Send warning notification
                                send_failed_attempt_notification(
                                    chat_id, ip, user, attempt_count, auto_blocked=False
                                )

                            # Save attempts to file
                            save_failed_attempts(failed_attempts)

                save_last_processed_line(current_lines)

        except Exception as e:
            print(f"Error: {e}")

        time.sleep(2)  # Check every 2 seconds

if __name__ == "__main__":
    monitor_auth_log()