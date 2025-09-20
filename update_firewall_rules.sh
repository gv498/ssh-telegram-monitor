#!/bin/bash

# Update firewall rules from blocked IPs database
# This ensures blocked IPs are rejected at the network level

BLOCKED_IPS_FILE="/var/lib/ssh-monitor/blocked_ips.json"

# Function to update iptables rules
update_iptables() {
    if [ -f "$BLOCKED_IPS_FILE" ]; then
        # Clear existing SSH_BLOCKED chain if it exists
        iptables -F SSH_BLOCKED 2>/dev/null || iptables -N SSH_BLOCKED

        # Extract IPs from JSON and add to chain
        BLOCKED_IPS=$(python3 -c "
import json
try:
    with open('$BLOCKED_IPS_FILE', 'r') as f:
        data = json.load(f)
        for ip in data.keys():
            print(ip)
except:
    pass
")

        for IP in $BLOCKED_IPS; do
            # Add REJECT rule (immediate rejection, not DROP which causes timeout)
            iptables -A SSH_BLOCKED -s "$IP" -j REJECT --reject-with tcp-reset 2>/dev/null
        done

        # Insert rule to check SSH_BLOCKED chain for port 22
        iptables -D INPUT -p tcp --dport 22 -j SSH_BLOCKED 2>/dev/null
        iptables -I INPUT -p tcp --dport 22 -j SSH_BLOCKED

        echo "Updated firewall rules for blocked IPs"
    fi
}

# Run the update
update_iptables