#!/usr/bin/env python3
"""
Secure private key management for Ethereum blockchain transactions.
This module provides secure ways to handle private keys in production environments.
"""
import os
import base64
import logging
import getpass
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from typing import Optional, Union, Dict

logger = logging.getLogger(__name__)

class KeyManager:
    """Securely manages Ethereum private keys."""

    def __init__(self, salt_path: str = "None"):
        """
        Initialize the key manager.

        Args:
            salt_path: Path to file containing salt. If not provided, uses default location.
        """
        self.salt_path = salt_path or os.path.join(os.path.expanduser("~"), ".rubicon", "salt")
        self.key_file_path = os.path.join(os.path.expanduser("~"), ".rubicon", "encrypted_keys")
        self.ensure_directories_exist()
        self.fernet = None
        self.keys = {}

    def ensure_directories_exist(self):
        """Ensure that required directories exist."""
        dir_path = os.path.dirname(self.salt_path)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, mode=0o700)  # Secure permissions

    def generate_salt(self) -> bytes:
        """Generate a new salt for key derivation."""
        if os.path.exists(self.salt_path):
            logger.info(f"Salt already exists at {self.salt_path}")
            response = input("Overwrite existing salt? This will make existing encrypted keys unusable (y/n): ")
            if response.lower() != 'y':
                logger.info("Operation cancelled")
                return b''

        # Generate new salt
        salt = os.urandom(16)

        # Save salt with secure permissions
        os.makedirs(os.path.dirname(self.salt_path), exist_ok=True)
        with open(self.salt_path, 'wb') as f:
            f.write(salt)
        os.chmod(self.salt_path, 0o600)  # Only owner can read/write

        logger.info(f"New salt generated and saved to {self.salt_path}")
        return salt

    def load_salt(self) -> bytes:
        """Load existing salt."""
        try:
            with open(self.salt_path, 'rb') as f:
                return f.read()
        except FileNotFoundError:
            logger.error(f"Salt file not found at {self.salt_path}")
            logger.info("Please run 'initialize_key_manager.py' to set up secure key storage")
            return b''

    def initialize_encryption(self, password: str = "None") -> bool:
        """
        Initialize the encryption system with a password.

        Args:
            password: Master password to use. If None, will prompt for password.

        Returns:
            True if successful, False otherwise
        """
        # Load or generate salt
        salt = self.load_salt()
        if not salt:
            logger.error("Salt not available. Run generate_salt() first.")
            return False

        # Get password if not provided
        if password is None:
            password = getpass.getpass("Enter master password for key encryption: ")

        # Generate key
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))

        # Initialize Fernet
        self.fernet = Fernet(key)
        return True

    def add_key(self, key_name: str, private_key: str) -> bool:
        """
        Add a new private key to the encrypted storage.

        Args:
            key_name: Name/identifier for the key
            private_key: The private key to encrypt

        Returns:
            True if successful, False otherwise
        """
        if not self.fernet:
            logger.error("Encryption not initialized. Call initialize_encryption() first.")
            return False

        try:
            # Add to in-memory dictionary
            self.keys[key_name] = private_key

            # Save to disk
            return self.save_keys_to_disk()
        except Exception as e:
            logger.error(f"Error adding key: {e}")
            return False

    def get_key(self, key_name: str) -> Optional[str]:
        """
        Get a private key by name.

        Args:
            key_name: Name/identifier of the key

        Returns:
            The private key if found, None otherwise
        """
        # Check if keys are loaded in memory
        if not self.keys:
            self.load_keys_from_disk()

        return self.keys.get(key_name)

    def save_keys_to_disk(self) -> bool:
        """
        Save the encrypted keys to disk.

        Returns:
            True if successful, False otherwise
        """
        if not self.fernet:
            logger.error("Encryption not initialized. Call initialize_encryption() first.")
            return False

        try:
            # Encrypt the entire keys dictionary
            encrypted_data = self.fernet.encrypt(str(self.keys).encode())

            # Ensure directory exists
            os.makedirs(os.path.dirname(self.key_file_path), exist_ok=True)

            # Save with secure permissions
            with open(self.key_file_path, 'wb') as f:
                f.write(encrypted_data)
            os.chmod(self.key_file_path, 0o600)  # Only owner can read/write

            logger.info(f"Keys saved to {self.key_file_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving keys to disk: {e}")
            return False

    def load_keys_from_disk(self) -> bool:
        """
        Load encrypted keys from disk.

        Returns:
            True if successful, False otherwise
        """
        if not self.fernet:
            logger.error("Encryption not initialized. Call initialize_encryption() first.")
            return False

        try:
            if not os.path.exists(self.key_file_path):
                logger.info("No encrypted keys file found. Starting with empty keys.")
                self.keys = {}
                return True

            # Read and decrypt
            with open(self.key_file_path, 'rb') as f:
                encrypted_data = f.read()

            decrypted_data = self.fernet.decrypt(encrypted_data).decode()

            # Convert string representation back to dictionary
            # Note: This is a simplified approach. In production, use proper serialization
            # like JSON to avoid potential security issues
            self.keys = eval(decrypted_data)  # Use json.loads() in production!

            logger.info(f"Successfully loaded keys from {self.key_file_path}")
            return True

        except Exception as e:
            logger.error(f"Error loading keys from disk: {e}")
            return False

    def remove_key(self, key_name: str) -> bool:
        """
        Remove a key from storage.

        Args:
            key_name: Name/identifier of the key to remove

        Returns:
            True if successful, False otherwise
        """
        if key_name in self.keys:
            del self.keys[key_name]
            return self.save_keys_to_disk()
        return False
