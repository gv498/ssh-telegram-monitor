#!/bin/bash

# SSH Telegram Monitor - Installation Script
# ==========================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}SSH Telegram Monitor Installer${NC}"
echo -e "${GREEN}================================${NC}"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}This script must be run as root${NC}"
   exit 1
fi

# Check for .env file
if [ ! -f ".env" ]; then
    echo -e "${RED}Error: .env file not found!${NC}"
    echo -e "${YELLOW}Please copy .env.example to .env and configure it:${NC}"
    echo "cp .env.example .env"
    echo "nano .env"
    exit 1
fi

# Load environment variables
source .env

# Validate required variables
if [ -z "$BOT_TOKEN" ] || [ "$BOT_TOKEN" == "YOUR_BOT_TOKEN_HERE" ]; then
    echo -e "${RED}Error: BOT_TOKEN not configured in .env${NC}"
    exit 1
fi

echo -e "${GREEN}Step 1: Installing system dependencies...${NC}"
apt update
apt install -y python3-pip fail2ban ufw conntrack python3-psutil whois

echo -e "${GREEN}Step 2: Installing Python packages...${NC}"
pip3 install requests psutil

echo -e "${GREEN}Step 3: Copying scripts...${NC}"
cp scripts/*.py /usr/local/bin/
cp scripts/*.sh /usr/local/bin/
chmod +x /usr/local/bin/*.py
chmod +x /usr/local/bin/*.sh

# Replace tokens in scripts
echo -e "${GREEN}Step 4: Configuring scripts with your tokens...${NC}"
for file in /usr/local/bin/{ssh_telegram_notify,ssh_monitor_advanced,telegram_action_handler,get_telegram_chat_id}.py; do
    sed -i "s/YOUR_BOT_TOKEN_HERE/$BOT_TOKEN/g" "$file"
done

echo -e "${GREEN}Step 5: Setting up PAM...${NC}"
if ! grep -q "ssh_login_notify.sh" /etc/pam.d/sshd; then
    echo "session    optional     pam_exec.so seteuid /usr/local/bin/ssh_login_notify.sh" >> /etc/pam.d/sshd
    echo "PAM configuration added"
else
    echo "PAM already configured"
fi

echo -e "${GREEN}Step 6: Setting up systemd services...${NC}"
cp systemd/*.service /etc/systemd/system/
systemctl daemon-reload

echo -e "${GREEN}Step 7: Setting up Fail2ban...${NC}"
cp config/jail.local.example /etc/fail2ban/jail.local
systemctl restart fail2ban

echo -e "${GREEN}Step 8: Getting Telegram Chat ID...${NC}"
if [ -z "$CHAT_ID" ] || [ "$CHAT_ID" == "YOUR_CHAT_ID_HERE" ]; then
    echo -e "${YELLOW}Please follow these steps:${NC}"
    echo "1. Open Telegram and find your bot"
    echo "2. Send /start to your bot"
    echo "3. Run: python3 /usr/local/bin/get_telegram_chat_id.py"
    echo ""
    read -p "Press Enter to continue after getting your Chat ID..."
fi

echo -e "${GREEN}Step 9: Starting services...${NC}"
systemctl enable ssh-telegram-monitor.service
systemctl enable telegram-action-handler.service
systemctl start ssh-telegram-monitor.service
systemctl start telegram-action-handler.service

echo -e "${GREEN}Step 10: Configuring UFW firewall...${NC}"
ufw --force enable
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'

echo ""
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Installation Complete!${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
echo "Services Status:"
systemctl status ssh-telegram-monitor --no-pager | head -5
systemctl status telegram-action-handler --no-pager | head -5

echo ""
echo -e "${YELLOW}Important:${NC}"
echo "1. Test by attempting SSH login with wrong password"
echo "2. Check Telegram for notifications"
echo "3. Monitor logs: journalctl -u ssh-telegram-monitor -f"
echo ""
echo -e "${GREEN}Your server is now protected!${NC}"