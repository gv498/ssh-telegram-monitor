#!/usr/bin/env python3
import os
import sys
import json
import asyncio
import logging
import psutil
import subprocess
import requests
from datetime import datetime
from telegram_group_manager import TelegramGroupManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SSHNotifier:
    def __init__(self):
        self.manager = TelegramGroupManager()

    def get_system_info(self) -> dict:
        """Get system information"""
        try:
            return {
                'cpu': psutil.cpu_percent(interval=1),
                'memory': psutil.virtual_memory().percent,
                'disk': psutil.disk_usage('/').percent,
                'load': os.getloadavg()[0]
            }
        except:
            return {
                'cpu': 'N/A',
                'memory': 'N/A',
                'disk': 'N/A',
                'load': 'N/A'
            }

    def get_location(self, ip: str) -> str:
        """Get geographic location for IP"""
        try:
            response = requests.get(f'http://ip-api.com/json/{ip}', timeout=2)
            data = response.json()
            if data.get('status') == 'success':
                city = data.get('city', 'לא ידוע')
                country = data.get('country', 'לא ידוע')
                isp = data.get('isp', 'לא ידוע')
                return f"{city}, {country} (ספק: {isp})"
        except:
            pass
        return "מיקום לא ידוע"

    def get_active_sessions(self) -> int:
        """Get count of active SSH sessions"""
        try:
            result = subprocess.run("who | grep -c pts", shell=True,
                                  capture_output=True, text=True)
            return int(result.stdout.strip() or 0)
        except:
            return 0

    async def notify_login(self):
        """Send login notification to appropriate topic"""
        try:
            # Get environment variables
            user = os.environ.get('PAM_USER', 'unknown')
            ip = os.environ.get('PAM_RHOST', 'unknown')
            service = os.environ.get('PAM_SERVICE', 'ssh')
            pam_type = os.environ.get('PAM_TYPE', 'unknown')

            # Skip local connections
            if ip in ['127.0.0.1', 'localhost', '::1']:
                logger.info(f"Skipping notification for local connection: {user}@{ip}")
                return

            # Get additional info
            location = self.get_location(ip)
            system_info = self.get_system_info()
            active_sessions = self.get_active_sessions()

            # Prepare details
            details = {
                'cpu': system_info['cpu'],
                'memory': system_info['memory'],
                'disk': system_info['disk'],
                'sessions': active_sessions
            }

            # Send notification to successful_logins topic
            await self.manager.send_successful_login(user, ip, location, details)

            logger.info(f"Sent login notification for {user}@{ip}")

        except Exception as e:
            logger.error(f"Error sending notification: {e}")

async def main():
    """Main function"""
    notifier = SSHNotifier()
    await notifier.notify_login()

if __name__ == "__main__":
    asyncio.run(main())