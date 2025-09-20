#!/usr/bin/env python3
import os
import json
import asyncio
import logging
import socket
import subprocess
from typing import Optional, Dict, Any
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import TelegramError
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TelegramGroupManager:
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.group_id = int(os.getenv('TELEGRAM_GROUP_ID', '-1003066710155'))
        self.bot = Bot(token=self.bot_token)

        # Topic IDs storage
        self.topics_file = '/var/lib/ssh-monitor/telegram_topics.json'
        self.topics = self.load_topics()

        # Topic names and descriptions
        self.topic_config = {
            'successful_logins': {
                'name': '✅ התחברויות מוצלחות',
                'description': 'התראות על התחברויות SSH מוצלחות'
            },
            'failed_logins': {
                'name': '❌ ניסיונות כושלים',
                'description': 'ניסיונות התחברות כושלים וחסימות אוטומטיות'
            },
            'session_end': {
                'name': '🚪 סיום חיבור',
                'description': 'התראות על סיום חיבורי SSH'
            },
            '2fa_approval': {
                'name': '🔐 אישור דו-שלבי',
                'description': 'בקשות אישור לאימות דו-שלבי'
            },
            'general': {
                'name': '📢 כללי',
                'description': 'התראות כלליות של המערכת'
            }
        }

    def load_topics(self) -> Dict[str, int]:
        """Load saved topic IDs from file"""
        os.makedirs(os.path.dirname(self.topics_file), exist_ok=True)
        if os.path.exists(self.topics_file):
            try:
                with open(self.topics_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def save_topics(self):
        """Save topic IDs to file"""
        with open(self.topics_file, 'w') as f:
            json.dump(self.topics, f, indent=2)

    def get_server_ip(self) -> str:
        """Get the server's public IP address"""
        try:
            # Try multiple methods to get public IP
            methods = [
                "curl -s ifconfig.me",
                "curl -s icanhazip.com",
                "curl -s ipinfo.io/ip",
                "curl -s api.ipify.org"
            ]

            for cmd in methods:
                try:
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
                    if result.returncode == 0 and result.stdout.strip():
                        return result.stdout.strip()
                except:
                    continue

            # Fallback to hostname
            return socket.gethostname()
        except:
            return "Unknown"

    async def rename_group(self):
        """Rename the group to include server IP"""
        try:
            server_ip = self.get_server_ip()
            new_title = f"לוגים SSH של שרת {server_ip}"

            # Set chat title
            await self.bot.set_chat_title(
                chat_id=self.group_id,
                title=new_title
            )
            logger.info(f"Group renamed to: {new_title}")
            return True
        except TelegramError as e:
            logger.error(f"Failed to rename group: {e}")
            return False

    async def create_topics(self):
        """Create forum topics in the Telegram group"""
        try:
            # Check if group is a forum
            chat = await self.bot.get_chat(self.group_id)
            if not chat.is_forum:
                logger.error(f"Group {self.group_id} is not a forum. Please enable forum mode in group settings.")
                # Send message to group about enabling forums
                try:
                    await self.bot.send_message(
                        chat_id=self.group_id,
                        text="⚠️ **נדרש להפעיל נושאים (Topics)**\n\n"
                             "כדי שהבוט יוכל לעבוד כראוי, יש להפעיל נושאים בקבוצה:\n\n"
                             "1. לחץ על שם הקבוצה למעלה\n"
                             "2. לחץ על 'עריכה' (עיפרון)\n"
                             "3. הפעל את 'נושאים' (Topics)\n"
                             "4. שמור שינויים\n\n"
                             "לאחר ההפעלה, הרץ שוב את הפקודה /init",
                        parse_mode='Markdown'
                    )
                except:
                    pass
                return False

            # Rename group first
            await self.rename_group()

            # Create topics
            for topic_key, config in self.topic_config.items():
                if topic_key not in self.topics:
                    try:
                        # Create forum topic
                        result = await self.bot.create_forum_topic(
                            chat_id=self.group_id,
                            name=config['name']
                        )
                        self.topics[topic_key] = result.message_thread_id
                        logger.info(f"Created topic '{config['name']}' with ID {result.message_thread_id}")

                        # Send initial message to topic
                        await self.send_to_topic(
                            topic_key,
                            f"📌 **נושא: {config['name']}**\n\n{config['description']}"
                        )
                    except TelegramError as e:
                        logger.error(f"Failed to create topic {topic_key}: {e}")

            # Save topic IDs
            self.save_topics()
            return True

        except Exception as e:
            logger.error(f"Error creating topics: {e}")
            return False

    async def send_to_topic(self, topic_key: str, message: str, reply_markup=None, parse_mode='Markdown'):
        """Send message to specific topic"""
        if topic_key not in self.topics:
            logger.error(f"Topic {topic_key} not found")
            return None

        try:
            result = await self.bot.send_message(
                chat_id=self.group_id,
                message_thread_id=self.topics[topic_key],
                text=message,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
            return result
        except Exception as e:
            logger.error(f"Failed to send message to topic {topic_key}: {e}")
            return None

    async def send_successful_login(self, user: str, ip: str, location: str, details: Dict):
        """Send successful login notification"""
        message = f"""✅ **התחברות SSH מוצלחת**

👤 משתמש: `{user}`
🌐 כתובת IP: `{ip}`
📍 מיקום: {location}
🕒 זמן: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

**מידע מערכת:**
מעבד: {details.get('cpu', 'לא זמין')}%
זיכרון: {details.get('memory', 'לא זמין')}%
דיסק: {details.get('disk', 'לא זמין')}%
"""

        keyboard = [
            [
                InlineKeyboardButton("🚫 חסום IP", callback_data=f"block:{ip}"),
                InlineKeyboardButton("👁 הצג חיבורים", callback_data=f"sessions:{ip}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await self.send_to_topic('successful_logins', message, reply_markup)

    async def send_failed_login(self, user: str, ip: str, attempts: int, blocked: bool = False):
        """Send failed login notification"""
        status = "🚫 **נחסם אוטומטית**" if blocked else "⚠️ אזהרה"

        message = f"""❌ **ניסיון התחברות SSH כושל**

סטטוס: {status}
👤 משתמש: `{user}`
🌐 כתובת IP: `{ip}`
🔢 ניסיונות: {attempts}
🕒 זמן: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""

        if not blocked:
            keyboard = [
                [
                    InlineKeyboardButton("🚫 חסום עכשיו", callback_data=f"block:{ip}"),
                    InlineKeyboardButton("📊 הצג היסטוריה", callback_data=f"history:{ip}")
                ]
            ]
        else:
            keyboard = [
                [
                    InlineKeyboardButton("🔓 בטל חסימה", callback_data=f"unblock:{ip}"),
                    InlineKeyboardButton("📊 הצג היסטוריה", callback_data=f"history:{ip}")
                ]
            ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.send_to_topic('failed_logins', message, reply_markup)

    async def send_session_end(self, user: str, ip: str, duration: str):
        """Send session end notification"""
        message = f"""🚪 **חיבור SSH הסתיים**

👤 משתמש: `{user}`
🌐 כתובת IP: `{ip}`
⏱ משך זמן: {duration}
🕒 זמן: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""

        await self.send_to_topic('session_end', message)

    async def send_2fa_request(self, user: str, ip: str, location: str, session_id: str):
        """Send 2FA approval request"""
        message = f"""🔐 **נדרש אימות דו-שלבי**

⚠️ ניסיון התחברות SSH דורש אישור

👤 משתמש: `{user}`
🌐 כתובת IP: `{ip}`
📍 מיקום: {location}
🆔 מזהה חיבור: `{session_id}`
🕒 זמן: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

**ההתחברות תיחסם אם לא תאושר תוך 30 שניות**
"""

        keyboard = [
            [
                InlineKeyboardButton("✅ אשר", callback_data=f"2fa_approve:{session_id}:{ip}"),
                InlineKeyboardButton("❌ דחה", callback_data=f"2fa_deny:{session_id}:{ip}")
            ],
            [
                InlineKeyboardButton("🚫 דחה וחסום", callback_data=f"2fa_block:{session_id}:{ip}")
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        result = await self.send_to_topic('2fa_approval', message, reply_markup)
        return result.message_id if result else None

    async def send_general_alert(self, title: str, message: str, severity: str = 'info'):
        """Send general system alert"""
        emoji = {
            'info': 'ℹ️',
            'warning': '⚠️',
            'error': '❌',
            'success': '✅'
        }.get(severity, '📢')

        full_message = f"""{emoji} **{title}**

{message}

🕒 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

        await self.send_to_topic('general', full_message)

    async def send_ip_blocked_alert(self, ip: str, user: str, attempts: int):
        """Send IP blocked notification with unblock button"""
        message = f"""🚫 **כתובת IP נחסמה אוטומטית**

👤 משתמש אחרון: `{user}`
🌐 כתובת IP: `{ip}`
🔢 ניסיונות כושלים: {attempts}
🕒 זמן חסימה: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

הכתובת נחסמה בכל השכבות:
• iptables
• UFW
• Fail2ban
• חיבורים פעילים נותקו
"""

        keyboard = [
            [
                InlineKeyboardButton("🔓 בטל חסימה מיידית", callback_data=f"unblock:{ip}"),
                InlineKeyboardButton("📊 הצג היסטוריה", callback_data=f"history:{ip}")
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.send_to_topic('failed_logins', message, reply_markup)

    async def initialize(self):
        """Initialize group, rename it, and create topics"""
        logger.info("Initializing Telegram group manager...")

        # First check if group exists and is accessible
        try:
            chat = await self.bot.get_chat(self.group_id)
            logger.info(f"Found group: {chat.title}")
        except TelegramError as e:
            logger.error(f"Cannot access group {self.group_id}: {e}")
            logger.error("Please ensure:")
            logger.error("1. The bot is added to the group")
            logger.error("2. The bot has admin privileges")
            logger.error("3. The group ID is correct")
            return False

        # Create topics (will also rename group)
        success = await self.create_topics()
        if success:
            server_ip = self.get_server_ip()
            await self.send_general_alert(
                "המערכת אותחלה",
                f"מערכת ניטור SSH עם אימות דו-שלבי פעילה\n\nכתובת שרת: {server_ip}\nהקבוצה הוגדרה בהצלחה",
                "success"
            )
        return success

async def main():
    """Main function for testing"""
    manager = TelegramGroupManager()
    await manager.initialize()

if __name__ == "__main__":
    asyncio.run(main())