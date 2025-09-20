#!/usr/bin/env python3
import requests
import time

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

print("🤖 Telegram Bot Setup")
print("=" * 50)
print(f"1. Open Telegram and search for your bot")
print(f"2. Start a chat with the bot and send: /start")
print(f"3. Bot username: @{BOT_TOKEN.split(':')[0]}_bot")
print(f"4. Or use this link: https://t.me/YOUR_BOT_NAME")
print("=" * 50)
print("Waiting for message...")

last_update_id = 0

while True:
    try:
        response = requests.get(f"{TELEGRAM_API}/getUpdates?offset={last_update_id+1}")
        if response.status_code == 200:
            data = response.json()
            if data['result']:
                for update in data['result']:
                    last_update_id = update['update_id']
                    if 'message' in update:
                        chat_id = update['message']['chat']['id']
                        username = update['message']['from'].get('username', 'Unknown')
                        first_name = update['message']['from'].get('first_name', '')

                        print(f"\n✅ Found chat!")
                        print(f"Chat ID: {chat_id}")
                        print(f"User: {first_name} (@{username})")

                        # Save chat ID
                        with open('/etc/telegram_chat_id.txt', 'w') as f:
                            f.write(str(chat_id))

                        # Send confirmation
                        msg = "✅ Bot configured successfully!\n"
                        msg += "You will now receive SSH login notifications."
                        requests.post(f"{TELEGRAM_API}/sendMessage",
                                    data={'chat_id': chat_id, 'text': msg})

                        print(f"\n✅ Chat ID saved to /etc/telegram_chat_id.txt")
                        exit(0)

        time.sleep(2)

    except KeyboardInterrupt:
        print("\n\nSetup cancelled.")
        exit(1)
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(5)