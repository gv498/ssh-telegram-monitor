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

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SimpleFailedMonitor:
    def __init__(self):
        self.manager = TelegramGroupManager()
        self.attempts_file = '/var/lib/ssh-monitor/failed_attempts.json'
        self.blocked_file = '/var/lib/ssh-monitor/blocked_ips.json'
        self.last_line_file = '/var/lib/ssh-monitor/last_auth_line'
        self.max_attempts = 3

        # Create directories
        os.makedirs(os.path.dirname(self.attempts_file), exist_ok=True)

        # Load data
        self.attempts = self.load_json(self.attempts_file, {})
        self.blocked_ips = self.load_json(self.blocked_file, {})
        self.last_line = self.load_last_line()

        logger.info("Simple monitor started - will send ALL notifications immediately")

    def load_json(self, filepath, default):
        """Load JSON file safely"""
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    return json.load(f)
            except:
                pass
        return default

    def save_json(self, filepath, data):
        """Save JSON file safely"""
        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save {filepath}: {e}")

    def load_last_line(self):
        """Load last processed line"""
        if os.path.exists(self.last_line_file):
            try:
                with open(self.last_line_file, 'r') as f:
                    return int(f.read().strip())
            except:
                pass
        return 0

    def save_last_line(self, line_num):
        """Save last processed line"""
        try:
            with open(self.last_line_file, 'w') as f:
                f.write(str(line_num))
        except:
            pass

    def block_ip_now(self, ip):
        """Block IP immediately"""
        if ip in self.blocked_ips:
            return True

        logger.info(f"BLOCKING IP: {ip}")

        # Block with REJECT for immediate response
        commands = [
            f"iptables -I INPUT -s {ip} -p tcp --dport 22 -j REJECT --reject-with tcp-reset",
            f"fail2ban-client set sshd banip {ip}"
        ]

        success = False
        for cmd in commands:
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.returncode == 0:
                    success = True
                    logger.info(f"✓ Executed: {cmd}")
            except Exception as e:
                logger.error(f"✗ Failed: {cmd} - {e}")

        if success:
            self.blocked_ips[ip] = {
                'timestamp': datetime.now().isoformat(),
                'reason': 'max_failed_attempts'
            }
            self.save_json(self.blocked_file, self.blocked_ips)

            # Kill sessions
            subprocess.run(f"pkill -f 'sshd.*{ip}'", shell=True)

            logger.info(f"✓ IP {ip} BLOCKED SUCCESSFULLY")
            return True
        else:
            logger.error(f"✗ FAILED TO BLOCK IP {ip}")
            return False

    async def send_notification_now(self, ip, user, attempts, blocked=False):
        """Send notification immediately - no delays, no batching"""
        try:
            logger.info(f"Sending notification for {ip} (attempts: {attempts}, blocked: {blocked})")

            if blocked:
                # Send block notification
                await self.manager.send_ip_blocked_alert(ip, user or 'unknown', attempts)
                logger.info(f"✓ Block notification sent for {ip}")
            else:
                # Send failed attempt notification
                await self.manager.send_failed_login(user or 'unknown', ip, attempts, False)
                logger.info(f"✓ Failed attempt notification sent for {ip}")

            return True

        except Exception as e:
            logger.error(f"✗ Failed to send notification for {ip}: {e}")

            # Try simple notification as fallback
            try:
                message = f"⚠️ {ip} - {attempts} attempts"
                if blocked:
                    message = f"🚫 BLOCKED: {ip} after {attempts} attempts"

                await self.manager.send_general_alert("SSH Alert", message, "warning")
                logger.info(f"✓ Fallback notification sent for {ip}")
                return True

            except Exception as e2:
                logger.error(f"✗ Even fallback failed for {ip}: {e2}")
                return False

    async def process_failed_attempt(self, ip, user):
        """Process a failed attempt and send immediate notification"""
        # Skip local IPs
        if ip in ['127.0.0.1', 'localhost', '::1']:
            return

        # Skip if already blocked
        if ip in self.blocked_ips:
            logger.info(f"IP {ip} already blocked, skipping")
            return

        # Update attempts
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

        self.save_json(self.attempts_file, self.attempts)

        count = self.attempts[ip]['count']
        logger.info(f"Failed attempt #{count} from {ip} (user: {user or 'unknown'})")

        # ALWAYS send notification
        if count >= self.max_attempts:
            # Block and notify
            if self.block_ip_now(ip):
                await self.send_notification_now(ip, user, count, blocked=True)
            else:
                # Even if block fails, send notification
                await self.send_notification_now(ip, user, count, blocked=False)
        else:
            # Just notify
            await self.send_notification_now(ip, user, count, blocked=False)

    async def monitor_auth_log(self):
        """Monitor auth.log and send immediate notifications"""
        auth_log = '/var/log/auth.log'

        # Patterns to detect failed attempts
        patterns = [
            r'Failed password for (?:invalid user )?(\S+) from (\S+)',
            r'Invalid user (\S+) from (\S+)',
            r'authentication failure.*ruser=(\S+).*rhost=(\S+)',
            r'Connection closed by authenticating user (\S+) (\S+)',
            r'Connection closed by (\S+) port \d+ \[preauth\]'
        ]

        logger.info("Starting to monitor /var/log/auth.log")

        while True:
            try:
                # Read new lines
                with open(auth_log, 'r') as f:
                    lines = f.readlines()

                new_lines = lines[self.last_line:]

                if new_lines:
                    logger.info(f"Processing {len(new_lines)} new lines")

                for line in new_lines:
                    for pattern in patterns:
                        match = re.search(pattern, line)
                        if match:
                            groups = match.groups()

                            if len(groups) == 2:
                                user = groups[0]
                                ip = groups[1]
                            elif len(groups) == 1:
                                user = None
                                ip = groups[0]
                            else:
                                continue

                            # Skip invalid IPs
                            if not ip or ip == 'port' or ':' in ip:
                                continue

                            logger.info(f"Detected failed attempt from {ip}")

                            # Process immediately
                            await self.process_failed_attempt(ip, user)
                            break

                # Update last line
                if new_lines:
                    self.last_line += len(new_lines)
                    self.save_last_line(self.last_line)

            except Exception as e:
                logger.error(f"Error monitoring auth.log: {e}")

            # Check every 2 seconds
            await asyncio.sleep(2)

    async def run(self):
        """Main run function"""
        logger.info("="*50)
        logger.info("SIMPLE MONITOR STARTED")
        logger.info("Will send ALL notifications immediately")
        logger.info("="*50)

        await self.monitor_auth_log()

async def main():
    monitor = SimpleFailedMonitor()
    await monitor.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Monitor stopped by user")
    except Exception as e:
        logger.error(f"Monitor crashed: {e}")
        import traceback
        traceback.print_exc()