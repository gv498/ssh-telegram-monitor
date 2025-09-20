#!/usr/bin/env python3
import os
import re
import json
import time
import asyncio
import logging
import subprocess
from datetime import datetime
from telegram_group_manager import TelegramGroupManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class FailedAttemptsMonitor:
    def __init__(self):
        self.manager = TelegramGroupManager()
        self.attempts_file = '/var/lib/ssh-monitor/failed_attempts.json'
        self.blocked_file = '/var/lib/ssh-monitor/blocked_ips.json'
        self.last_line_file = '/var/lib/ssh-monitor/last_auth_line'
        self.max_attempts = 3

        # Create directories
        os.makedirs(os.path.dirname(self.attempts_file), exist_ok=True)

        # Load data
        self.attempts = self.load_attempts()
        self.blocked_ips = self.load_blocked()
        self.last_line = self.load_last_line()

    def load_attempts(self) -> dict:
        """Load failed attempts data"""
        if os.path.exists(self.attempts_file):
            try:
                with open(self.attempts_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def save_attempts(self):
        """Save failed attempts data"""
        with open(self.attempts_file, 'w') as f:
            json.dump(self.attempts, f, indent=2)

    def load_blocked(self) -> dict:
        """Load blocked IPs data"""
        if os.path.exists(self.blocked_file):
            try:
                with open(self.blocked_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def save_blocked(self):
        """Save blocked IPs data"""
        with open(self.blocked_file, 'w') as f:
            json.dump(self.blocked_ips, f, indent=2)

    def load_last_line(self) -> int:
        """Load last processed line number"""
        if os.path.exists(self.last_line_file):
            try:
                with open(self.last_line_file, 'r') as f:
                    return int(f.read().strip())
            except:
                pass
        return 0

    def save_last_line(self, line_num: int):
        """Save last processed line number"""
        with open(self.last_line_file, 'w') as f:
            f.write(str(line_num))

    def block_ip(self, ip: str):
        """Block an IP address"""
        if ip in self.blocked_ips:
            return

        logger.info(f"Blocking IP: {ip}")

        # Execute blocking commands
        commands = [
            f"iptables -A INPUT -s {ip} -j DROP",
            f"ip6tables -A INPUT -s {ip} -j DROP 2>/dev/null",
            f"ufw insert 1 deny from {ip} to any",
            f"fail2ban-client set sshd banip {ip}",
            f"/usr/local/bin/kill_ssh_sessions.sh {ip}"
        ]

        for cmd in commands:
            try:
                subprocess.run(cmd, shell=True, check=False,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except:
                pass

        # Update blocked IPs
        self.blocked_ips[ip] = {
            'timestamp': datetime.now().isoformat(),
            'reason': 'max_failed_attempts'
        }
        self.save_blocked()

    async def process_failed_attempt(self, ip: str, user: str):
        """Process a failed login attempt"""
        # Skip local IPs
        if ip in ['127.0.0.1', 'localhost', '::1']:
            return

        # Update attempts count
        if ip not in self.attempts:
            self.attempts[ip] = {
                'count': 0,
                'users': [],
                'first_attempt': datetime.now().isoformat()
            }

        self.attempts[ip]['count'] += 1
        self.attempts[ip]['last_attempt'] = datetime.now().isoformat()

        if user and user not in self.attempts[ip]['users']:
            self.attempts[ip]['users'].append(user)

        self.save_attempts()

        count = self.attempts[ip]['count']

        # Check if should block
        should_block = count >= self.max_attempts and ip not in self.blocked_ips

        # Send notification
        await self.manager.send_failed_login(user or 'unknown', ip, count, should_block)

        # Block if needed
        if should_block:
            self.block_ip(ip)

            # Send general alert
            await self.manager.send_general_alert(
                "חסימה אוטומטית הופעלה",
                f"כתובת IP {ip} נחסמה אוטומטית לאחר {count} ניסיונות כושלים",
                "warning"
            )

    async def monitor_auth_log(self):
        """Monitor /var/log/auth.log for failed attempts"""
        auth_log = '/var/log/auth.log'

        # Patterns to match
        patterns = [
            r'Failed password for (?:invalid user )?(\S+) from (\S+)',
            r'Invalid user (\S+) from (\S+)',
            r'authentication failure.*ruser=(\S+).*rhost=(\S+)',
            r'Connection closed by authenticating user (\S+) (\S+)',
            r'Connection closed by (\S+) port \d+ \[preauth\]'
        ]

        while True:
            try:
                # Read auth.log
                with open(auth_log, 'r') as f:
                    lines = f.readlines()

                # Process new lines
                current_line = 0
                for line in lines[self.last_line:]:
                    current_line += 1

                    # Check each pattern
                    for pattern in patterns:
                        match = re.search(pattern, line)
                        if match:
                            # Extract user and IP
                            if len(match.groups()) >= 2:
                                user = match.group(1)
                                ip = match.group(2)
                            elif len(match.groups()) == 1:
                                user = None
                                ip = match.group(1)
                            else:
                                continue

                            # Process the failed attempt
                            await self.process_failed_attempt(ip, user)
                            break

                # Update last line
                self.save_last_line(self.last_line + current_line)
                self.last_line += current_line

            except Exception as e:
                logger.error(f"Error monitoring auth.log: {e}")

            # Wait before next check
            await asyncio.sleep(5)

    async def monitor_session_end(self):
        """Monitor for session end events"""
        # This would typically monitor wtmp or use PAM session close
        # For now, simplified implementation
        while True:
            try:
                # Check active sessions
                result = subprocess.run("who", capture_output=True, text=True)
                current_sessions = set(result.stdout.strip().split('\n'))

                # Compare with previous sessions (would need to track)
                # Send notifications for ended sessions

                await asyncio.sleep(30)
            except Exception as e:
                logger.error(f"Error monitoring sessions: {e}")
                await asyncio.sleep(30)

async def main():
    """Main function"""
    monitor = FailedAttemptsMonitor()

    # Run monitoring tasks
    tasks = [
        monitor.monitor_auth_log(),
        monitor.monitor_session_end()
    ]

    await asyncio.gather(*tasks)

if __name__ == "__main__":
    logger.info("Starting failed attempts monitor with group support...")
    asyncio.run(main())