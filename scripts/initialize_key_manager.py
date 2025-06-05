#!/usr/bin/env python3
"""
Initialize the secure key management system.
This script sets up the encryption system and helps securely store wallet private keys.
"""
import os
import sys
import logging
import getpass

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.security.key_manager import KeyManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def setup_key_manager():
    """Set up the key management system with a new salt and master password."""
    print("=" * 80)
    print("RUBICON TRADING BOT - SECURE KEY MANAGEMENT SETUP")
    print("=" * 80)
    print("\nThis utility will set up secure storage for your Ethereum private keys.")
    print("WARNING: Losing your master password will make stored keys unrecoverable!")
    print()

    # Create key manager
    key_manager = KeyManager()

    # Generate salt
    salt = key_manager.generate_salt()
    if not salt:
        return False

    # Set up master password
    password = getpass.getpass("Create a strong master password: ")
    confirm = getpass.getpass("Confirm master password: ")

    if password != confirm:
        logger.error("Passwords do not match.")
        return False

    if len(password) < 12:
        logger.warning("Password is shorter than 12 characters. Consider using a stronger password.")
        proceed = input("Continue anyway? (y/n): ")
        if proceed.lower() != 'y':
            return False

    # Initialize encryption with password
    if not key_manager.initialize_encryption(password):
        logger.error("Failed to initialize encryption")
        return False

    # Add initial key if needed
    add_key = input("Would you like to add an Ethereum private key now? (y/n): ")
    if add_key.lower() == 'y':
        name = input("Enter a name for this key (e.g., 'mainnet_trading'): ")
        key = getpass.getpass("Enter the private key (without '0x' prefix): ")

        if key_manager.add_key(name, key):
            logger.info(f"Key '{name}' added successfully")
        else:
            logger.error(f"Failed to add key '{name}'")

    print("\nKey manager setup complete!")
    print(f"Salt stored at: {key_manager.salt_path}")
    print(f"Encrypted keys will be stored at: {key_manager.key_file_path}")
    print("\nTo use the key manager in your code:")
    print("1. Create a KeyManager instance")
    print("2. Call initialize_encryption() with the master password")
    print("3. Use get_key(name) to retrieve your private keys")

    return True

if __name__ == "__main__":
    if setup_key_manager():
        sys.exit(0)
    else:
        sys.exit(1)
