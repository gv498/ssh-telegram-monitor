#!/bin/bash

# Setup DDoS protection for SSH
echo "Setting up DDoS protection for SSH..."

# 1. Create rate limiting with iptables
echo "Creating rate limiting rules..."

# Remove old rules if exist
iptables -F SSH_RATELIMIT 2>/dev/null
iptables -X SSH_RATELIMIT 2>/dev/null

# Create new chain
iptables -N SSH_RATELIMIT

# Rate limit: Allow 3 connection attempts per minute per IP
iptables -A SSH_RATELIMIT -m recent --name SSH --set --rsource
iptables -A SSH_RATELIMIT -m recent --name SSH --update --seconds 60 --hitcount 4 --rsource -j REJECT --reject-with tcp-reset

# Apply to SSH port
iptables -D INPUT -p tcp --dport 22 -m state --state NEW -j SSH_RATELIMIT 2>/dev/null
iptables -I INPUT -p tcp --dport 22 -m state --state NEW -j SSH_RATELIMIT

# 2. Connection limit per IP
echo "Setting connection limits..."

# Max 2 parallel connections per IP
iptables -A INPUT -p tcp --dport 22 -m connlimit --connlimit-above 2 -j REJECT --reject-with tcp-reset

# 3. SYN flood protection
echo "Enabling SYN flood protection..."
echo 1 > /proc/sys/net/ipv4/tcp_syncookies
echo 2048 > /proc/sys/net/ipv4/tcp_max_syn_backlog
echo 3 > /proc/sys/net/ipv4/tcp_synack_retries

# 4. Update sysctl for better performance
cat >> /etc/sysctl.d/99-ssh-ddos.conf <<EOF
# SSH DDoS Protection
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_max_syn_backlog = 2048
net.ipv4.tcp_synack_retries = 3
net.ipv4.tcp_syn_retries = 3

# Connection tracking
net.netfilter.nf_conntrack_max = 100000
net.netfilter.nf_conntrack_tcp_timeout_established = 3600
net.netfilter.nf_conntrack_tcp_timeout_time_wait = 60
net.netfilter.nf_conntrack_tcp_timeout_close_wait = 60
net.netfilter.nf_conntrack_tcp_timeout_fin_wait = 60

# Rate limiting
net.core.somaxconn = 1024
EOF

sysctl -p /etc/sysctl.d/99-ssh-ddos.conf

echo "✅ DDoS protection configured"