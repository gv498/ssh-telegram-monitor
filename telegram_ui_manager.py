#!/usr/bin/env python3
import os
import json
import asyncio
import logging
import subprocess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TelegramUIManager:
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')

        # Configuration files
        self.config_dir = '/var/lib/ssh-monitor'
        self.user_2fa_file = f'{self.config_dir}/user_2fa_settings.json'
        self.global_settings_file = f'{self.config_dir}/global_settings.json'
        self.blocked_ips_file = f'{self.config_dir}/blocked_ips.json'

        # Create directories
        os.makedirs(self.config_dir, exist_ok=True)

        # Load configurations
        self.user_2fa_settings = self.load_json(self.user_2fa_file, {})
        self.global_settings = self.load_json(self.global_settings_file, {
            '2fa_enabled': True,
            'max_attempts': 3,
            'auto_block': True,
            'notification_level': 'all'
        })

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
        """Save JSON file"""
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Main menu"""
        keyboard = [
            [InlineKeyboardButton("🎛 לוח בקרה", callback_data="menu_dashboard")],
            [InlineKeyboardButton("👥 ניהול משתמשים", callback_data="menu_users")],
            [InlineKeyboardButton("🔐 הגדרות אבטחה", callback_data="menu_security")],
            [InlineKeyboardButton("🚫 ניהול חסימות", callback_data="menu_blocks")],
            [InlineKeyboardButton("📊 סטטיסטיקות", callback_data="menu_stats")],
            [InlineKeyboardButton("⚙️ הגדרות כלליות", callback_data="menu_settings")]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        message = """🎮 **מערכת ניהול SSH**

ברוך הבא למערכת הניהול המלאה.
בחר אפשרות מהתפריט:"""

        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show main menu via /menu command"""
        await self.show_main_menu(update, context)

    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show main menu"""
        keyboard = [
            [InlineKeyboardButton("🎛 לוח בקרה", callback_data="menu_dashboard")],
            [InlineKeyboardButton("👥 ניהול משתמשים", callback_data="menu_users")],
            [InlineKeyboardButton("🔐 הגדרות אבטחה", callback_data="menu_security")],
            [InlineKeyboardButton("🚫 ניהול חסימות", callback_data="menu_blocks")],
            [InlineKeyboardButton("📊 סטטיסטיקות", callback_data="menu_stats")],
            [InlineKeyboardButton("⚙️ הגדרות כלליות", callback_data="menu_settings")]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        message = """🎮 **מערכת ניהול SSH**

