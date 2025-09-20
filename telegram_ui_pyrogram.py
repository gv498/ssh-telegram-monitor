#!/usr/bin/env python3
import os
import sys
import json
import pwd
import grp
import subprocess
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    Message
)
from pyrogram.errors import MessageNotModified
import re

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TelegramUIManager:
    def __init__(self):
        # Load environment variables
        from dotenv import load_dotenv
        load_dotenv()

        self.bot_token = os.getenv('BOT_TOKEN')
        self.group_id = int(os.getenv('GROUP_ID', '-1003066710155'))
        self.admin_chat_id = int(os.getenv('TELEGRAM_CHAT_ID', '6793022306'))

        # Initialize Pyrogram client
        # For bot tokens, we can use default test API credentials
        self.app = Client(
            "ui_manager",
            bot_token=self.bot_token,
            api_id=2040,
            api_hash="b18441a1ff607e10a989891a5462e627"
        )

        # Data files
        self.user_2fa_file = '/var/lib/ssh-monitor/user_2fa_settings.json'
        self.global_settings_file = '/var/lib/ssh-monitor/global_settings.json'
        self.blocked_ips_file = '/var/lib/ssh-monitor/blocked_ips.json'
        self.user_f2b_file = '/var/lib/ssh-monitor/user_f2b_settings.json'

        # Ensure directories exist
        os.makedirs('/var/lib/ssh-monitor', exist_ok=True)

        # Load settings
        self.load_settings()

        # Register handlers
        self.register_handlers()

    def load_settings(self):
        """Load all settings from files"""
        # Load user 2FA settings
        if os.path.exists(self.user_2fa_file):
            with open(self.user_2fa_file, 'r') as f:
                self.user_2fa_settings = json.load(f)
        else:
            self.user_2fa_settings = {}

        # Load global settings
        if os.path.exists(self.global_settings_file):
            with open(self.global_settings_file, 'r') as f:
                self.global_settings = json.load(f)
        else:
            self.global_settings = {
                'global_2fa': True,
                'max_attempts': 3,
                'block_duration': 3600
            }

        # Load user F2B settings
        if os.path.exists(self.user_f2b_file):
            with open(self.user_f2b_file, 'r') as f:
                self.user_f2b_settings = json.load(f)
        else:
            self.user_f2b_settings = {}

    def save_settings(self):
        """Save all settings to files"""
        with open(self.user_2fa_file, 'w') as f:
            json.dump(self.user_2fa_settings, f, indent=2)

        with open(self.global_settings_file, 'w') as f:
            json.dump(self.global_settings, f, indent=2)

        with open(self.user_f2b_file, 'w') as f:
            json.dump(self.user_f2b_settings, f, indent=2)

    def get_system_users(self) -> List[Dict]:
        """Get all system users with login shell"""
        users = []
        try:
            for user in pwd.getpwall():
                # Skip system users and users without login shell
                if user.pw_uid >= 1000 or user.pw_name == 'root':
                    if '/bin/false' not in user.pw_shell and '/nologin' not in user.pw_shell:
                        users.append({
                            'username': user.pw_name,
                            'uid': user.pw_uid,
                            'home': user.pw_dir,
                            'shell': user.pw_shell,
                            '2fa_enabled': self.user_2fa_settings.get(user.pw_name, {}).get('2fa_enabled', True),
                            'f2b_enabled': self.user_f2b_settings.get(user.pw_name, {}).get('f2b_enabled', True)
                        })
        except Exception as e:
            logger.error(f"Error getting system users: {e}")

        return sorted(users, key=lambda x: x['username'])

    def get_ssh_keys(self, username: str) -> List[str]:
        """Get SSH authorized keys for a user"""
        keys = []
        try:
            user = pwd.getpwnam(username)
            authorized_keys_path = os.path.join(user.pw_dir, '.ssh', 'authorized_keys')

            if os.path.exists(authorized_keys_path):
                with open(authorized_keys_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            # Extract key comment/identifier
                            parts = line.split()
                            if len(parts) >= 3:
                                key_info = f"{parts[0][:15]}... {parts[-1]}"
                            else:
                                key_info = line[:50] + "..."
                            keys.append(key_info)
        except Exception as e:
            logger.error(f"Error getting SSH keys for {username}: {e}")

        return keys

    def add_ssh_key(self, username: str, key: str) -> bool:
        """Add SSH key for a user"""
        try:
            user = pwd.getpwnam(username)
            ssh_dir = os.path.join(user.pw_dir, '.ssh')
            authorized_keys_path = os.path.join(ssh_dir, 'authorized_keys')

            # Create .ssh directory if it doesn't exist
            if not os.path.exists(ssh_dir):
                os.makedirs(ssh_dir, mode=0o700)
                os.chown(ssh_dir, user.pw_uid, user.pw_gid)

            # Add key to authorized_keys
            with open(authorized_keys_path, 'a') as f:
                f.write(f"\n{key}\n")

            # Set proper permissions
            os.chmod(authorized_keys_path, 0o600)
            os.chown(authorized_keys_path, user.pw_uid, user.pw_gid)

            return True
        except Exception as e:
            logger.error(f"Error adding SSH key for {username}: {e}")
            return False

    def delete_ssh_key(self, username: str, key_pattern: str) -> bool:
        """Delete SSH key for a user"""
        try:
            user = pwd.getpwnam(username)
            authorized_keys_path = os.path.join(user.pw_dir, '.ssh', 'authorized_keys')

            if os.path.exists(authorized_keys_path):
                with open(authorized_keys_path, 'r') as f:
                    lines = f.readlines()

                # Filter out the key to delete
                new_lines = [l for l in lines if key_pattern not in l]

                with open(authorized_keys_path, 'w') as f:
                    f.writelines(new_lines)

                return len(new_lines) < len(lines)
        except Exception as e:
            logger.error(f"Error deleting SSH key for {username}: {e}")

        return False

    def create_user(self, username: str, password: Optional[str] = None) -> Tuple[bool, str]:
        """Create a new system user"""
        try:
            # Check if user already exists
            try:
                pwd.getpwnam(username)
                return False, "משתמש כבר קיים"
            except KeyError:
                pass

            # Create user
            cmd = f"useradd -m -s /bin/bash {username}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            if result.returncode != 0:
                return False, f"שגיאה ביצירת משתמש: {result.stderr}"

            # Set password if provided
            if password:
                cmd = f"echo '{username}:{password}' | chpasswd"
                subprocess.run(cmd, shell=True)

            # Create SSH directory
            user = pwd.getpwnam(username)
            ssh_dir = os.path.join(user.pw_dir, '.ssh')
            os.makedirs(ssh_dir, mode=0o700, exist_ok=True)
            os.chown(ssh_dir, user.pw_uid, user.pw_gid)

            return True, "משתמש נוצר בהצלחה"
        except Exception as e:
            logger.error(f"Error creating user {username}: {e}")
            return False, str(e)

    def delete_user(self, username: str) -> Tuple[bool, str]:
        """Delete a system user"""
        try:
            # Don't allow deleting root
            if username == 'root':
                return False, "לא ניתן למחוק את משתמש root"

            # Check if user exists
            try:
                pwd.getpwnam(username)
            except KeyError:
                return False, "משתמש לא קיים"

            # Delete user and home directory
            cmd = f"userdel -r {username}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            if result.returncode != 0:
                return False, f"שגיאה במחיקת משתמש: {result.stderr}"

            # Remove from settings
            if username in self.user_2fa_settings:
                del self.user_2fa_settings[username]
            if username in self.user_f2b_settings:
                del self.user_f2b_settings[username]
            self.save_settings()

            return True, "משתמש נמחק בהצלחה"
        except Exception as e:
            logger.error(f"Error deleting user {username}: {e}")
            return False, str(e)

    def register_handlers(self):
        """Register all message and callback handlers"""

        @self.app.on_message(filters.command("menu"))
        async def menu_command(client, message: Message):
            await self.show_main_menu(message)

        @self.app.on_message(filters.command("adduser"))
        async def adduser_command(client, message: Message):
            await self.handle_adduser_command(message)

        @self.app.on_message(filters.command("addkey"))
        async def addkey_command(client, message: Message):
            await self.handle_addkey_command(message)

        @self.app.on_callback_query()
        async def callback_handler(client, query: CallbackQuery):
            await self.handle_callback(query)

    async def show_main_menu(self, message: Message):
        """Show main menu"""
        # Check if user is authorized
        chat_id = message.chat.id
        if chat_id != self.group_id and chat_id != self.admin_chat_id:
            await message.reply_text("❌ אין לך הרשאה להשתמש בפקודה זו")
            return

        keyboard = [
            [InlineKeyboardButton("🎛 לוח בקרה", callback_data="menu_dashboard")],
            [InlineKeyboardButton("👥 ניהול משתמשים", callback_data="menu_users")],
            [InlineKeyboardButton("🔐 הגדרות אבטחה", callback_data="menu_security")],
            [InlineKeyboardButton("🚫 ניהול חסימות", callback_data="menu_blocks")],
            [InlineKeyboardButton("📊 סטטיסטיקות", callback_data="menu_stats")],
            [InlineKeyboardButton("⚙️ הגדרות מערכת", callback_data="menu_system")]
        ]

        text = "🏠 **תפריט ראשי**\n\nבחר אפשרות:"

        await message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def handle_callback(self, query: CallbackQuery):
        """Handle callback queries"""
        data = query.data

        try:
            # Answer callback to remove loading animation
            await query.answer()

            # Main menu callbacks
            if data == "menu_main":
                await self.show_main_menu_edit(query)
            elif data == "menu_dashboard":
                await self.show_dashboard(query)
            elif data == "menu_users":
                await self.show_users_menu(query)
            elif data == "menu_security":
                await self.show_security_menu(query)
            elif data == "menu_blocks":
                await self.show_blocks_menu(query)
            elif data == "menu_stats":
                await self.show_stats(query)
            elif data == "menu_system":
                await self.show_system_menu(query)

            # User management callbacks
            elif data.startswith("user_manage_"):
                username = data.replace("user_manage_", "")
                await self.show_user_details(query, username)
            elif data.startswith("user_2fa_toggle_"):
                username = data.replace("user_2fa_toggle_", "")
                await self.toggle_user_2fa(query, username)
            elif data.startswith("user_f2b_toggle_"):
                username = data.replace("user_f2b_toggle_", "")
                await self.toggle_user_f2b(query, username)
            elif data.startswith("user_keys_"):
                username = data.replace("user_keys_", "")
                await self.show_user_ssh_keys(query, username)
            elif data.startswith("user_delete_"):
                username = data.replace("user_delete_", "")
                await self.confirm_delete_user(query, username)
            elif data.startswith("user_delete_confirm_"):
                username = data.replace("user_delete_confirm_", "")
                await self.delete_user_action(query, username)
            elif data == "user_create":
                await self.start_create_user(query)

            # SSH key management
            elif data.startswith("key_delete_"):
                parts = data.split("_", 3)
                username = parts[2]
                key_index = int(parts[3])
                await self.delete_ssh_key_action(query, username, key_index)
            elif data.startswith("key_add_"):
                username = data.replace("key_add_", "")
                await self.start_add_ssh_key(query, username)

            # Security callbacks
            elif data == "toggle_global_2fa":
                await self.toggle_global_2fa(query)
            elif data.startswith("set_max_attempts_"):
                attempts = int(data.replace("set_max_attempts_", ""))
                await self.set_max_attempts(query, attempts)

            # Block management
            elif data.startswith("unblock_"):
                ip = data.replace("unblock_", "")
                await self.unblock_ip(query, ip)

            # System callbacks
            elif data.startswith("restart_"):
                service = data.replace("restart_", "")
                await self.restart_service(query, service)

        except MessageNotModified:
            # Ignore if message content hasn't changed
            pass
        except Exception as e:
            logger.error(f"Error handling callback: {e}")
            await query.answer("❌ שגיאה בעיבוד הפעולה", show_alert=True)

    async def show_main_menu_edit(self, query: CallbackQuery):
        """Edit message to show main menu"""
        keyboard = [
            [InlineKeyboardButton("🎛 לוח בקרה", callback_data="menu_dashboard")],
            [InlineKeyboardButton("👥 ניהול משתמשים", callback_data="menu_users")],
            [InlineKeyboardButton("🔐 הגדרות אבטחה", callback_data="menu_security")],
            [InlineKeyboardButton("🚫 ניהול חסימות", callback_data="menu_blocks")],
            [InlineKeyboardButton("📊 סטטיסטיקות", callback_data="menu_stats")],
            [InlineKeyboardButton("⚙️ הגדרות מערכת", callback_data="menu_system")]
        ]

        text = "🏠 **תפריט ראשי**\n\nבחר אפשרות:"

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def show_dashboard(self, query: CallbackQuery):
        """Show dashboard with current status"""
        # Get system info
        uptime = subprocess.getoutput("uptime -p")
        active_sessions = subprocess.getoutput("who | wc -l")
        blocked_ips_count = len(self.get_blocked_ips())

        text = f"""🎛 **לוח בקרה**

📊 **מצב מערכת:**
⏱ זמן פעילות: {uptime}
👥 חיבורים פעילים: {active_sessions}
🚫 כתובות חסומות: {blocked_ips_count}

🔐 **הגדרות נוכחיות:**
• אימות דו-שלבי: {'✅ פעיל' if self.global_settings.get('global_2fa', True) else '❌ כבוי'}
• מקסימום ניסיונות: {self.global_settings.get('max_attempts', 3)}
• משך חסימה: {self.global_settings.get('block_duration', 3600)} שניות
"""

        keyboard = [
            [InlineKeyboardButton("🔄 רענן", callback_data="menu_dashboard")],
            [InlineKeyboardButton("🔙 תפריט ראשי", callback_data="menu_main")]
        ]

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def show_users_menu(self, query: CallbackQuery):
        """Show users management menu"""
        users = self.get_system_users()

        text = "👥 **ניהול משתמשים**\n\nבחר משתמש לניהול:"

        keyboard = []
        for user in users:
            status = []
            if user['2fa_enabled']:
                status.append("🔐")
            if user['f2b_enabled']:
                status.append("🚫")
            status_str = " ".join(status) if status else "⚠️"

            keyboard.append([
                InlineKeyboardButton(
                    f"{user['username']} {status_str}",
                    callback_data=f"user_manage_{user['username']}"
                )
            ])

        keyboard.append([InlineKeyboardButton("➕ צור משתמש חדש", callback_data="user_create")])
        keyboard.append([InlineKeyboardButton("🔙 תפריט ראשי", callback_data="menu_main")])

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def show_user_details(self, query: CallbackQuery, username: str):
        """Show detailed user management"""
        try:
            user = pwd.getpwnam(username)
            user_settings = self.user_2fa_settings.get(username, {})
            user_f2b = self.user_f2b_settings.get(username, {})
            ssh_keys = self.get_ssh_keys(username)

            text = f"""👤 **ניהול משתמש: {username}**

📋 **פרטי משתמש:**
• UID: {user.pw_uid}
• תיקיית בית: {user.pw_dir}
• Shell: {user.pw_shell}

🔐 **הגדרות אבטחה:**
• אימות דו-שלבי: {'✅ פעיל' if user_settings.get('2fa_enabled', True) else '❌ כבוי'}
• Fail2Ban: {'✅ פעיל' if user_f2b.get('f2b_enabled', True) else '❌ כבוי'}

🔑 **מפתחות SSH:** {len(ssh_keys)}
"""

            keyboard = [
                [InlineKeyboardButton(
                    f"{'🔐 כבה' if user_settings.get('2fa_enabled', True) else '🔓 הפעל'} אימות דו-שלבי",
                    callback_data=f"user_2fa_toggle_{username}"
                )],
                [InlineKeyboardButton(
                    f"{'🚫 כבה' if user_f2b.get('f2b_enabled', True) else '✅ הפעל'} Fail2Ban",
                    callback_data=f"user_f2b_toggle_{username}"
                )],
                [InlineKeyboardButton("🔑 ניהול מפתחות SSH", callback_data=f"user_keys_{username}")],
                [InlineKeyboardButton("🗑 מחק משתמש", callback_data=f"user_delete_{username}")],
                [InlineKeyboardButton("🔙 חזרה למשתמשים", callback_data="menu_users")]
            ]

            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except KeyError:
            await query.answer("❌ משתמש לא נמצא", show_alert=True)

    async def toggle_user_2fa(self, query: CallbackQuery, username: str):
        """Toggle 2FA for specific user"""
        if username not in self.user_2fa_settings:
            self.user_2fa_settings[username] = {}

        current = self.user_2fa_settings[username].get('2fa_enabled', True)
        self.user_2fa_settings[username]['2fa_enabled'] = not current
        self.save_settings()

        await query.answer(f"✅ אימות דו-שלבי {'כבוי' if current else 'פעיל'} עבור {username}")
        await self.show_user_details(query, username)

    async def toggle_user_f2b(self, query: CallbackQuery, username: str):
        """Toggle Fail2Ban for specific user"""
        if username not in self.user_f2b_settings:
            self.user_f2b_settings[username] = {}

        current = self.user_f2b_settings[username].get('f2b_enabled', True)
        self.user_f2b_settings[username]['f2b_enabled'] = not current
        self.save_settings()

        await query.answer(f"✅ Fail2Ban {'כבוי' if current else 'פעיל'} עבור {username}")
        await self.show_user_details(query, username)

    async def show_user_ssh_keys(self, query: CallbackQuery, username: str):
        """Show SSH keys for user"""
        keys = self.get_ssh_keys(username)

        text = f"""🔑 **מפתחות SSH עבור {username}**

מפתחות רשומים: {len(keys)}
"""

        keyboard = []
        for i, key in enumerate(keys):
            keyboard.append([
                InlineKeyboardButton(f"🗑 {key}", callback_data=f"key_delete_{username}_{i}")
            ])

        keyboard.append([InlineKeyboardButton("➕ הוסף מפתח", callback_data=f"key_add_{username}")])
        keyboard.append([InlineKeyboardButton("🔙 חזרה למשתמש", callback_data=f"user_manage_{username}")])

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def show_security_menu(self, query: CallbackQuery):
        """Show security settings menu"""
        text = f"""🔐 **הגדרות אבטחה**

**הגדרות נוכחיות:**
• אימות דו-שלבי גלובלי: {'✅ פעיל' if self.global_settings.get('global_2fa', True) else '❌ כבוי'}
• מקסימום ניסיונות כושלים: {self.global_settings.get('max_attempts', 3)}
• משך חסימה: {self.global_settings.get('block_duration', 3600)} שניות
"""

        keyboard = [
            [InlineKeyboardButton(
                f"{'🔐 כבה' if self.global_settings.get('global_2fa', True) else '🔓 הפעל'} אימות דו-שלבי גלובלי",
                callback_data="toggle_global_2fa"
            )],
            [
                InlineKeyboardButton("1️⃣", callback_data="set_max_attempts_1"),
                InlineKeyboardButton("3️⃣", callback_data="set_max_attempts_3"),
                InlineKeyboardButton("5️⃣", callback_data="set_max_attempts_5"),
                InlineKeyboardButton("🔟", callback_data="set_max_attempts_10")
            ],
            [InlineKeyboardButton("🔙 תפריט ראשי", callback_data="menu_main")]
        ]

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def toggle_global_2fa(self, query: CallbackQuery):
        """Toggle global 2FA setting"""
        current = self.global_settings.get('global_2fa', True)
        self.global_settings['global_2fa'] = not current
        self.save_settings()

        # Update 2FA config file
        config_file = '/var/lib/ssh-monitor/2fa_config.json'
        with open(config_file, 'w') as f:
            json.dump({'enabled': not current}, f)

        await query.answer(f"✅ אימות דו-שלבי גלובלי {'כבוי' if current else 'פעיל'}")
        await self.show_security_menu(query)

    async def set_max_attempts(self, query: CallbackQuery, attempts: int):
        """Set maximum login attempts"""
        self.global_settings['max_attempts'] = attempts
        self.save_settings()

        await query.answer(f"✅ מקסימום ניסיונות הוגדר ל-{attempts}")
        await self.show_security_menu(query)

    async def show_blocks_menu(self, query: CallbackQuery):
        """Show blocked IPs menu"""
        blocked_ips = self.get_blocked_ips()

        text = f"""🚫 **ניהול חסימות**

כתובות IP חסומות: {len(blocked_ips)}
"""

        keyboard = []
        for ip in list(blocked_ips.keys())[:10]:  # Show first 10
            keyboard.append([
                InlineKeyboardButton(f"🔓 {ip}", callback_data=f"unblock_{ip}")
            ])

        if len(blocked_ips) > 10:
            text += f"\n_מוצגות 10 הכתובות הראשונות מתוך {len(blocked_ips)}_"

        keyboard.append([InlineKeyboardButton("🔙 תפריט ראשי", callback_data="menu_main")])

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    def get_blocked_ips(self) -> Dict:
        """Get list of blocked IPs"""
        if os.path.exists(self.blocked_ips_file):
            with open(self.blocked_ips_file, 'r') as f:
                return json.load(f)
        return {}

    async def unblock_ip(self, query: CallbackQuery, ip: str):
        """Unblock an IP address"""
        try:
            # Remove from blocked IPs file
            blocked_ips = self.get_blocked_ips()
            if ip in blocked_ips:
                del blocked_ips[ip]
                with open(self.blocked_ips_file, 'w') as f:
                    json.dump(blocked_ips, f)

            # Remove from firewall rules
            commands = [
                f"iptables -D INPUT -s {ip} -j REJECT --reject-with tcp-reset 2>/dev/null",
                f"iptables -D INPUT -s {ip} -j DROP 2>/dev/null",
                f"ip6tables -D INPUT -s {ip} -j REJECT --reject-with tcp6-reset 2>/dev/null",
                f"ip6tables -D INPUT -s {ip} -j DROP 2>/dev/null",
                f"ufw delete deny from {ip} 2>/dev/null",
                f"fail2ban-client set sshd unbanip {ip} 2>/dev/null"
            ]

            for cmd in commands:
                subprocess.run(cmd, shell=True, stderr=subprocess.DEVNULL)

            await query.answer(f"✅ {ip} בוטלה חסימתו")
            await self.show_blocks_menu(query)
        except Exception as e:
            await query.answer(f"❌ שגיאה: {str(e)}", show_alert=True)

    async def show_stats(self, query: CallbackQuery):
        """Show statistics"""
        # Get stats from log files and monitoring data
        try:
            # Count today's events
            today = datetime.now().strftime("%Y-%m-%d")

            # Get login attempts
            successful_logins = subprocess.getoutput(f"grep 'Accepted' /var/log/auth.log | grep '{today}' | wc -l")
            failed_logins = subprocess.getoutput(f"grep 'Failed password' /var/log/auth.log | grep '{today}' | wc -l")

            # Get unique IPs
            unique_ips = subprocess.getoutput("grep 'from' /var/log/auth.log | awk '{print $NF}' | sort -u | wc -l")

            text = f"""📊 **סטטיסטיקות**

📅 **היום ({today}):**
• התחברויות מוצלחות: {successful_logins}
• ניסיונות כושלים: {failed_logins}
• כתובות IP ייחודיות: {unique_ips}

🔐 **הגדרות משתמשים:**
• משתמשים עם 2FA: {sum(1 for u in self.user_2fa_settings.values() if u.get('2fa_enabled', True))}
• משתמשים עם F2B: {sum(1 for u in self.user_f2b_settings.values() if u.get('f2b_enabled', True))}

🚫 **חסימות:**
• IP חסומות כעת: {len(self.get_blocked_ips())}
"""

            keyboard = [
                [InlineKeyboardButton("🔄 רענן", callback_data="menu_stats")],
                [InlineKeyboardButton("🔙 תפריט ראשי", callback_data="menu_main")]
            ]

            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            await query.answer("❌ שגיאה בטעינת סטטיסטיקות", show_alert=True)

    async def show_system_menu(self, query: CallbackQuery):
        """Show system management menu"""
        text = """⚙️ **הגדרות מערכת**

בחר שירות להפעלה מחדש:
"""

        keyboard = [
            [InlineKeyboardButton("🔄 SSH Monitor", callback_data="restart_ssh-monitor")],
            [InlineKeyboardButton("🔄 Failed Monitor", callback_data="restart_ssh-failed-monitor")],
            [InlineKeyboardButton("🔄 Callback Handler", callback_data="restart_telegram-callback-handler")],
            [InlineKeyboardButton("🔄 UI Manager", callback_data="restart_telegram-ui-manager")],
            [InlineKeyboardButton("🔙 תפריט ראשי", callback_data="menu_main")]
        ]

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def restart_service(self, query: CallbackQuery, service: str):
        """Restart a system service"""
        try:
            result = subprocess.run(
                f"systemctl restart {service}",
                shell=True,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                await query.answer(f"✅ {service} הופעל מחדש")
            else:
                await query.answer(f"❌ שגיאה בהפעלת {service}", show_alert=True)

            await self.show_system_menu(query)
        except Exception as e:
            await query.answer(f"❌ שגיאה: {str(e)}", show_alert=True)

    async def confirm_delete_user(self, query: CallbackQuery, username: str):
        """Show confirmation before deleting user"""
        if username == 'root':
            await query.answer("❌ לא ניתן למחוק את משתמש root", show_alert=True)
            return

        text = f"""⚠️ **אזהרה**

האם אתה בטוח שברצונך למחוק את המשתמש {username}?

פעולה זו תמחק:
• את המשתמש מהמערכת
• את תיקיית הבית שלו
• את כל הקבצים שלו
• את כל ההגדרות שלו

**פעולה זו לא ניתנת לביטול!**
"""

        keyboard = [
            [InlineKeyboardButton("❌ מחק סופית", callback_data=f"user_delete_confirm_{username}")],
            [InlineKeyboardButton("🔙 ביטול", callback_data=f"user_manage_{username}")]
        ]

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def delete_user_action(self, query: CallbackQuery, username: str):
        """Actually delete the user"""
        success, message = self.delete_user(username)

        if success:
            await query.answer(f"✅ {message}")
            await self.show_users_menu(query)
        else:
            await query.answer(f"❌ {message}", show_alert=True)
            await self.show_user_details(query, username)

    async def start_create_user(self, query: CallbackQuery):
        """Start user creation process"""
        text = """➕ **יצירת משתמש חדש**

שלח הודעה בפורמט:
`/adduser <username> [password]`

דוגמה:
`/adduser john mypassword123`
או
`/adduser john` (ללא סיסמה)
"""

        keyboard = [
            [InlineKeyboardButton("🔙 ביטול", callback_data="menu_users")]
        ]

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    async def delete_ssh_key_action(self, query: CallbackQuery, username: str, key_index: int):
        """Delete an SSH key"""
        keys = self.get_ssh_keys(username)
        if key_index < len(keys):
            key_pattern = keys[key_index].split("...")[0].strip()
            if self.delete_ssh_key(username, key_pattern):
                await query.answer("✅ מפתח נמחק בהצלחה")
            else:
                await query.answer("❌ שגיאה במחיקת מפתח", show_alert=True)

        await self.show_user_ssh_keys(query, username)

    async def start_add_ssh_key(self, query: CallbackQuery, username: str):
        """Start process to add SSH key"""
        text = f"""🔑 **הוספת מפתח SSH עבור {username}**

שלח את המפתח הציבורי בהודעה הבאה.

הפורמט צריך להיות:
`ssh-rsa AAAAB3NzaC1... comment`

או השתמש בפקודה:
`/addkey {username} <ssh-key>`
"""

        keyboard = [
            [InlineKeyboardButton("🔙 ביטול", callback_data=f"user_keys_{username}")]
        ]

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    async def handle_adduser_command(self, message: Message):
        """Handle /adduser command"""
        parts = message.text.split(maxsplit=2)
        if len(parts) < 2:
            await message.reply_text("❌ שימוש: /adduser <username> [password]")
            return

        username = parts[1]
        password = parts[2] if len(parts) > 2 else None

        success, msg = self.create_user(username, password)
        if success:
            await message.reply_text(f"✅ {msg}\n\nהמשתמש {username} נוצר בהצלחה")
        else:
            await message.reply_text(f"❌ {msg}")

    async def handle_addkey_command(self, message: Message):
        """Handle /addkey command"""
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            await message.reply_text("❌ שימוש: /addkey <username> <ssh-public-key>")
            return

        username = parts[1]
        key = parts[2]

        # Validate SSH key format
        if not (key.startswith(('ssh-rsa ', 'ssh-ed25519 ', 'ecdsa-sha2-')) and len(key.split()) >= 2):
            await message.reply_text("❌ פורמט מפתח SSH לא תקין")
            return

        if self.add_ssh_key(username, key):
            await message.reply_text(f"✅ מפתח SSH נוסף בהצלחה עבור {username}")
        else:
            await message.reply_text(f"❌ שגיאה בהוספת מפתח SSH")

    async def run(self):
        """Start the bot"""
        logger.info("Starting Telegram UI Manager with Pyrogram...")
        await self.app.start()
        logger.info("Bot started successfully")

        # Keep the bot running
        await asyncio.Event().wait()

async def main():
    manager = TelegramUIManager()
    await manager.run()

if __name__ == "__main__":
    asyncio.run(main())