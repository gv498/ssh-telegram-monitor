#!/usr/bin/env python3
import os
import time
import json
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

class SSHSessionMonitor:
    def __init__(self):
        self.manager = TelegramGroupManager()
        self.sessions_file = '/var/lib/ssh-monitor/active_sessions.json'
        self.check_interval = 10  # seconds

        # Create directory if not exists
        os.makedirs(os.path.dirname(self.sessions_file), exist_ok=True)

        # Load existing sessions
        self.active_sessions = self.load_sessions()

    def load_sessions(self) -> dict:
        """Load active sessions from file"""
        if os.path.exists(self.sessions_file):
            try:
                with open(self.sessions_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def save_sessions(self):
        """Save active sessions to file"""
        with open(self.sessions_file, 'w') as f:
            json.dump(self.active_sessions, f, indent=2)

    def get_current_sessions(self) -> dict:
        """Get currently active SSH sessions"""
        sessions = {}
        try:
            # Use who command to get active sessions
            result = subprocess.run("who", capture_output=True, text=True)
            if result.stdout:
                for line in result.stdout.strip().split('\n'):
                    if 'pts/' in line or 'tty' in line:
                        parts = line.split()
                        if len(parts) >= 5:
                            user = parts[0]
                            terminal = parts[1]
                            login_time = f"{parts[2]} {parts[3]}"
                            ip = parts[-1].strip('()')

                            # Create unique session ID
                            session_id = f"{user}_{terminal}_{ip}_{login_time}"
                            sessions[session_id] = {
                                'user': user,
                                'terminal': terminal,
                                'ip': ip if ip and not ip.startswith(':') else 'local',
                                'login_time': login_time,
                                'start_timestamp': time.time()
                            }

            # Also check with ss command for SSH connections
            result = subprocess.run("ss -tnp | grep ':22 '", shell=True, capture_output=True, text=True)
            if result.stdout:
                for line in result.stdout.strip().split('\n'):
                    if 'ESTAB' in line:
                        parts = line.split()
                        if len(parts) >= 5:
                            # Extract IP from the connection
                            remote = parts[4]
                            if ':' in remote:
                                ip = remote.rsplit(':', 1)[0]
                                # Try to match with who output or create new entry
                                for sid, session in sessions.items():
                                    if session['ip'] == 'local' or session['ip'] == '':
                                        session['ip'] = ip
                                        break
        except Exception as e:
            logger.error(f"Error getting current sessions: {e}")

        return sessions

    def calculate_duration(self, start_time: float) -> str:
        """Calculate session duration"""
        duration = int(time.time() - start_time)
        hours = duration // 3600
        minutes = (duration % 3600) // 60
        seconds = duration % 60

        if hours > 0:
            return f"{hours} שעות, {minutes} דקות"
        elif minutes > 0:
            return f"{minutes} דקות, {seconds} שניות"
        else:
            return f"{seconds} שניות"

    async def check_ended_sessions(self):
        """Check for sessions that have ended"""
        current_sessions = self.get_current_sessions()

        # Find sessions that ended
        ended_sessions = []
        for session_id, session_data in self.active_sessions.items():
            if session_id not in current_sessions:
                ended_sessions.append((session_id, session_data))

        # Send notifications for ended sessions
        for session_id, session_data in ended_sessions:
            user = session_data.get('user', 'unknown')
            ip = session_data.get('ip', 'unknown')
            start_time = session_data.get('start_timestamp', time.time())
            duration = self.calculate_duration(start_time)

            # Skip local sessions
            if ip not in ['local', '127.0.0.1', '::1', '', 'unknown']:
                logger.info(f"Session ended: {user}@{ip}, duration: {duration}")
                try:
                    await self.manager.send_session_end(user, ip, duration)
                except Exception as e:
                    logger.error(f"Error sending session end notification: {e}")

            # Remove from active sessions
            del self.active_sessions[session_id]

        # Add new sessions
        for session_id, session_data in current_sessions.items():
            if session_id not in self.active_sessions:
                # Preserve the original timestamp if this is a new detection
                if 'start_timestamp' not in session_data:
                    session_data['start_timestamp'] = time.time()
                self.active_sessions[session_id] = session_data
                logger.info(f"New session detected: {session_data.get('user')}@{session_data.get('ip')}")

        # Save updated sessions
        self.save_sessions()

    async def monitor_loop(self):
        """Main monitoring loop"""
        logger.info("Starting SSH session monitor...")

        while True:
            try:
                await self.check_ended_sessions()
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")

            await asyncio.sleep(self.check_interval)

async def main():
    """Main function"""
    monitor = SSHSessionMonitor()
    await monitor.monitor_loop()

if __name__ == "__main__":
    asyncio.run(main())