בחר אפשרות מהתפריט:"""

        if update.callback_query:
            await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

    async def show_dashboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show dashboard"""
        query = update.callback_query

        # Get system status
        services = {
            'ssh-failed-monitor-simple': '🔍 ניטור ניסיונות',
            'telegram-callback-handler': '🤖 מטפל פקודות',
            'ssh-session-monitor': '🚪 ניטור חיבורים'
        }

        status_text = "📊 **סטטוס מערכת**\n\n"

        for service, name in services.items():
            try:
                result = subprocess.run(f"systemctl is-active {service}",
                                      shell=True, capture_output=True, text=True)
                is_active = result.stdout.strip() == 'active'
                status_text += f"{'✅' if is_active else '❌'} {name}\n"
            except:
                status_text += f"❓ {name}\n"

        # Get blocked IPs count
        blocked_ips = self.load_json(self.blocked_ips_file, {})
        status_text += f"\n🚫 IPs חסומים: {len(blocked_ips)}"

        # Get 2FA status
        status_text += f"\n🔐 אימות דו-שלבי: {'פעיל' if self.global_settings.get('2fa_enabled', True) else 'כבוי'}"

        keyboard = [
            [InlineKeyboardButton("🔄 רענן", callback_data="menu_dashboard")],
            [InlineKeyboardButton("🔙 חזרה", callback_data="menu_main")]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(status_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def show_users_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show users management menu"""
        query = update.callback_query

        # Get system users
        try:
            result = subprocess.run("getent passwd | grep -E ':[0-9]{4,}:' | cut -d: -f1",
                                  shell=True, capture_output=True, text=True)
            users = result.stdout.strip().split('\n') if result.stdout else []
        except:
            users = []

        message = "👥 **ניהול משתמשים**\n\n"
        message += "בחר משתמש להגדרת 2FA:\n\n"

        keyboard = []

        for user in users[:10]:  # Limit to 10 users for UI
            if user:
                status = self.user_2fa_settings.get(user, {}).get('2fa_enabled', True)
                emoji = "🔐" if status else "🔓"
                keyboard.append([
                    InlineKeyboardButton(
                        f"{emoji} {user}",
                        callback_data=f"user_toggle_{user}"
                    )
                ])

        keyboard.append([InlineKeyboardButton("🔙 חזרה", callback_data="menu_main")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

    async def toggle_user_2fa(self, update: Update, context: ContextTypes.DEFAULT_TYPE, username: str):
        """Toggle 2FA for specific user"""
        query = update.callback_query

        if username not in self.user_2fa_settings:
            self.user_2fa_settings[username] = {'2fa_enabled': True}

        current = self.user_2fa_settings[username].get('2fa_enabled', True)
        self.user_2fa_settings[username]['2fa_enabled'] = not current

        self.save_json(self.user_2fa_file, self.user_2fa_settings)

        status = "פעיל" if not current else "כבוי"
        await query.answer(f"2FA למשתמש {username}: {status}")

        # Refresh the menu
        await self.show_users_menu(update, context)

    async def show_security_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show security settings menu"""
        query = update.callback_query

        message = "🔐 **הגדרות אבטחה**\n\n"

        # Get current settings
        twofa_enabled = self.global_settings.get('2fa_enabled', True)
        max_attempts = self.global_settings.get('max_attempts', 3)
        auto_block = self.global_settings.get('auto_block', True)

        message += f"אימות דו-שלבי: {'✅ פעיל' if twofa_enabled else '❌ כבוי'}\n"
        message += f"מקס׳ ניסיונות: {max_attempts}\n"
        message += f"חסימה אוטומטית: {'✅ פעילה' if auto_block else '❌ כבויה'}\n"

        keyboard = [
            [InlineKeyboardButton(
                f"{'🔐 כבה' if twofa_enabled else '🔓 הפעל'} 2FA גלובלי",
                callback_data="toggle_global_2fa"
            )],
            [
                InlineKeyboardButton("➖", callback_data="attempts_minus"),
                InlineKeyboardButton(f"{max_attempts} ניסיונות", callback_data="noop"),
                InlineKeyboardButton("➕", callback_data="attempts_plus")
            ],
            [InlineKeyboardButton(
                f"{'🚫 כבה' if auto_block else '✅ הפעל'} חסימה אוטומטית",
                callback_data="toggle_auto_block"
            )],
            [InlineKeyboardButton("🔙 חזרה", callback_data="menu_main")]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

    async def show_blocks_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show blocked IPs management"""
        query = update.callback_query

        blocked_ips = self.load_json(self.blocked_ips_file, {})

        if not blocked_ips:
            message = "🚫 **ניהול חסימות**\n\nאין כתובות IP חסומות"
            keyboard = [[InlineKeyboardButton("🔙 חזרה", callback_data="menu_main")]]
        else:
            message = "🚫 **כתובות IP חסומות**\n\n"
            keyboard = []

            for ip, info in list(blocked_ips.items())[:8]:  # Limit display
                timestamp = info.get('timestamp', 'לא ידוע')
                keyboard.append([
                    InlineKeyboardButton(f"🔓 שחרר {ip}", callback_data=f"unblock_{ip}")
                ])
                message += f"• {ip}\n  📅 {timestamp[:10]}\n\n"

            keyboard.append([
                InlineKeyboardButton("🔓 שחרר הכל", callback_data="unblock_all_confirm")
            ])
            keyboard.append([InlineKeyboardButton("🔙 חזרה", callback_data="menu_main")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

    async def show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show statistics"""
        query = update.callback_query

        # Get statistics
        attempts = self.load_json(f'{self.config_dir}/failed_attempts.json', {})
        blocked = self.load_json(self.blocked_ips_file, {})

        message = "📊 **סטטיסטיקות**\n\n"
        message += f"🔴 ניסיונות כושלים: {sum(a.get('count', 0) for a in attempts.values())}\n"
        message += f"🚫 IPs חסומים: {len(blocked)}\n"
        message += f"⚠️ IPs עם ניסיונות: {len(attempts)}\n"

        # Top attackers
        if attempts:
            message += "\n**תוקפים מובילים:**\n"
            sorted_attempts = sorted(attempts.items(),
                                    key=lambda x: x[1].get('count', 0),
                                    reverse=True)[:5]
            for ip, data in sorted_attempts:
                count = data.get('count', 0)
                message += f"• {ip}: {count} ניסיונות\n"

        keyboard = [
            [InlineKeyboardButton("🔄 רענן", callback_data="menu_stats")],
            [InlineKeyboardButton("🔙 חזרה", callback_data="menu_main")]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

    async def show_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show general settings"""
        query = update.callback_query

        notification_level = self.global_settings.get('notification_level', 'all')

        message = "⚙️ **הגדרות כלליות**\n\n"
        message += f"📢 רמת התראות: {notification_level}\n\n"

        keyboard = [
            [InlineKeyboardButton("📢 כל ההתראות", callback_data="notif_all")],
            [InlineKeyboardButton("⚠️ חסימות בלבד", callback_data="notif_blocks")],
            [InlineKeyboardButton("🔕 מושתק", callback_data="notif_none")],
            [InlineKeyboardButton("🔄 אתחל מערכת", callback_data="restart_confirm")],
            [InlineKeyboardButton("🔙 חזרה", callback_data="menu_main")]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle all callback queries"""
        query = update.callback_query
        await query.answer()

        data = query.data

        # Main menu navigation
        if data == "menu_main":
            await self.show_main_menu(update, context)
        elif data == "menu_dashboard":
            await self.show_dashboard(update, context)
        elif data == "menu_users":
            await self.show_users_menu(update, context)
        elif data == "menu_security":
            await self.show_security_menu(update, context)
        elif data == "menu_blocks":
            await self.show_blocks_menu(update, context)
        elif data == "menu_stats":
            await self.show_stats(update, context)
        elif data == "menu_settings":
            await self.show_settings(update, context)

        # User 2FA toggles
        elif data.startswith("user_toggle_"):
            username = data.replace("user_toggle_", "")
            await self.toggle_user_2fa(update, context, username)

        # Security settings
        elif data == "toggle_global_2fa":
            self.global_settings['2fa_enabled'] = not self.global_settings.get('2fa_enabled', True)
            self.save_json(self.global_settings_file, self.global_settings)
            await query.answer(f"2FA גלובלי: {'פעיל' if self.global_settings['2fa_enabled'] else 'כבוי'}")
            await self.show_security_menu(update, context)

        elif data == "attempts_minus":
            current = self.global_settings.get('max_attempts', 3)
            if current > 1:
                self.global_settings['max_attempts'] = current - 1
                self.save_json(self.global_settings_file, self.global_settings)
            await self.show_security_menu(update, context)

        elif data == "attempts_plus":
            current = self.global_settings.get('max_attempts', 3)
            if current < 10:
                self.global_settings['max_attempts'] = current + 1
                self.save_json(self.global_settings_file, self.global_settings)
            await self.show_security_menu(update, context)

        elif data == "toggle_auto_block":
            self.global_settings['auto_block'] = not self.global_settings.get('auto_block', True)
            self.save_json(self.global_settings_file, self.global_settings)
            await query.answer(f"חסימה אוטומטית: {'פעילה' if self.global_settings['auto_block'] else 'כבויה'}")
            await self.show_security_menu(update, context)

        # Block management
        elif data.startswith("unblock_"):
            if data == "unblock_all_confirm":
                keyboard = [
                    [
                        InlineKeyboardButton("✅ כן, שחרר הכל", callback_data="unblock_all_yes"),
                        InlineKeyboardButton("❌ ביטול", callback_data="menu_blocks")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    "⚠️ **אישור**\n\nהאם לשחרר את כל החסימות?",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            elif data == "unblock_all_yes":
                # Unblock all IPs
                blocked = self.load_json(self.blocked_ips_file, {})
                for ip in blocked.keys():
                    subprocess.run(f"/usr/local/bin/unblock_ip_complete.sh {ip}",
                                 shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.save_json(self.blocked_ips_file, {})
                await query.answer("כל החסימות שוחררו")
                await self.show_blocks_menu(update, context)
            else:
                ip = data.replace("unblock_", "")
                subprocess.run(f"/usr/local/bin/unblock_ip_complete.sh {ip}",
                             shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                blocked = self.load_json(self.blocked_ips_file, {})
                if ip in blocked:
                    del blocked[ip]
                    self.save_json(self.blocked_ips_file, blocked)
                await query.answer(f"{ip} שוחרר")
                await self.show_blocks_menu(update, context)

        # Settings
        elif data.startswith("notif_"):
            level = data.replace("notif_", "")
            self.global_settings['notification_level'] = level
            self.save_json(self.global_settings_file, self.global_settings)
            await query.answer(f"רמת התראות: {level}")
            await self.show_settings(update, context)

        elif data == "restart_confirm":
            keyboard = [
                [
                    InlineKeyboardButton("✅ כן, אתחל", callback_data="restart_yes"),
                    InlineKeyboardButton("❌ ביטול", callback_data="menu_settings")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "⚠️ **אישור**\n\nלאתחל את כל שירותי המערכת?",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

        elif data == "restart_yes":
            await query.answer("מאתחל שירותים...")
            services = [
                'ssh-failed-monitor-simple',
                'telegram-callback-handler',
                'ssh-session-monitor'
            ]
            for service in services:
                subprocess.run(f"systemctl restart {service}", shell=True)
            await query.answer("השירותים אותחלו")
            await self.show_settings(update, context)

def main():
    """Main function"""
    ui = TelegramUIManager()

    # Create application
    application = Application.builder().token(ui.bot_token).build()

    # Add handlers
    application.add_handler(CommandHandler("start", ui.start_command))
    application.add_handler(CommandHandler("menu", ui.menu_command))
    application.add_handler(CallbackQueryHandler(ui.handle_callback))

    # Run bot
    logger.info("Starting Telegram UI Manager...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()