#!/bin/bash

# SSH Login Notification Script with 2FA Support
# This script is called by PAM on SSH login

# Export PAM variables
export PAM_USER="${PAM_USER}"
export PAM_RHOST="${PAM_RHOST}"
export PAM_SERVICE="${PAM_SERVICE}"
export PAM_TYPE="${PAM_TYPE}"
export PAM_TTY="${PAM_TTY}"

# Log directory
LOG_DIR="/var/log/ssh-monitor"
mkdir -p "$LOG_DIR"

# Log the login attempt
echo "$(date '+%Y-%m-%d %H:%M:%S') - Login: User=${PAM_USER}, IP=${PAM_RHOST}, Service=${PAM_SERVICE}, Type=${PAM_TYPE}" >> "$LOG_DIR/logins.log"

# Check if this is an actual login (not just auth check)
if [ "$PAM_TYPE" = "open_session" ]; then
    # Run 2FA check first (synchronous)
    /usr/bin/python3 /root/ssh-telegram-monitor/ssh_pam_2fa.py
    RESULT=$?

    if [ $RESULT -ne 0 ]; then
        # 2FA failed, deny access
        echo "$(date '+%Y-%m-%d %H:%M:%S') - 2FA denied for ${PAM_USER}@${PAM_RHOST}" >> "$LOG_DIR/2fa.log"
        exit 1
    fi

    # 2FA passed, send notification to Telegram group
    /usr/bin/python3 /root/ssh-telegram-monitor/ssh_notify_groups.py &
fi

# Always allow continuation (PAM will handle the actual auth)
exit 0