# SSH Telegram Monitor 🔐

![GitHub stars](https://img.shields.io/github/stars/SHLOMO77018/ssh-telegram-monitor)
![GitHub release](https://img.shields.io/github/v/release/SHLOMO77018/ssh-telegram-monitor)
![License](https://img.shields.io/github/license/SHLOMO77018/ssh-telegram-monitor)
![GitHub issues](https://img.shields.io/github/issues/SHLOMO77018/ssh-telegram-monitor)
![GitHub forks](https://img.shields.io/github/forks/SHLOMO77018/ssh-telegram-monitor)

Real-time SSH authentication monitoring and automated blocking system with Telegram notifications for Linux servers.

## Features 🚀

- **Real-time SSH Monitoring**: Instant notifications for successful and failed SSH login attempts
- **Auto-blocking**: Automatically blocks IPs after 3 failed attempts
- **Telegram Integration**:
  - Live notifications with detailed information
  - Interactive buttons for immediate blocking/unblocking
  - Geographic location and ISP information
- **Multi-layer Security**:
  - Fail2ban integration
  - UFW firewall rules
  - iptables direct rules
  - Active session termination
- **Smart Tracking**:
  - Database of blocked IPs
  - Failed attempts counter with time-based reset
  - Prevents duplicate notifications for blocked IPs

## Screenshots 📱

### Notification Examples:
- ✅ Successful login notification with action buttons
- ⚠️ Failed attempt warning (1/3, 2/3)
- 🚫 Auto-block notification after 3 attempts
- 🔓 Unblock confirmation

## Requirements 📋

- Ubuntu/Debian Linux
- Python 3.8+
- Root access
- Active Telegram bot

## Installation 🛠️

### 1. Clone the Repository
```bash
git clone https://github.com/SHLOMO77018/ssh-telegram-monitor.git
cd ssh-telegram-monitor
```

### 2. Install Dependencies
```bash
# System packages
apt update
apt install -y python3-pip fail2ban ufw conntrack python3-psutil

# Python packages
pip3 install requests psutil
```

### 3. Create Telegram Bot
1. Open Telegram and search for @BotFather
2. Send `/newbot` and follow instructions
3. Save your bot token

### 4. Configure Environment
```bash
# Copy example config
cp .env.example .env

# Edit with your credentials
nano .env
# Add your BOT_TOKEN and run get_telegram_chat_id.py to get CHAT_ID
```

### 5. Run Setup Script
```bash
sudo ./install.sh
```

## Manual Installation 🔧

### 1. Copy Scripts
```bash
cp scripts/* /usr/local/bin/
chmod +x /usr/local/bin/*.sh
chmod +x /usr/local/bin/*.py
```

### 2. Configure PAM
Add to `/etc/pam.d/sshd`:
```bash
session    optional     pam_exec.so seteuid /usr/local/bin/ssh_login_notify.sh
```

### 3. Setup Systemd Services
```bash
cp systemd/*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable ssh-telegram-monitor.service
systemctl enable telegram-action-handler.service
systemctl start ssh-telegram-monitor.service
systemctl start telegram-action-handler.service
```

### 4. Configure Fail2ban
```bash
cp config/jail.local.example /etc/fail2ban/jail.local
systemctl restart fail2ban
```

## Configuration ⚙️

### Environment Variables (.env)
```env
BOT_TOKEN=your_bot_token_here
CHAT_ID=your_chat_id_here
MAX_ATTEMPTS=3
BLOCK_DURATION_HOURS=24
```

### Get Your Chat ID
```bash
python3 scripts/get_telegram_chat_id.py
# Follow instructions and send /start to your bot
```

## Usage 📱

### Telegram Commands
- `/block <IP>` - Manually block an IP
- `/unblock <IP>` - Unblock an IP

### Interactive Buttons
Each notification includes:
- **🚫 Block IP** - Immediately block and disconnect
- **🔓 Unblock** - Remove all blocks
- **📊 More Info** - Get server statistics

### Service Management
```bash
# Check status
systemctl status ssh-telegram-monitor
systemctl status telegram-action-handler

# View logs
journalctl -u ssh-telegram-monitor -f
journalctl -u telegram-action-handler -f

# Restart services
systemctl restart ssh-telegram-monitor
systemctl restart telegram-action-handler
```

## File Structure 📁

```
ssh-telegram-monitor/
├── scripts/
│   ├── ssh_telegram_notify.py      # Login notifications
│   ├── ssh_monitor_advanced.py     # Failed attempts monitor
│   ├── telegram_action_handler.py  # Handle Telegram buttons
│   ├── get_telegram_chat_id.py     # Setup helper
│   ├── ssh_login_notify.sh         # PAM script
│   ├── kill_ssh_sessions.sh        # Session terminator
│   └── unblock_ip_complete.sh      # Unblock helper
├── systemd/
│   ├── ssh-telegram-monitor.service
│   └── telegram-action-handler.service
├── config/
│   ├── sshd.pam.example            # PAM configuration
│   └── jail.local.example          # Fail2ban config
├── docs/
│   └── setup_guide.md
├── .env.example
├── README.md
└── install.sh
```

## How It Works 🔍

1. **SSH Login Detection**: PAM module triggers on every SSH session
2. **Failed Attempts Tracking**: Monitors `/var/log/auth.log` for failures
3. **Smart Blocking**:
   - Counts attempts per IP
   - Auto-blocks after threshold
   - Maintains blocked IPs database
4. **Notifications**:
   - Sends detailed info via Telegram
   - Includes location, ISP, attempt count
   - Provides action buttons
5. **Multi-layer Blocking**:
   - Adds to Fail2ban
   - Creates UFW rule
   - Inserts iptables DROP
   - Kills active sessions

## Troubleshooting 🔨

### No Notifications
```bash
# Check services
systemctl status ssh-telegram-monitor
systemctl status telegram-action-handler

# Verify bot token
curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe

# Check logs
tail -f /var/log/ssh_telegram.log
```

### False Positives
- Edit MAX_ATTEMPTS in .env
- Whitelist IPs in UFW
- Check `/var/run/ssh_blocked_ips.json`

### Clear All Blocks
```bash
/usr/local/bin/unblock_ip_complete.sh <IP>
```

## Security Considerations 🔒

- Keep bot token secret
- Use strong SSH keys
- Regular system updates
- Monitor logs regularly
- Implement rate limiting
- Use VPN for admin access

## Contributing 🤝

1. Fork the repository
2. Create feature branch
3. Commit changes
4. Push to branch
5. Open Pull Request

## License 📄

MIT License - see LICENSE file

## Author 👤

Created with ❤️ for server security

## Support 💬

- Issues: [GitHub Issues](https://github.com/SHLOMO77018/ssh-telegram-monitor/issues)
- Discussions: [GitHub Discussions](https://github.com/SHLOMO77018/ssh-telegram-monitor/discussions)

## Changelog 📝

### v1.0.0
- Initial release
- Basic monitoring and notifications
- Auto-blocking after 3 attempts
- Interactive Telegram buttons
- Multi-layer security implementation

---

⭐ Star this repo if it helps secure your server!