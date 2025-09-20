#!/bin/bash

# Kill all SSH sessions from a specific IP
IP=$1

if [ -z "$IP" ]; then
    echo "Usage: $0 <IP_ADDRESS>"
    exit 1
fi

echo "Terminating all SSH sessions from IP: $IP"

# Method 1: Kill using netstat/ss
for PID in $(ss -tnp | grep "$IP.*:22" | grep -oP 'pid=\K\d+'); do
    echo "Killing PID $PID"
    kill -9 $PID 2>/dev/null
done

# Method 2: Kill using who and pts
who | grep "$IP" | awk '{print $2}' | while read PTS; do
    echo "Killing all processes on $PTS"
    pkill -9 -t "$PTS"
done

# Method 3: Find and kill sshd processes
ps aux | grep sshd | grep "$IP" | awk '{print $2}' | while read PID; do
    echo "Killing SSH daemon PID $PID"
    kill -9 $PID 2>/dev/null
done

# Method 4: Use lsof to find network connections
lsof -i tcp:22 | grep "$IP" | awk '{print $2}' | uniq | while read PID; do
    echo "Killing PID $PID from lsof"
    kill -9 $PID 2>/dev/null
done

echo "All sessions from $IP terminated"