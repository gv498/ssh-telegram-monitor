#!/usr/bin/env python3
import os
import json
import asyncio
import logging
import subprocess
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
from dotenv import load_dotenv
from ssh_2fa_handler import SSH2FAHandler
from telegram_group_manager import TelegramGroupManager

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CallbackHandler:
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.group_id = int(os.getenv('TELEGRAM_GROUP_ID', '-1003066710155'))
        self.manager = TelegramGroupManager()
        self.twofa_handler = SSH2FAHandler()

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries from inline buttons"""
        query = update.callback_query
        await query.answer()

        data = query.data
        logger.info(f"Received callback: {data}")

        # Parse callback data
        parts = data.split(':')
        action = parts[0]

        if action == 'block':
            ip = parts[1]
            await self.block_ip(query, ip)

        elif action == 'unblock':
            ip = parts[1]
            await self.unblock_ip(query, ip)

        elif action == 'sessions':
            ip = parts[1]
            await self.show_sessions(query, ip)

        elif action == 'history':
            ip = parts[1]
            await self.show_history(query, ip)

        elif action == '2fa_approve':
            session_id = parts[1]
            ip = parts[2]
            await self.approve_2fa(query, session_id, ip, 'approved')

        elif action == '2fa_deny':
            session_id = parts[1]
            ip = parts[2]
            await self.approve_2fa(query, session_id, ip, 'denied')

        elif action == '2fa_block':
            session_id = parts[1]
            ip = parts[2]
            await self.approve_2fa(query, session_id, ip, 'blocked')

    async def block_ip(self, query, ip: str):
        """Block an IP address"""
        try:
            # Execute blocking commands
            commands = [
                f"iptables -A INPUT -s {ip} -j DROP",
                f"ip6tables -A INPUT -s {ip} -j DROP 2>/dev/null",
                f"ufw insert 1 deny from {ip} to any",
                f"fail2ban-client set sshd banip {ip}",
                f"/usr/local/bin/kill_ssh_sessions.sh {ip}"
            ]

            for cmd in commands:
                subprocess.run(cmd, shell=True, check=False,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Update blocked IPs database
            blocked_file = '/var/lib/ssh-monitor/blocked_ips.json'
            blocked_ips = {}
            if os.path.exists(blocked_file):
                try:
                    with open(blocked_file, 'r') as f:
                        blocked_ips = json.load(f)
                except:
                    pass

            blocked_ips[ip] = {
                'timestamp': str(datetime.now()),
                'blocked_by': 'telegram_callback'
            }

            with open(blocked_file, 'w') as f:
                json.dump(blocked_ips, f, indent=2)

            await query.edit_message_text(f"✅ Successfully blocked IP: {ip}")

            # Send notification to general topic
            await self.manager.send_general_alert(
                "IP Blocked",
                f"IP address {ip} has been blocked via Telegram",
                "warning"
            )

        except Exception as e:
            logger.error(f"Error blocking IP {ip}: {e}")
            await query.edit_message_text(f"❌ Failed to block IP: {ip}")

    async def unblock_ip(self, query, ip: str):
        """Unblock an IP address"""
        try:
            # Execute unblocking script
            subprocess.run(f"/usr/local/bin/unblock_ip_complete.sh {ip}",
                          shell=True, check=False,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Update blocked IPs database
            blocked_file = '/var/lib/ssh-monitor/blocked_ips.json'
            if os.path.exists(blocked_file):
                try:
                    with open(blocked_file, 'r') as f:
                        blocked_ips = json.load(f)
                    if ip in blocked_ips:
                        del blocked_ips[ip]
                    with open(blocked_file, 'w') as f:
                        json.dump(blocked_ips, f, indent=2)
                except:
                    pass

            await query.edit_message_text(f"✅ Successfully unblocked IP: {ip}")

            # Send notification to general topic
            await self.manager.send_general_alert(
                "IP Unblocked",
                f"IP address {ip} has been unblocked via Telegram",
                "success"
            )

        except Exception as e:
            logger.error(f"Error unblocking IP {ip}: {e}")
            await query.edit_message_text(f"❌ Failed to unblock IP: {ip}")

    async def show_sessions(self, query, ip: str):
        """Show active SSH sessions from an IP"""
        try:
            result = subprocess.run(f"ss -tnp | grep ':22' | grep '{ip}'",
                                  shell=True, capture_output=True, text=True)
            sessions = result.stdout.strip()

            if sessions:
                message = f"Active SSH sessions from {ip}:\n\n{sessions}"
            else:
                message = f"No active SSH sessions from {ip}"

            await query.edit_message_text(message)

        except Exception as e:
            logger.error(f"Error showing sessions: {e}")
            await query.edit_message_text("❌ Failed to get session information")

    async def show_history(self, query, ip: str):
        """Show login history for an IP"""
        try:
            # Get attempt history
            attempts_file = '/var/lib/ssh-monitor/failed_attempts.json'
            attempts = {}
            if os.path.exists(attempts_file):
                try:
                    with open(attempts_file, 'r') as f:
                        attempts = json.load(f)
                except:
                    pass

            if ip in attempts:
                count = attempts[ip].get('count', 0)
                last = attempts[ip].get('last_attempt', 'Unknown')
                message = f"Login history for {ip}:\n\nFailed attempts: {count}\nLast attempt: {last}"
            else:
                message = f"No failed login attempts recorded for {ip}"

            await query.edit_message_text(message)

        except Exception as e:
            logger.error(f"Error showing history: {e}")
            await query.edit_message_text("❌ Failed to get history information")

    async def approve_2fa(self, query, session_id: str, ip: str, status: str):
        """Handle 2FA approval/denial"""
        try:
            # Update session status
            self.twofa_handler.approve_session(session_id, status)

            # Update message
            emoji = {'approved': '✅', 'denied': '❌', 'blocked': '🚫'}.get(status, '❓')
            action_text = {'approved': 'approved', 'denied': 'denied', 'blocked': 'denied and blocked'}.get(status)

            await query.edit_message_text(
                f"{emoji} Login from {ip} has been {action_text}\n"
                f"Session ID: {session_id}"
            )

            # Send notification to general topic
            await self.manager.send_general_alert(
                f"2FA {status.capitalize()}",
                f"Login attempt from {ip} was {action_text}",
                "success" if status == 'approved' else "warning"
            )

            # If blocked, execute blocking
            if status == 'blocked':
                await self.block_ip(query, ip)

        except Exception as e:
            logger.error(f"Error handling 2FA response: {e}")
            await query.edit_message_text("❌ Failed to process 2FA response")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        await update.message.reply_text(
            "🔐 SSH Telegram Monitor with 2FA Active\n\n"
            "This bot monitors SSH access and provides 2FA authentication.\n"
            "Configure group ID and topics in your .env file."
        )

    async def init_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /init command to create topics"""
        if update.effective_chat.id != self.group_id:
            await update.message.reply_text("This command must be run in the configured group.")
            return

        await update.message.reply_text("Initializing group topics...")
        success = await self.manager.initialize()

        if success:
            await update.message.reply_text(
                "✅ Group initialized successfully!\n"
                "Topics have been created for different notification types."
            )
        else:
            await update.message.reply_text(
                "❌ Failed to initialize group.\n"
                "Please ensure the bot is admin and group has forums enabled."
            )

def main():
    """Main function to run the bot"""
    handler = CallbackHandler()

    # Create application
    application = Application.builder().token(handler.bot_token).build()

    # Add handlers
    application.add_handler(CallbackQueryHandler(handler.handle_callback))
    application.add_handler(CommandHandler("start", handler.start_command))
    application.add_handler(CommandHandler("init", handler.init_command))

    # Run bot
    logger.info("Starting Telegram callback handler...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    from datetime import datetime
    main()