#!/usr/bin/env python3
import os
import sys
import asyncio
import logging
from telegram_group_manager import TelegramGroupManager
from telegram.error import TelegramError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def auto_setup():
    """Automatically setup group with rename and topics"""
    manager = TelegramGroupManager()

    print("\n" + "="*60)
    print("SSH Telegram Monitor - Automatic Group Setup")
    print("="*60)

    # Get server IP
    server_ip = manager.get_server_ip()
    print(f"\n✓ Server IP detected: {server_ip}")

    # Check group access
    print(f"✓ Connecting to group: {manager.group_id}")

    try:
        chat = await manager.bot.get_chat(manager.group_id)
        print(f"✓ Found group: {chat.title}")

        # Check if it's a forum
        if not chat.is_forum:
            print("\n⚠️  IMPORTANT: Forums/Topics are not enabled!")
            print("\nPlease follow these steps:")
            print("1. Open Telegram and go to your group")
            print("2. Tap on the group name at the top")
            print("3. Tap 'Edit' (pencil icon)")
            print("4. Enable 'Topics' toggle")
            print("5. Save changes")
            print("\nPress ENTER after enabling Topics...")
            input()

            # Check again
            chat = await manager.bot.get_chat(manager.group_id)
            if not chat.is_forum:
                print("❌ Topics still not enabled. Please enable them and run this script again.")
                return False

        print("✓ Topics/Forums enabled")

        # Now rename the group
        print(f"\n• Renaming group to: לוגים SSH של שרת {server_ip}")
        try:
            await manager.bot.set_chat_title(
                chat_id=manager.group_id,
                title=f"לוגים SSH של שרת {server_ip}"
            )
            print("✓ Group renamed successfully")
        except TelegramError as e:
            if "CHAT_NOT_MODIFIED" in str(e):
                print("✓ Group name already correct")
            else:
                print(f"⚠️  Could not rename group: {e}")

        # Create topics
        print("\n• Creating notification topics...")
        topics_created = 0

        for topic_key, config in manager.topic_config.items():
            if topic_key not in manager.topics:
                try:
                    result = await manager.bot.create_forum_topic(
                        chat_id=manager.group_id,
                        name=config['name']
                    )
                    manager.topics[topic_key] = result.message_thread_id
                    print(f"  ✓ Created: {config['name']}")
                    topics_created += 1

                    # Send initial message
                    await manager.send_to_topic(
                        topic_key,
                        f"📌 **Topic: {config['name']}**\n\n{config['description']}"
                    )
                except TelegramError as e:
                    print(f"  ❌ Failed to create {config['name']}: {e}")
            else:
                print(f"  ✓ Already exists: {config['name']}")

        # Save topics
        manager.save_topics()

        # Send initialization message
        await manager.send_general_alert(
            "System Initialized",
            f"SSH Telegram Monitor is now active!\n\nServer: {server_ip}\nTopics created: {topics_created}\nMonitoring: Active",
            "success"
        )

        print("\n" + "="*60)
        print("✅ SETUP COMPLETED SUCCESSFULLY!")
        print("="*60)
        print("\nYour Telegram group is now configured with:")
        print(f"• Group name: לוגים SSH של שרת {server_ip}")
        print("• 5 organized topics for different notifications")
        print("• 2FA authentication system")
        print("• Real-time SSH monitoring")
        print("\nThe system is now active and monitoring SSH access!")

        return True

    except TelegramError as e:
        print(f"\n❌ Error: {e}")
        print("\nPlease ensure:")
        print("1. The bot is added to the group")
        print("2. The bot has admin privileges")
        print("3. The group ID is correct in .env file")
        return False

if __name__ == "__main__":
    result = asyncio.run(auto_setup())
    sys.exit(0 if result else 1)