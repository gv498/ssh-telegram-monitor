#!/bin/bash

# GitHub Push Script for SSH Telegram Monitor
# ============================================

echo "📦 SSH Telegram Monitor - GitHub Push Script"
echo "==========================================="
echo ""

# Check if we're in the right directory
if [ ! -f "README.md" ] || [ ! -d ".git" ]; then
    echo "❌ Error: Not in the project directory!"
    echo "Please run from /root/ssh-telegram-monitor/"
    exit 1
fi

# Get GitHub username
read -p "Enter your GitHub username: " GITHUB_USER
if [ -z "$GITHUB_USER" ]; then
    echo "❌ Username cannot be empty!"
    exit 1
fi

# Repository name
REPO_NAME="ssh-telegram-monitor"

echo ""
echo "📌 Setting up remote repository..."
git remote remove origin 2>/dev/null  # Remove if exists
git remote add origin "https://github.com/${GITHUB_USER}/${REPO_NAME}.git"

echo "📌 Switching to main branch..."
git branch -M main

echo ""
echo "🚀 Ready to push to: https://github.com/${GITHUB_USER}/${REPO_NAME}"
echo ""
echo "⚠️  Make sure you've created the repository on GitHub first!"
echo "   Go to: https://github.com/new"
echo "   Name: ${REPO_NAME}"
echo "   Select: Public"
echo "   DON'T initialize with README"
echo ""
read -p "Press Enter when ready to push..."

echo ""
echo "📤 Pushing to GitHub..."
git push -u origin main

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Success! Your project is now on GitHub!"
    echo ""
    echo "🔗 Repository URL: https://github.com/${GITHUB_USER}/${REPO_NAME}"
    echo "📄 Clone command: git clone https://github.com/${GITHUB_USER}/${REPO_NAME}.git"
    echo ""
    echo "📌 Next steps:"
    echo "1. Add a nice description on GitHub"
    echo "2. Add topics: ssh, security, telegram, monitoring, linux"
    echo "3. Star the repo ⭐"
    echo "4. Share with the community!"
else
    echo ""
    echo "❌ Push failed. Possible issues:"
    echo "1. Repository doesn't exist on GitHub"
    echo "2. Authentication failed (you'll need to enter username/password or token)"
    echo "3. Network issues"
    echo ""
    echo "For authentication, use:"
    echo "- Username: your GitHub username"
    echo "- Password: your Personal Access Token (not password!)"
    echo ""
    echo "To create a token:"
    echo "1. Go to: https://github.com/settings/tokens"
    echo "2. Generate new token (classic)"
    echo "3. Select 'repo' scope"
    echo "4. Use the token as password"
fi