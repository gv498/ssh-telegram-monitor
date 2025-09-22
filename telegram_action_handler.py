#!/usr/bin/env python3
import requests
import json
import subprocess
import time
import sys

BOT_TOKEN = "8208600847:AAFjHcPEbYG1PJO03tfwOP7rxOHvKJ0qvhk"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

def get_chat_id():
    """Get saved chat ID"""
    try:
        with open('/etc/telegram_chat_id.txt', 'r') as f:
            return f.read().strip()
    except:
        return None

def unblock_ip(ip):
    """Unblock IP from all security layers"""
    try:
        # Run the comprehensive unblock script
        result = subprocess.run(['/usr/local/bin/unblock_ip_complete.sh', ip],
                              capture_output=True, text=True)

        # Check if successful
        if "Unblocking complete" in result.stdout:
            # Parse verification results
            verifications = []
            if "✅ IP not in fail2ban" in result.stdout:
                verifications.append("✅ Fail2ban - נקי")
            if "✅ IP not in iptables" in result.stdout:
                verifications.append("✅ iptables - נקי")
            if "✅ IP not in UFW" in result.stdout:
                verifications.append("✅ UFW - נקי")

            response = f"🔓 IP {ip} שוחרר בהצלחה!\n"
            response += "\n".join(verifications)

            # Check for warnings
            if "⚠️" in result.stdout:
                response += "\n\n⚠️ אזהרה: ייתכן שנשארו חסימות נוספות"

            return response
        else:
            return f"❌ בעיה בביטול חסימת {ip}\nנסה: /usr/local/bin/unblock_ip_complete.sh {ip}"

    except Exception as e:
        return f"❌ Failed to unblock {ip}: {str(e)}"

def block_ip(ip):
    """Block IP using fail2ban and ufw, and terminate active sessions"""
    try:
        success_actions = []
        errors = []

        # First, run the comprehensive kill script
        try:
            kill_result = subprocess.run(['/usr/local/bin/kill_ssh_sessions.sh', ip],
                                       capture_output=True, text=True)
            terminated_count = kill_result.stdout.count('Killing')
            if terminated_count > 0:
                success_actions.append(f"⚡ נותקו {terminated_count} חיבורים פעילים")
        except Exception as e:
            errors.append(f"Session termination: {str(e)}")

        # Ban in fail2ban
        try:
            subprocess.run(['fail2ban-client', 'set', 'sshd', 'banip', ip],
                         capture_output=True, check=False)
            success_actions.append("🔒 נוסף ל-Fail2ban")
        except Exception as e:
            errors.append(f"Fail2ban: {str(e)}")

        # Block in UFW (insert at position 1 for immediate effect)
        try:
            subprocess.run(['ufw', 'insert', '1', 'deny', 'from', ip],
                         capture_output=True, check=False)
            success_actions.append("🛡️ נחסם ב-UFW Firewall")
        except Exception as e:
            errors.append(f"UFW: {str(e)}")

        # Add immediate iptables DROP rule
        try:
            subprocess.run(['iptables', '-I', 'INPUT', '1', '-s', ip, '-j', 'DROP'],
                         capture_output=True, check=False)
            success_actions.append("🚫 נוסף כלל DROP ב-iptables")
        except Exception as e:
            errors.append(f"iptables: {str(e)}")

        # Force close TCP connections using tcpkill if available
        try:
            subprocess.run(['timeout', '2', 'tcpkill', '-i', 'any', 'host', ip],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
        except:
            pass  # Optional tool, ignore if not available

        # Kill established connections using conntrack (if available)
        try:
            subprocess.run(['conntrack', '-D', '-s', ip],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
            success_actions.append("🔌 חיבורים קיימים נותקו")
        except:
            pass  # Optional tool, ignore if not available

        # Build response based on what succeeded
        if success_actions:
            result = f"✅ IP {ip} נחסם בהצלחה!\n\n"
            result += "\n".join(success_actions)

            # Add note if there were minor errors
            if errors and len(errors) < 3:
                result += "\n\n⚠️ פעולות משניות נכשלו (החסימה בוצעה)"

            return result
        else:
            # Only return error if nothing succeeded
            return f"❌ Failed to block {ip}: No actions succeeded"

    except Exception as e:
        # Catch-all for unexpected errors
        return f"❌ Unexpected error blocking {ip}: {str(e)}"

def get_more_info():
    """Get detailed server information"""
    info = []

    # Active SSH sessions
    try:
        result = subprocess.run(['who'], capture_output=True, text=True)
        info.append("👥 Active SSH Sessions:\n" + result.stdout)
    except:
        pass

    # Fail2ban status
    try:
        result = subprocess.run(['fail2ban-client', 'status', 'sshd'],
                              capture_output=True, text=True)
        info.append("🔒 Fail2ban Status:\n" + result.stdout)
    except:
        pass

    # Network connections
    try:
        result = subprocess.run(['ss', '-tuln'], capture_output=True, text=True)
        lines = result.stdout.split('\n')[:10]
        info.append("🔌 Network Connections:\n" + '\n'.join(lines))
    except:
        pass

    return '\n\n'.join(info)

def handle_callback(callback_data, callback_id, chat_id, message_id):
    """Handle callback from inline keyboard"""
    response_text = ""

    if callback_data.startswith("unblock_"):
        # Extract IP from callback data
        ip = callback_data.replace("unblock_", "")
        if ip and ip != "unknown":
            response_text = unblock_ip(ip)
        else:
            response_text = "❌ לא ניתן לזהות את כתובת ה-IP"

    elif callback_data.startswith("block_"):
        # Extract IP from callback data
        ip = callback_data.replace("block_", "")
        if ip and ip != "unknown":
            response_text = block_ip(ip)
        else:
            response_text = "❌ לא ניתן לזהות את כתובת ה-IP"

    elif callback_data == "more_info":
        response_text = get_more_info()

    # Answer callback
    requests.post(f"{TELEGRAM_API}/answerCallbackQuery",
                 data={'callback_query_id': callback_id})

    # Send response
    if response_text:
        requests.post(f"{TELEGRAM_API}/sendMessage",
                     data={'chat_id': chat_id, 'text': response_text})

def monitor_updates():
    """Monitor bot updates for commands"""
    chat_id = get_chat_id()
    if not chat_id:
        print("No chat ID configured")
        return

    last_update_id = 0

    while True:
        try:
            response = requests.get(f"{TELEGRAM_API}/getUpdates?offset={last_update_id+1}")
            if response.status_code == 200:
                data = response.json()

                for update in data.get('result', []):
                    last_update_id = update['update_id']

                    # Handle callback queries
                    if 'callback_query' in update:
                        callback = update['callback_query']
                        handle_callback(
                            callback['data'],
                            callback['id'],
                            callback['message']['chat']['id'],
                            callback['message']['message_id']
                        )

                    # Handle messages
                    elif 'message' in update:
                        message = update['message']
                        text = message.get('text', '')

                        if text.startswith('/unblock '):
                            ip = text.split()[1]
                            result = unblock_ip(ip)
                            requests.post(f"{TELEGRAM_API}/sendMessage",
                                        data={'chat_id': chat_id, 'text': result})

                        elif text.startswith('/block '):
                            ip = text.split()[1]
                            result = block_ip(ip)
                            requests.post(f"{TELEGRAM_API}/sendMessage",
                                        data={'chat_id': chat_id, 'text': result})

            time.sleep(2)

        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    monitor_updates()