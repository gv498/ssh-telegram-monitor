#!/usr/bin/env python3
import os
import sys
import json
import requests
import socket
import subprocess
from datetime import datetime
import psutil
import re

# Telegram Bot Configuration
BOT_TOKEN = "8208600847:AAFjHcPEbYG1PJO03tfwOP7rxOHvKJ0qvhk"
PHONE_NUMBER = "+972526342871"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

def get_chat_id():
    """Get chat ID from stored file or wait for user to start conversation"""
    chat_id_file = "/etc/telegram_chat_id.txt"

    if os.path.exists(chat_id_file):
        with open(chat_id_file, 'r') as f:
            return f.read().strip()

    # Get updates to find chat ID
    response = requests.get(f"{TELEGRAM_API}/getUpdates")
    if response.status_code == 200:
        data = response.json()
        if data['result']:
            for update in data['result']:
                if 'message' in update:
                    chat_id = update['message']['chat']['id']
                    with open(chat_id_file, 'w') as f:
                        f.write(str(chat_id))
                    return str(chat_id)
    return None

def get_system_info():
    """Collect comprehensive system information"""
    info = {}

    # Basic info from environment
    ssh_info = os.environ.get('SSH_CLIENT', '') or os.environ.get('SSH_CONNECTION', '')
    if ssh_info:
        parts = ssh_info.split()
        info['ip'] = parts[0] if parts else 'Unknown'
    else:
        info['ip'] = 'Unknown'

    info['user'] = os.environ.get('USER', os.environ.get('PAM_USER', 'Unknown'))
    info['hostname'] = socket.gethostname()
    info['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # System info
    try:
        info['os'] = subprocess.check_output(['uname', '-a'], text=True).strip()
    except:
        info['os'] = 'Unknown'

    # CPU and Memory usage
    try:
        info['cpu_percent'] = f"{psutil.cpu_percent(interval=1)}%"
        info['memory_percent'] = f"{psutil.virtual_memory().percent}%"
        info['disk_free'] = subprocess.check_output(['df', '-h', '/'], text=True).split('\n')[1].split()[3]
    except:
        info['cpu_percent'] = 'N/A'
        info['memory_percent'] = 'N/A'
        info['disk_free'] = 'N/A'

    # Uptime
    try:
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = float(f.readline().split()[0])
            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            info['uptime'] = f"{days} days, {hours} hours, {minutes} minutes"
    except:
        info['uptime'] = 'N/A'

    # Failed login attempts
    try:
        failed = subprocess.check_output(
            ['grep', 'Failed password', '/var/log/auth.log'],
            text=True, stderr=subprocess.DEVNULL
        ).count('\n')
        info['failed_attempts'] = str(failed)
    except:
        info['failed_attempts'] = '0'

    # Open ports
    try:
        netstat = subprocess.check_output(['ss', '-tuln'], text=True)
        ports = re.findall(r':(\d+)\s', netstat)
        unique_ports = sorted(set(ports))[:10]  # First 10 ports
        info['open_ports'] = ', '.join(unique_ports)
    except:
        info['open_ports'] = 'N/A'

    # GeoIP location
    try:
        if info['ip'] and info['ip'] != 'Unknown':
            response = requests.get(f"http://ip-api.com/json/{info['ip']}", timeout=2)
            if response.status_code == 200:
                geo_data = response.json()
                info['location'] = f"{geo_data.get('country', 'Unknown')}, {geo_data.get('city', 'Unknown')}"
                info['reverse_dns'] = geo_data.get('reverse', 'N/A')
            else:
                info['location'] = 'Unknown'
                info['reverse_dns'] = 'N/A'
        else:
            info['location'] = 'Unknown'
            info['reverse_dns'] = 'N/A'
    except:
        info['location'] = 'Unknown'
        info['reverse_dns'] = 'N/A'

    # Check sudo permissions
    try:
        sudo_check = subprocess.run(['sudo', '-n', 'true'], capture_output=True)
        info['sudo'] = 'Yes' if sudo_check.returncode == 0 else 'No'
    except:
        info['sudo'] = 'N/A'

    # Last command
    try:
        history = subprocess.check_output(['tail', '-n', '1', f'/home/{info["user"]}/.bash_history'],
                                        text=True, stderr=subprocess.DEVNULL).strip()
        info['last_command'] = history if history else 'N/A'
    except:
        info['last_command'] = 'N/A'

    # Recent logins with full date and time
    try:
        last_output = subprocess.check_output(['last', '-n', '5', '-i', '-F'], text=True)
        recent_logins = []
        for line in last_output.split('\n')[1:5]:
            if line.strip() and not line.startswith('wtmp'):
                parts = line.split()
                if len(parts) >= 10:
                    # Extract user, IP and full timestamp
                    user = parts[0]
                    ip = parts[2]
                    # Find the date/time part (usually starts with a day name)
                    date_start = -1
                    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
                    for i, part in enumerate(parts):
                        if part in days:
                            date_start = i
                            break
                    if date_start > 0:
                        date_time = ' '.join(parts[date_start:date_start+5])
                        recent_logins.append(f"{user} from {ip} - {date_time}")
        info['recent_logins'] = '\n'.join(recent_logins) if recent_logins else 'N/A'
    except:
        info['recent_logins'] = 'N/A'

    return info

def format_message(info, event_type="login"):
    """Format the notification message"""
    if event_type == "login":
        emoji = "✅"
        title = "התחברות SSH מוצלחת"
    elif event_type == "failed":
        emoji = "❌"
        title = "ניסיון התחברות SSH נכשל"
    else:
        emoji = "🔔"
        title = "התראת SSH"

    message = f"""
{emoji} {title} {emoji}
📌 כתובת IP: {info['ip']}
🔢 פורט: 22
👤 משתמש: {info['user']}
⏰ זמן: {info['timestamp']}
🖥 שרת: {info['hostname']}
📂 מערכת הפעלה: {info['os'][:100]}...
📜 פקודה אחרונה: {info['last_command']}
📅 התחברויות אחרונות:
{info['recent_logins']}
📊 שימוש במעבד: {info['cpu_percent']}
💾 שימוש בזיכרון: {info['memory_percent']}
🖴 שטח פנוי בדיסק: {info['disk_free']}
⏳ משך פעילות המערכת: {info['uptime']}
❌ ניסיונות התחברות כושלים: {info['failed_attempts']}
🔌 פורטים פתוחים: {info['open_ports']}
🌍 מיקום גיאוגרפי: {info['location']}
🔄 DNS הפוך: {info['reverse_dns']}
🔐 הרשאות Sudo: {info['sudo']}
"""

    return message

def send_telegram_message(chat_id, message, ip_address=None):
    """Send message via Telegram Bot API"""
    # Extract IP from message if not provided
    if not ip_address:
        import re
        ip_match = re.search(r'📌 כתובת IP: ([\d.]+)', message)
        if ip_match:
            ip_address = ip_match.group(1)
        else:
            ip_address = "unknown"

    # Create inline keyboard for actions with IP embedded
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "🔓 פתח חסימה", "callback_data": f"unblock_{ip_address}"},
                {"text": "🚫 חסום IP", "callback_data": f"block_{ip_address}"}
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

def main():
    """Main function"""
    event_type = sys.argv[1] if len(sys.argv) > 1 else "login"

    # Get chat ID
    chat_id = get_chat_id()
    if not chat_id:
        # Send message to get chat ID
        print(f"Please start a conversation with the bot and send any message")
        print(f"Bot link: https://t.me/{BOT_TOKEN.split(':')[0]}")
        sys.exit(1)

    # Collect system information
    info = get_system_info()

    # Format message
    message = format_message(info, event_type)

    # Send notification with IP address
    if send_telegram_message(chat_id, message, info.get('ip')):
        print("Notification sent successfully")
    else:
        print("Failed to send notification")

if __name__ == "__main__":
    main()