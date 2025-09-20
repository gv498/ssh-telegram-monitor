#!/bin/bash

# Setup script for SSH Monitor with Telegram Groups and 2FA
# Run this script to configure the system with group topics and 2FA support

set -e

echo "SSH Telegram Monitor - Group & 2FA Setup"
echo "========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root"
    exit 1
fi

# Install dependencies
echo "Installing dependencies..."
apt-get update
apt-get install -y python3 python3-pip python3-venv

# Install Python packages
echo "Installing Python packages..."
pip3 install python-telegram-bot python-dotenv psutil requests aiofiles

# Create directories
echo "Creating directories..."
mkdir -p /var/lib/ssh-monitor
mkdir -p /var/log/ssh-monitor

# Set permissions
chmod +x /root/ssh-telegram-monitor/*.py
chmod +x /root/ssh-telegram-monitor/*.sh

# Copy scripts to system locations
echo "Installing scripts..."
cp /root/ssh-telegram-monitor/ssh_pam_2fa.py /usr/local/bin/
cp /root/ssh-telegram-monitor/ssh_login_notify_v2.sh /usr/local/bin/
cp /root/ssh-telegram-monitor/telegram_group_manager.py /usr/local/bin/
cp /root/ssh-telegram-monitor/ssh_2fa_handler.py /usr/local/bin/
cp /root/ssh-telegram-monitor/ssh_notify_groups.py /usr/local/bin/
cp /root/ssh-telegram-monitor/telegram_callback_handler.py /usr/local/bin/

chmod +x /usr/local/bin/ssh_pam_2fa.py
chmod +x /usr/local/bin/ssh_login_notify_v2.sh
chmod +x /usr/local/bin/telegram_group_manager.py
chmod +x /usr/local/bin/ssh_2fa_handler.py
chmod +x /usr/local/bin/ssh_notify_groups.py
chmod +x /usr/local/bin/telegram_callback_handler.py

# Update PAM configuration for 2FA
echo "Configuring PAM for 2FA..."
PAM_CONFIG="/etc/pam.d/sshd"

# Remove old PAM configuration if exists
sed -i '/pam_exec.so.*ssh_login_notify.sh/d' "$PAM_CONFIG"
sed -i '/pam_exec.so.*ssh_telegram_notify.py/d' "$PAM_CONFIG"

# Add new PAM configuration for 2FA
if ! grep -q "ssh_login_notify_v2.sh" "$PAM_CONFIG"; then
    echo "session optional pam_exec.so seteuid /usr/local/bin/ssh_login_notify_v2.sh" >> "$PAM_CONFIG"
    echo "PAM configuration updated for 2FA"
else
    echo "PAM configuration already set for 2FA"
fi

# Create systemd service for callback handler
echo "Creating systemd service for callback handler..."
cat > /etc/systemd/system/telegram-callback-handler.service << 'EOF'
[Unit]
Description=Telegram Callback Handler for SSH Monitor
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/ssh-telegram-monitor
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/usr/bin/python3 /usr/local/bin/telegram_callback_handler.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and start services
echo "Starting services..."
systemctl daemon-reload
systemctl enable telegram-callback-handler.service
systemctl restart telegram-callback-handler.service

# Initialize Telegram group topics
echo "Initializing Telegram group topics..."
echo "The bot will:"
echo "  1. Rename your group to include server IP"
echo "  2. Create 5 organized topics for different notifications"
echo "  3. Configure the monitoring system"
echo ""
python3 /usr/local/bin/telegram_group_manager.py

echo ""
echo "========================================="
echo "Setup completed successfully!"
echo ""
echo "Next steps:"
echo "1. Copy .env.example to .env and configure your tokens:"
echo "   cp .env.example .env"
echo "   nano .env"
echo ""
echo "2. Add your bot as admin to the Telegram group"
echo ""
echo "3. Enable 'Topics' (Forums) in your Telegram group settings"
echo ""
echo "4. Run /init command in the group to create topics"
echo ""
echo "5. Test SSH login to verify 2FA is working"
echo ""
echo "To check service status:"
echo "  systemctl status telegram-callback-handler"
echo ""
echo "To view logs:"
echo "  journalctl -u telegram-callback-handler -f"
echo "  tail -f /var/log/ssh-monitor/2fa.log"