#!/usr/bin/env python3
import time
import subprocess
import re
import os
from ssh_telegram_notify import get_chat_id, send_telegram_message, get_system_info, format_message

LAST_LINE_FILE = "/var/run/ssh_monitor_last_line"

def get_last_processed_line():
    """Get the last processed line number"""
    if os.path.exists(LAST_LINE_FILE):
        with open(LAST_LINE_FILE, 'r') as f:
            return int(f.read().strip())
    return 0

def save_last_processed_line(line_num):
    """Save the last processed line number"""
    with open(LAST_LINE_FILE, 'w') as f:
        f.write(str(line_num))

def monitor_auth_log():
    """Monitor /var/log/auth.log for failed SSH attempts"""
    chat_id = get_chat_id()
    if not chat_id:
        print("No chat ID configured. Please run get_telegram_chat_id.py first")
        return

    last_line = get_last_processed_line()

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
                    # Check for failed SSH attempts
                    if 'Failed password' in line or 'Invalid user' in line:
                        # Extract IP and user
                        ip_match = re.search(r'from\s+([\d.]+)', line)
                        user_match = re.search(r'(Failed password for |Invalid user\s+)(\S+)', line)

                        if ip_match:
                            # Create custom info for failed attempt
                            info = get_system_info()
                            info['ip'] = ip_match.group(1)
                            if user_match:
                                info['user'] = user_match.group(2)

                            message = format_message(info, "failed")
                            send_telegram_message(chat_id, message)

                save_last_processed_line(current_lines)

        except Exception as e:
            print(f"Error: {e}")

        time.sleep(5)  # Check every 5 seconds

if __name__ == "__main__":
    monitor_auth_log()