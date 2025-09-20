#!/usr/bin/env python3
import os
import sys
import pwd
import time
import asyncio
import logging
from ssh_2fa_handler import SSH2FAHandler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - SSH_PAM_2FA - %(levelname)s - %(message)s',
    filename='/var/log/ssh_2fa.log'
)
logger = logging.getLogger(__name__)

def get_pam_env(key: str) -> str:
    """Get PAM environment variable"""
    return os.environ.get(f'PAM_{key}', '')

async def pam_auth():
    """PAM authentication hook for 2FA"""
    try:
        # Get PAM environment variables
        pam_user = get_pam_env('USER')
        pam_rhost = get_pam_env('RHOST')
        pam_service = get_pam_env('SERVICE')
        pam_type = get_pam_env('TYPE')

        # Also check SSH environment variables
        ssh_client = os.environ.get('SSH_CLIENT', '').split()[0] if os.environ.get('SSH_CLIENT') else ''
        ssh_connection = os.environ.get('SSH_CONNECTION', '').split()[0] if os.environ.get('SSH_CONNECTION') else ''

        # Determine IP address
        ip = pam_rhost or ssh_client or ssh_connection or 'unknown'

        # Skip for local connections
        if ip in ['127.0.0.1', 'localhost', '::1', 'unknown']:
            logger.info(f"Skipping 2FA for local connection: {pam_user}@{ip}")
            return 0

        logger.info(f"2FA check for {pam_user}@{ip} (service={pam_service}, type={pam_type})")

        # Get current process PID
        pid = os.getpid()

        # Initialize 2FA handler
        handler = SSH2FAHandler()

        # Check if 2FA is required
        if handler.check_2fa_required(ip):
            logger.info(f"2FA required for {pam_user}@{ip}")

            # Request 2FA approval
            approved = await handler.request_2fa_approval(pam_user, ip, pid)

            if not approved:
                logger.warning(f"2FA denied for {pam_user}@{ip}")
                return 1  # PAM_AUTH_ERR

        logger.info(f"2FA approved or not required for {pam_user}@{ip}")
        return 0  # PAM_SUCCESS

    except Exception as e:
        logger.error(f"Error in PAM 2FA module: {e}")
        # Don't block on errors
        return 0

def main():
    """Main entry point for PAM module"""
    try:
        # Run async function
        result = asyncio.run(pam_auth())
        sys.exit(result)
    except Exception as e:
        logger.error(f"Fatal error in PAM 2FA: {e}")
        # Don't block on errors
        sys.exit(0)

if __name__ == "__main__":
    main()