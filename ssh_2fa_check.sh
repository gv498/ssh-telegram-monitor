#!/bin/bash

# 2FA Check Script for PAM
# Returns 0 if access allowed, 1 if denied

# Log for debugging
LOG_FILE="/var/log/ssh-monitor/2fa_check.log"
echo "$(date '+%Y-%m-%d %H:%M:%S') - 2FA check for ${PAM_USER}@${PAM_RHOST}" >> "$LOG_FILE"

# Skip 2FA for local connections
if [ "$PAM_RHOST" = "" ] || [ "$PAM_RHOST" = "127.0.0.1" ] || [ "$PAM_RHOST" = "::1" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Skipping 2FA for local connection" >> "$LOG_FILE"
    exit 0
fi

# Run Python 2FA handler
/usr/bin/python3 /root/ssh-telegram-monitor/ssh_pam_2fa.py
RESULT=$?

if [ $RESULT -eq 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - 2FA approved for ${PAM_USER}@${PAM_RHOST}" >> "$LOG_FILE"
    exit 0
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - 2FA denied for ${PAM_USER}@${PAM_RHOST}" >> "$LOG_FILE"
    exit 1
fi