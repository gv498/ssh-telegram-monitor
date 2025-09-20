#!/usr/bin/env python3
import os
import re
import json
import time
import asyncio
import logging
import subprocess
from datetime import datetime, timedelta
from collections import defaultdict
from asyncio import Queue, Semaphore
from telegram_group_manager import TelegramGroupManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/ssh-monitor/failed_attempts.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class OptimizedFailedAttemptsMonitor:
    def __init__(self):
        self.manager = TelegramGroupManager()
        self.attempts_file = '/var/lib/ssh-monitor/failed_attempts.json'
        self.blocked_file = '/var/lib/ssh-monitor/blocked_ips.json'
        self.last_line_file = '/var/lib/ssh-monitor/last_auth_line'
        self.max_attempts = 3

        # Async processing
        self.process_queue = Queue(maxsize=1000)
        self.notification_queue = Queue(maxsize=100)
        self.block_semaphore = Semaphore(5)  # Max 5 concurrent blocks

        # Batch processing
        self.batch_interval = 5  # seconds
        self.pending_notifications = defaultdict(dict)
        self.last_notification = defaultdict(float)
        self.notification_cooldown = 30  # seconds between notifications for same IP

        # Create directories
        os.makedirs(os.path.dirname(self.attempts_file), exist_ok=True)
        os.makedirs('/var/log/ssh-monitor', exist_ok=True)

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
        try:
            with open(self.attempts_file, 'w') as f:
                json.dump(self.attempts, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save attempts: {e}")

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
        try:
            with open(self.blocked_file, 'w') as f:
                json.dump(self.blocked_ips, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save blocked IPs: {e}")

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
        try:
            with open(self.last_line_file, 'w') as f:
                f.write(str(line_num))
        except Exception as e:
            logger.error(f"Failed to save last line: {e}")

    async def block_ip_async(self, ip: str):
        """Block an IP address asynchronously with semaphore"""
        async with self.block_semaphore:
            if ip in self.blocked_ips:
                logger.info(f"IP {ip} already blocked, skipping")
                return True

            logger.info(f"Blocking IP: {ip}")

            # Execute blocking commands
            commands = [
                f"iptables -I INPUT -s {ip} -p tcp --dport 22 -j REJECT --reject-with tcp-reset",
                f"fail2ban-client set sshd banip {ip}",
            ]

            success = False
            for cmd in commands:
                try:
                    proc = await asyncio.create_subprocess_shell(
                        cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await proc.communicate()
                    if proc.returncode == 0:
                        success = True
                        logger.info(f"Successfully executed: {cmd}")
                    else:
                        logger.error(f"Command failed: {cmd} - {stderr.decode()}")
                except Exception as e:
                    logger.error(f"Failed to execute {cmd}: {e}")

            if success:
                # Update blocked IPs
                self.blocked_ips[ip] = {
                    'timestamp': datetime.now().isoformat(),
                    'reason': 'max_failed_attempts',
                    'attempts': self.attempts.get(ip, {}).get('count', self.max_attempts)
                }
                self.save_blocked()

                # Kill active sessions
                try:
                    await asyncio.create_subprocess_shell(
                        f"/usr/local/bin/kill_ssh_sessions.sh {ip}",
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL
                    )
                except:
                    pass

                logger.info(f"IP {ip} successfully blocked")
                return True
            else:
                logger.error(f"Failed to block IP {ip}")
                return False

    async def process_failed_attempt_async(self, ip: str, user: str, timestamp: float):
        """Process a failed login attempt asynchronously"""
        # Skip local IPs
        if ip in ['127.0.0.1', 'localhost', '::1']:
            return

        # Skip if already blocked
        if ip in self.blocked_ips:
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
        if count >= self.max_attempts:
            # Block immediately
            success = await self.block_ip_async(ip)

            if success:
                # Queue notification
                await self.notification_queue.put({
                    'type': 'blocked',
                    'ip': ip,
                    'user': user or 'unknown',
                    'attempts': count
                })
        elif count % 3 == 0 or count == 1:  # Notify on 1st, 3rd, 6th, etc.
            # Check cooldown
            current_time = time.time()
            if current_time - self.last_notification[ip] > self.notification_cooldown:
                await self.notification_queue.put({
                    'type': 'failed',
                    'ip': ip,
                    'user': user or 'unknown',
                    'attempts': count
                })
                self.last_notification[ip] = current_time

    async def process_queue_worker(self):
        """Worker to process queued attempts"""
        while True:
            try:
                item = await self.process_queue.get()
                await self.process_failed_attempt_async(
                    item['ip'],
                    item['user'],
                    item['timestamp']
                )
            except Exception as e:
                logger.error(f"Error processing queue item: {e}")
            finally:
                self.process_queue.task_done()

    async def notification_worker(self):
        """Worker to send notifications in batches"""
        while True:
            notifications = []
            deadline = asyncio.get_event_loop().time() + self.batch_interval

            # Collect notifications for batch_interval seconds
            while asyncio.get_event_loop().time() < deadline:
                try:
                    timeout = deadline - asyncio.get_event_loop().time()
                    if timeout > 0:
                        notification = await asyncio.wait_for(
                            self.notification_queue.get(),
                            timeout=timeout
                        )
                        notifications.append(notification)
                except asyncio.TimeoutError:
                    break
                except Exception as e:
                    logger.error(f"Error collecting notifications: {e}")
                    break

            # Send batched notifications
            if notifications:
                await self.send_batch_notifications(notifications)

    async def send_batch_notifications(self, notifications):
        """Send notifications in batch"""
        blocked_ips = []
        failed_attempts = defaultdict(lambda: {'count': 0, 'users': set()})

        for notif in notifications:
            if notif['type'] == 'blocked':
                blocked_ips.append((notif['ip'], notif['user'], notif['attempts']))
            else:
                failed_attempts[notif['ip']]['count'] = notif['attempts']
                failed_attempts[notif['ip']]['users'].add(notif['user'])

        # Send block notifications
        for ip, user, attempts in blocked_ips:
            try:
                await self.manager.send_ip_blocked_alert(ip, user, attempts)
                logger.info(f"Sent block notification for {ip}")
            except Exception as e:
                logger.error(f"Failed to send block notification for {ip}: {e}")

        # Send failed attempt notifications (grouped)
        if failed_attempts:
            for ip, data in failed_attempts.items():
                try:
                    users = ', '.join(data['users'])
                    await self.manager.send_failed_login(
                        users, ip, data['count'], False
                    )
                    logger.info(f"Sent failed notification for {ip}")
                except Exception as e:
                    logger.error(f"Failed to send notification for {ip}: {e}")

    async def monitor_auth_log(self):
        """Monitor /var/log/auth.log for failed attempts"""
        auth_log = '/var/log/auth.log'

        # Patterns to match
        patterns = [
            (r'Failed password for (?:invalid user )?(\S+) from (\S+)', 2),
            (r'Invalid user (\S+) from (\S+)', 2),
            (r'Connection closed by authenticating user (\S+) (\S+)', 2),
            (r'Connection closed by (\S+) port \d+ \[preauth\]', 1),
        ]

        while True:
            try:
                # Read new lines
                with open(auth_log, 'r') as f:
                    lines = f.readlines()

                new_lines = lines[self.last_line:]

                for i, line in enumerate(new_lines):
                    for pattern, group_count in patterns:
                        match = re.search(pattern, line)
                        if match:
                            if group_count == 2:
                                user = match.group(1)
                                ip = match.group(2)
                            else:
                                user = None
                                ip = match.group(1)

                            # Add to queue if not full
                            if not self.process_queue.full():
                                await self.process_queue.put({
                                    'ip': ip,
                                    'user': user,
                                    'timestamp': time.time()
                                })
                            else:
                                logger.warning(f"Queue full, dropping attempt from {ip}")
                            break

                # Update last line
                self.last_line += len(new_lines)
                self.save_last_line(self.last_line)

            except Exception as e:
                logger.error(f"Error monitoring auth.log: {e}")

            await asyncio.sleep(2)  # Check every 2 seconds

    async def cleanup_old_attempts(self):
        """Clean up old attempts periodically"""
        while True:
            try:
                current_time = datetime.now()
                cutoff_time = current_time - timedelta(hours=24)

                # Clean old attempts
                for ip in list(self.attempts.keys()):
                    last_attempt = self.attempts[ip].get('last_attempt')
                    if last_attempt:
                        last_time = datetime.fromisoformat(last_attempt)
                        if last_time < cutoff_time:
                            del self.attempts[ip]
                            logger.info(f"Cleaned old attempts for {ip}")

                self.save_attempts()

            except Exception as e:
                logger.error(f"Error cleaning attempts: {e}")

            await asyncio.sleep(3600)  # Run every hour

    async def main(self):
        """Main function to run all workers"""
        logger.info("Starting optimized failed attempts monitor...")

        # Start workers
        workers = [
            self.monitor_auth_log(),
            self.process_queue_worker(),
            self.process_queue_worker(),  # 2 queue workers
            self.process_queue_worker(),  # 3 queue workers for parallel processing
            self.notification_worker(),
            self.cleanup_old_attempts()
        ]

        await asyncio.gather(*workers)

async def run():
    monitor = OptimizedFailedAttemptsMonitor()
    await monitor.main()

if __name__ == "__main__":
    asyncio.run(run())