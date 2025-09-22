#!/bin/bash

echo "==================================================="
echo "SSH Telegram Monitor v3.0.0 Installation Script"
echo "==================================================="
echo

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "❌ This script must be run as root"
   exit 1
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Step 1/8: Installing system dependencies...${NC}"
apt update
apt install -y python3-pip fail2ban ufw conntrack python3-psutil

echo -e "${YELLOW}Step 2/8: Installing Python packages...${NC}"
pip3 install requests psutil pyrogram tgcrypto python-telegram-bot python-dotenv aiofiles

echo -e "${YELLOW}Step 3/8: Creating directories...${NC}"
mkdir -p /usr/local/bin
mkdir -p /var/lib/ssh-monitor
mkdir -p /var/log/ssh-monitor
mkdir -p /etc/systemd/system

echo -e "${YELLOW}Step 4/8: Copying scripts...${NC}"
# Copy all Python scripts
cp telegram_*.py /usr/local/bin/
cp ssh_*.py /usr/local/bin/
cp monitor_*.py /usr/local/bin/

# Copy shell scripts
cp ssh_*.sh /usr/local/bin/
cp setup_*.sh /usr/local/bin/

# Make scripts executable
chmod +x /usr/local/bin/*.py
chmod +x /usr/local/bin/*.sh

echo -e "${YELLOW}Step 5/8: Setting up configuration...${NC}"
if [ ! -f .env ]; then
    cp .env.example .env
    echo -e "${RED}⚠️  Please edit .env file with your credentials:${NC}"
    echo "   - BOT_TOKEN: Your Telegram bot token"
    echo "   - TELEGRAM_CHAT_ID: Your Telegram chat ID"
    echo "   - GROUP_ID: Your Telegram group ID (with topics enabled)"
    read -p "Press Enter to continue after editing .env file..."
fi

echo -e "${YELLOW}Step 6/8: Configuring PAM for 2FA...${NC}"
# Backup original PAM config
cp /etc/pam.d/sshd /etc/pam.d/sshd.backup.$(date +%Y%m%d)

# Add 2FA authentication
if ! grep -q "ssh_2fa_check" /etc/pam.d/sshd; then
    sed -i '/^@include common-auth$/a\# 2FA Authentication check\nauth required pam_exec.so quiet expose_authtok /usr/local/bin/ssh_2fa_check.sh' /etc/pam.d/sshd
fi

# Add session notification
if ! grep -q "ssh_login_notify" /etc/pam.d/sshd; then
    echo "session optional pam_exec.so seteuid /usr/local/bin/ssh_login_notify_v2.sh" >> /etc/pam.d/sshd
fi

echo -e "${YELLOW}Step 7/8: Creating systemd services...${NC}"

# Create UI Manager service
cat > /etc/systemd/system/telegram-ui-manager.service << 'EOF'
[Unit]
Description=Telegram Bot UI Manager
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/ssh-telegram-monitor
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/usr/bin/python3 /usr/local/bin/telegram_ui_pyrogram.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Create Callback Handler service
cat > /etc/systemd/system/telegram-callback-handler.service << 'EOF'
[Unit]
Description=Telegram Callback Handler
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 /usr/local/bin/telegram_callback_handler.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Create Failed Monitor service
cat > /etc/systemd/system/ssh-failed-monitor.service << 'EOF'
[Unit]
Description=SSH Failed Attempts Monitor
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 /usr/local/bin/monitor_failed_simple.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo -e "${YELLOW}Step 8/8: Starting services...${NC}"
systemctl daemon-reload
systemctl enable telegram-ui-manager
systemctl enable telegram-callback-handler
systemctl enable ssh-failed-monitor

systemctl start telegram-ui-manager
systemctl start telegram-callback-handler
systemctl start ssh-failed-monitor

# Restart SSH to apply PAM changes
systemctl restart sshd

echo
echo -e "${GREEN}✅ Installation complete!${NC}"
echo
echo "==================================================="
echo "Next Steps:"
echo "1. Edit .env file with your credentials (if not done)"
echo "2. Create a Telegram group and enable Topics/Forums"
echo "3. Add your bot as admin with full permissions"
echo "4. Send /menu in Telegram to access control panel"
echo "5. Send /init in the group to create topics"
echo
echo "Available Commands:"
echo "  /menu - Open control panel"
echo "  /adduser <username> [password] - Create user"
echo "  /addkey <username> <ssh-key> - Add SSH key"
echo "  /status - View system status"
echo
echo "Service Status:"
systemctl is-active telegram-ui-manager >/dev/null && echo -e "  UI Manager: ${GREEN}✓ Running${NC}" || echo -e "  UI Manager: ${RED}✗ Not running${NC}"
systemctl is-active telegram-callback-handler >/dev/null && echo -e "  Callback Handler: ${GREEN}✓ Running${NC}" || echo -e "  Callback Handler: ${RED}✗ Not running${NC}"
systemctl is-active ssh-failed-monitor >/dev/null && echo -e "  Failed Monitor: ${GREEN}✓ Running${NC}" || echo -e "  Failed Monitor: ${RED}✗ Not running${NC}"
echo "==================================================="