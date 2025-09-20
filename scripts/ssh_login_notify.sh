#!/bin/bash

# Log for debugging
echo "$(date): PAM_TYPE=$PAM_TYPE, PAM_RHOST=$PAM_RHOST, USER=$PAM_USER, TTY=$PAM_TTY" >> /var/log/ssh_telegram.log

# Only notify for SSH sessions
if [ "$PAM_TYPE" = "open_session" ]; then
    # Export environment variables for the Python script
    export SSH_CLIENT="${PAM_RHOST} 0 22"
    export SSH_CONNECTION="${PAM_RHOST} 0 $(hostname -I | awk '{print $1}') 22"
    export USER="${PAM_USER}"
    export PAM_USER="${PAM_USER}"

    # Run notification in background to not delay login
    /usr/local/bin/ssh_telegram_notify.py login >> /var/log/ssh_telegram.log 2>&1 &
fi

exit 0