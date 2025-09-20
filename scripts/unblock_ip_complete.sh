#!/bin/bash

IP=$1

if [ -z "$IP" ]; then
    echo "Usage: $0 <IP_ADDRESS>"
    exit 1
fi

echo "🔓 Unblocking IP: $IP"

# 1. Remove from fail2ban
echo "Removing from fail2ban..."
for jail in $(fail2ban-client status | grep "Jail list:" | sed 's/.*Jail list:\s*//g' | sed 's/,/ /g'); do
    fail2ban-client set "$jail" unbanip "$IP" 2>/dev/null
    echo "  - Removed from jail: $jail"
done

# 2. Remove from UFW
echo "Removing from UFW..."
# Get all rule numbers containing this IP
ufw status numbered | grep "$IP" | while read line; do
    if [[ $line =~ ^\[([0-9]+)\] ]]; then
        rule_num="${BASH_REMATCH[1]}"
        echo "  - Deleting UFW rule #$rule_num"
    fi
done

# Delete all rules containing this IP (in reverse order)
for rule_num in $(ufw status numbered | grep "$IP" | grep -oE '^\[[0-9]+\]' | grep -oE '[0-9]+' | sort -rn); do
    ufw --force delete "$rule_num"
done

# Also try direct deletion
ufw delete deny from "$IP" 2>/dev/null
ufw delete reject from "$IP" 2>/dev/null

# 3. Remove from iptables
echo "Removing from iptables..."

# Remove from INPUT chain
while iptables -C INPUT -s "$IP" -j DROP 2>/dev/null; do
    iptables -D INPUT -s "$IP" -j DROP
    echo "  - Removed DROP rule from INPUT"
done

while iptables -C INPUT -s "$IP" -j REJECT 2>/dev/null; do
    iptables -D INPUT -s "$IP" -j REJECT
    echo "  - Removed REJECT rule from INPUT"
done

# Remove from all fail2ban chains
for chain in $(iptables -L -n | grep "^Chain f2b" | awk '{print $2}'); do
    while iptables -C "$chain" -s "$IP" -j DROP 2>/dev/null; do
        iptables -D "$chain" -s "$IP" -j DROP
        echo "  - Removed from chain: $chain"
    done
    while iptables -C "$chain" -s "$IP" -j REJECT 2>/dev/null; do
        iptables -D "$chain" -s "$IP" -j REJECT
        echo "  - Removed REJECT from chain: $chain"
    done
done

# 4. Clear connection tracking
echo "Clearing connection tracking..."
conntrack -D -s "$IP" 2>/dev/null

# 5. Check if IP is still blocked
echo ""
echo "Verification:"

# Check fail2ban
if fail2ban-client status sshd | grep -q "$IP"; then
    echo "⚠️ IP still found in fail2ban!"
else
    echo "✅ IP not in fail2ban"
fi

# Check iptables
if iptables -L -n | grep -q "$IP"; then
    echo "⚠️ IP still found in iptables!"
    echo "Remaining rules:"
    iptables -L -n | grep "$IP"
else
    echo "✅ IP not in iptables"
fi

# Check UFW
if ufw status | grep -q "$IP"; then
    echo "⚠️ IP still found in UFW!"
else
    echo "✅ IP not in UFW"
fi

echo ""
echo "✅ Unblocking complete for IP: $IP"