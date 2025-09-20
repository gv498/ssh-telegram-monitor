#!/usr/bin/env python3
import os
import sys
import json
import time
import uuid
import asyncio
import logging
import subprocess
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from telegram_group_manager import TelegramGroupManager
import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SSH2FAHandler:
    def __init__(self):
        self.sessions_file = '/var/lib/ssh-monitor/2fa_sessions.json'
        self.approved_file = '/var/lib/ssh-monitor/2fa_approved.json'
        self.timeout = 30  # seconds to wait for approval
        self.manager = TelegramGroupManager()

        # Create directories
        os.makedirs(os.path.dirname(self.sessions_file), exist_ok=True)

        # Load existing sessions
        self.sessions = self.load_sessions()
        self.approved_sessions = self.load_approved()

    def load_sessions(self) -> Dict:
        """Load pending 2FA sessions"""
        if os.path.exists(self.sessions_file):
            try:
                with open(self.sessions_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def save_sessions(self):
        """Save pending 2FA sessions"""
        with open(self.sessions_file, 'w') as f:
            json.dump(self.sessions, f, indent=2)

    def load_approved(self) -> Dict:
        """Load approved sessions"""
        if os.path.exists(self.approved_file):
            try:
                with open(self.approved_file, 'r') as f:
                    data = json.load(f)
                    # Clean old approvals (older than 1 hour)
                    cutoff = (datetime.now() - timedelta(hours=1)).timestamp()
                    cleaned = {k: v for k, v in data.items()
                              if v.get('timestamp', 0) > cutoff}
                    if len(cleaned) != len(data):
                        with open(self.approved_file, 'w') as f:
                            json.dump(cleaned, f, indent=2)
                    return cleaned
            except:
                pass
        return {}

    def save_approved(self):
        """Save approved sessions"""
        with open(self.approved_file, 'w') as f:
            json.dump(self.approved_sessions, f, indent=2)

    def get_location(self, ip: str) -> str:
        """Get geographic location for IP"""
        try:
            response = requests.get(f'http://ip-api.com/json/{ip}', timeout=2)
            data = response.json()
            if data.get('status') == 'success':
                return f"{data.get('city', 'לא ידוע')}, {data.get('country', 'לא ידוע')}"
        except:
            pass
        return "מיקום לא ידוע"

    async def request_2fa_approval(self, user: str, ip: str, ssh_pid: int) -> bool:
        """Request 2FA approval for SSH login"""
        # First check if IP is already blocked
        blocked_file = '/var/lib/ssh-monitor/blocked_ips.json'
        if os.path.exists(blocked_file):
            try:
                with open(blocked_file, 'r') as f:
                    blocked_ips = json.load(f)
                    if ip in blocked_ips:
                        logger.warning(f"Blocked IP {ip} attempted to connect - denying immediately")
                        # Kill the SSH session immediately
                        try:
                            subprocess.run(f"kill -9 {ssh_pid}", shell=True, check=False)
                        except:
                            pass
                        return False
            except:
                pass

        session_id = str(uuid.uuid4())[:8]
        location = self.get_location(ip)

        # Store session info
        self.sessions[session_id] = {
            'user': user,
            'ip': ip,
            'pid': ssh_pid,
            'timestamp': time.time(),
            'status': 'pending'
        }
        self.save_sessions()

        # Send 2FA request to Telegram
        message_id = await self.manager.send_2fa_request(user, ip, location, session_id)

        # Wait for approval
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            # Reload approved sessions
            self.approved_sessions = self.load_approved()

            # Check if session was approved
            if session_id in self.approved_sessions:
                status = self.approved_sessions[session_id].get('status')
                if status == 'approved':
                    logger.info(f"2FA approved for session {session_id}")
                    self.cleanup_session(session_id)
                    return True
                elif status in ['denied', 'blocked']:
                    logger.info(f"2FA {status} for session {session_id}")
                    if status == 'blocked':
                        self.block_ip(ip)
                    self.cleanup_session(session_id)
                    # Kill the SSH session immediately when denied
                    try:
                        subprocess.run(f"kill -9 {ssh_pid}", shell=True, check=False)
                        logger.info(f"Killed SSH session PID {ssh_pid} for denied login")
                    except:
                        pass
                    return False

            await asyncio.sleep(1)

        # Timeout - deny access and kill session
        logger.warning(f"2FA timeout for session {session_id}")
        self.cleanup_session(session_id)

        # Kill the SSH session on timeout
        try:
            subprocess.run(f"kill -9 {ssh_pid}", shell=True, check=False)
            logger.info(f"Killed SSH session PID {ssh_pid} due to timeout")
        except:
            pass

        # Send timeout notification
        await self.manager.send_general_alert(
            "תם הזמן לאימות דו-שלבי",
            f"ניסיון כניסה מ-{user}@{ip} נדחה עקב תום זמן המתנה",
            "warning"
        )

        return False

    def cleanup_session(self, session_id: str):
        """Remove session from pending"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            self.save_sessions()

    def block_ip(self, ip: str):
        """Block IP address"""
        commands = [
            f"iptables -A INPUT -s {ip} -j DROP",
            f"ip6tables -A INPUT -s {ip} -j DROP 2>/dev/null",
            f"ufw insert 1 deny from {ip} to any",
            f"fail2ban-client set sshd banip {ip}"
        ]

        for cmd in commands:
            try:
                subprocess.run(cmd, shell=True, check=False,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except:
                pass

    def approve_session(self, session_id: str, status: str = 'approved'):
        """Approve or deny a 2FA session"""
        self.approved_sessions[session_id] = {
            'status': status,
            'timestamp': time.time()
        }
        self.save_approved()

    def check_2fa_required(self, ip: str) -> bool:
        """Check if 2FA is required for this IP"""
        # Check if 2FA is enabled
        config_file = '/var/lib/ssh-monitor/2fa_config.json'
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    if not config.get('enabled', True):
                        return False
            except:
                pass

        # Check whitelist IPs
        whitelist = os.getenv('2FA_WHITELIST_IPS', '').split(',')
        if ip in whitelist:
            return False

        return True

async def handle_ssh_login(user: str, ip: str, pid: int):
    """Handle SSH login with 2FA"""
    handler = SSH2FAHandler()

    # Load configuration
    config_file = '/var/lib/ssh-monitor/2fa_config.json'
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            config = json.load(f)
            if not config.get('enabled', True):
                logger.info("2FA disabled globally")
                return True

    # Check per-user 2FA settings
    user_settings_file = '/var/lib/ssh-monitor/user_2fa_settings.json'
    if os.path.exists(user_settings_file):
        with open(user_settings_file, 'r') as f:
            user_settings = json.load(f)
            user_setting = user_settings.get(user, {})
            if not user_setting.get('2fa_enabled', True):
                logger.info(f"2FA disabled for user {user}")
                return True

    if handler.check_2fa_required(ip):
        logger.info(f"2FA required for {user}@{ip}")
        approved = await handler.request_2fa_approval(user, ip, pid)

        if not approved:
            # Kill SSH session
            try:
                subprocess.run(f"kill -9 {pid}", shell=True, check=False)
                logger.info(f"Killed SSH session PID {pid} for unapproved login")
            except:
                pass
            return False
    else:
        # No 2FA required, allow login
        logger.info(f"No 2FA required for {user}@{ip}")

    return True

if __name__ == "__main__":
    # Test mode or CLI usage
    if len(sys.argv) > 3:
        user = sys.argv[1]
        ip = sys.argv[2]
        pid = int(sys.argv[3])

        result = asyncio.run(handle_ssh_login(user, ip, pid))
        sys.exit(0 if result else 1)
    else:
        print("Usage: ssh_2fa_handler.py <user> <ip> <pid>")
        sys.exit(1)