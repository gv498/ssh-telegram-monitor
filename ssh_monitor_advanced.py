#!/usr/bin/env python3
import time
import subprocess
import re
import os
import json
from datetime import datetime, timedelta
from collections import defaultdict
import sys
import requests

# Configuration
LAST_LINE_FILE = "/var/run/ssh_monitor_last_line"
ATTEMPTS_DB = "/var/run/ssh_attempts_db.json"
BLOCKED_IPS_DB = "/var/run/ssh_blocked_ips.json"
BOT_TOKEN = "8208600847:AAFjHcPEbYG1PJO03tfwOP7rxOHvKJ0qvhk"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
MAX_ATTEMPTS = 3
BLOCK_DURATION_HOURS = 24  # How long to keep tracking blocked IPs

class SSHMonitor:
    def __init__(self):
        self.chat_id = self.get_chat_id()
        self.failed_attempts = self.load_db(ATTEMPTS_DB, dict)
        self.blocked_ips = self.load_db(BLOCKED_IPS_DB, dict)
        self.last_line = self.get_last_line()

    def get_chat_id(self):
        """Get saved Telegram chat ID"""
        try:
            with open('/etc/telegram_chat_id.txt', 'r') as f:
                return f.read().strip()
        except:
            print("No chat ID configured")
            return None

    def load_db(self, filename, default_type):
        """Load JSON database file"""
        if os.path.exists(filename):
            try:
                with open(filename, 'r') as f:
                    return json.load(f)
            except:
                return default_type()
        return default_type()

    def save_db(self, data, filename):
        """Save data to JSON database"""
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)

    def get_last_line(self):
        """Get last processed line number"""
        if os.path.exists(LAST_LINE_FILE):
            try:
                with open(LAST_LINE_FILE, 'r') as f:
                    return int(f.read().strip())
            except:
                return 0
        return 0

    def save_last_line(self, line_num):
        """Save last processed line number"""
        with open(LAST_LINE_FILE, 'w') as f:
            f.write(str(line_num))

    def is_ip_blocked(self, ip):
        """Check if IP is currently blocked"""
        # Check our database
        if ip in self.blocked_ips:
            block_info = self.blocked_ips[ip]
            # Check if block is still valid (within 24 hours)
            blocked_time = datetime.fromisoformat(block_info['blocked_at'])
            if datetime.now() - blocked_time < timedelta(hours=BLOCK_DURATION_HOURS):
                return True
            else:
                # Remove expired block from our tracking
                del self.blocked_ips[ip]
                self.save_db(self.blocked_ips, BLOCKED_IPS_DB)

        # Also check fail2ban
        try:
            result = subprocess.run(['fail2ban-client', 'status', 'sshd'],
                                  capture_output=True, text=True)
            if ip in result.stdout:
                # Add to our database if not there
                if ip not in self.blocked_ips:
                    self.blocked_ips[ip] = {
                        'blocked_at': datetime.now().isoformat(),
                        'reason': 'Found in fail2ban',
                        'attempts': MAX_ATTEMPTS
                    }
                    self.save_db(self.blocked_ips, BLOCKED_IPS_DB)
                return True
        except:
            pass

        # Check iptables
        try:
            result = subprocess.run(['iptables', '-L', 'INPUT', '-n'],
                                  capture_output=True, text=True)
            if ip in result.stdout and 'DROP' in result.stdout:
                return True
        except:
            pass

        return False

    def block_ip(self, ip, reason="Multiple failed attempts"):
        """Block an IP address"""
        print(f"Blocking IP {ip}: {reason}")

        # Kill active sessions
        subprocess.run(['/usr/local/bin/kill_ssh_sessions.sh', ip],
                      capture_output=True)

        # Block in fail2ban
        subprocess.run(['fail2ban-client', 'set', 'sshd', 'banip', ip],
                      capture_output=True)

        # Block in UFW
        subprocess.run(['ufw', 'insert', '1', 'deny', 'from', ip],
                      capture_output=True)

        # Block in iptables
        subprocess.run(['iptables', '-I', 'INPUT', '1', '-s', ip, '-j', 'DROP'],
                      capture_output=True)

        # Update our database
        self.blocked_ips[ip] = {
            'blocked_at': datetime.now().isoformat(),
            'reason': reason,
            'attempts': self.failed_attempts.get(ip, {}).get('count', MAX_ATTEMPTS)
        }
        self.save_db(self.blocked_ips, BLOCKED_IPS_DB)

        # Clear attempts for this IP
        if ip in self.failed_attempts:
            del self.failed_attempts[ip]
            self.save_db(self.failed_attempts, ATTEMPTS_DB)

        return True

    def send_notification(self, ip, user, attempt_num, already_blocked=False):
        """Send Telegram notification"""
        if not self.chat_id:
            return

        # Don't send notification if IP is already blocked
        if already_blocked:
            print(f"IP {ip} is already blocked, skipping notification")
            return

        # Get location info
        location = "Unknown"
        isp = "Unknown"
        try:
            response = requests.get(f"http://ip-api.com/json/{ip}", timeout=2)
            if response.status_code == 200:
                geo_data = response.json()
                location = f"{geo_data.get('country', 'Unknown')}, {geo_data.get('city', 'Unknown')}"
                isp = geo_data.get('isp', 'Unknown')
        except:
            pass

        # Determine status
        if attempt_num >= MAX_ATTEMPTS:
            emoji = "🚫"
            title = "IP חסום אוטומטית!"
            status = f"נחסם אחרי {MAX_ATTEMPTS} ניסיונות"
            color = "🔴"
        else:
            emoji = "⚠️"
            title = "ניסיון התחברות כושל"
            status = f"ניסיון {attempt_num} מתוך {MAX_ATTEMPTS}"
            color = "🟡" if attempt_num < MAX_ATTEMPTS else "🔴"

        message = f"""
{emoji} {title}
{color} סטטוס: {status}
📌 IP: {ip}
👤 משתמש: {user}
⏰ זמן: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
🌍 מיקום: {location}
🌐 ספק: {isp}
🔢 ניסיון: {attempt_num}/{MAX_ATTEMPTS}
"""

        if attempt_num == MAX_ATTEMPTS - 1:
            message += "\n⚠️ עוד ניסיון אחד וייחסם!"
        elif attempt_num >= MAX_ATTEMPTS:
            message += "\n✅ IP נחסם בכל השכבות"

        # Inline keyboard
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🚫 חסום מיד", "callback_data": f"block_{ip}"},
                    {"text": "🔓 בטל חסימה", "callback_data": f"unblock_{ip}"}
                ]
            ]
        }

        data = {
            'chat_id': self.chat_id,
            'text': message,
            'reply_markup': json.dumps(keyboard)
        }

        try:
            requests.post(f"{TELEGRAM_API}/sendMessage", data=data)
        except:
            pass

    def process_failed_attempt(self, ip, user, line):
        """Process a failed SSH attempt"""
        # Check if IP is already blocked
        if self.is_ip_blocked(ip):
            print(f"IP {ip} is already blocked, ignoring attempt")
            return

        # Initialize or update attempts
        if ip not in self.failed_attempts:
            self.failed_attempts[ip] = {
                'count': 0,
                'users': [],
                'first_attempt': datetime.now().isoformat(),
                'last_attempt': datetime.now().isoformat()
            }

        # Clean old attempts (older than 1 hour)
        first_attempt = datetime.fromisoformat(self.failed_attempts[ip]['first_attempt'])
        if datetime.now() - first_attempt > timedelta(hours=1):
            # Reset counter if first attempt was over an hour ago
            self.failed_attempts[ip] = {
                'count': 0,
                'users': [],
                'first_attempt': datetime.now().isoformat(),
                'last_attempt': datetime.now().isoformat()
            }

        # Update attempt info
        self.failed_attempts[ip]['count'] += 1
        self.failed_attempts[ip]['users'].append(user)
        self.failed_attempts[ip]['last_attempt'] = datetime.now().isoformat()

        attempt_count = self.failed_attempts[ip]['count']

        print(f"Failed attempt #{attempt_count} from {ip} (user: {user})")

        # Send notification
        self.send_notification(ip, user, attempt_count)

        # Auto-block after MAX_ATTEMPTS
        if attempt_count >= MAX_ATTEMPTS:
            self.block_ip(ip, f"Auto-blocked after {MAX_ATTEMPTS} failed attempts")
            # Send final notification
            self.send_notification(ip, user, attempt_count, already_blocked=False)

        # Save database
        self.save_db(self.failed_attempts, ATTEMPTS_DB)

    def monitor(self):
        """Main monitoring loop"""
        print(f"Starting SSH monitor (max attempts: {MAX_ATTEMPTS})")
        print(f"Tracking {len(self.blocked_ips)} blocked IPs")

        while True:
            try:
                # Get current line count
                result = subprocess.run(['wc', '-l', '/var/log/auth.log'],
                                      capture_output=True, text=True)
                current_lines = int(result.stdout.split()[0])

                if current_lines > self.last_line:
                    # Read new lines
                    lines_to_read = current_lines - self.last_line
                    result = subprocess.run(['tail', '-n', str(lines_to_read), '/var/log/auth.log'],
                                          capture_output=True, text=True)

                    for line in result.stdout.splitlines():
                        # Skip test entries
                        if 'testuser' in line or '192.168.1.100' in line:
                            continue

                        # Check for real failed attempts
                        if 'sshd[' in line and any(pattern in line for pattern in [
                            'Failed password',
                            'Invalid user',
                            'authentication failure'
                        ]):
                            # Extract IP
                            ip_match = re.search(r'from\s+([\d.]+)', line)
                            if not ip_match:
                                ip_match = re.search(r'rhost=([\d.]+)', line)

                            if ip_match:
                                ip = ip_match.group(1)

                                # Extract username
                                user = "unknown"
                                patterns = [
                                    r'Failed password for invalid user (\S+)',
                                    r'Failed password for (\S+)',
                                    r'Invalid user (\S+)',
                                    r'user=(\S+)'
                                ]

                                for pattern in patterns:
                                    user_match = re.search(pattern, line)
                                    if user_match:
                                        user = user_match.group(1)
                                        break

                                # Process the attempt
                                self.process_failed_attempt(ip, user, line)

                    self.save_last_line(current_lines)

            except Exception as e:
                print(f"Error: {e}")

            time.sleep(2)

if __name__ == "__main__":
    monitor = SSHMonitor()
    monitor.monitor()