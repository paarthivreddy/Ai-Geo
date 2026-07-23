"""Encryption utilities for sensitive data at rest."""

import os
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64


class EncryptionManager:
    """Manage encryption/decryption of sensitive data at rest."""

    def __init__(self, key: Optional[bytes] = None):
        """
        Initialize with encryption key.

        Args:
            key: 32-byte key for Fernet encryption. If not provided, generates from env.
        """
        if key:
            self.key = key
        else:
            # In production, this should come from a key management system
            # For now, derive from environment variable
            import os
            master_key = os.getenv("ENCRYPTION_MASTER_KEY", "dev-master-key-change-in-production")
            self.key = self._derive_key(master_key.encode())

        self.fernet = Fernet(self.key)

    def _derive_key(self, master_key: bytes) -> bytes:
        """Derive Fernet key from master key using PBKDF2."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"geocare-salt",  # In production, use random salt per field
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(master_key))
        return key

    def encrypt(self, data: str) -> str:
        """
        Encrypt a string.

        Args:
            data: Plain text to encrypt

        Returns:
            Base64 encoded encrypted data
        """
        encrypted = self.fernet.encrypt(data.encode())
        return base64.urlsafe_b64encode(encrypted).decode()

    def decrypt(self, encrypted_data: str) -> str:
        """
        Decrypt a string.

        Args:
            encrypted_data: Base64 encoded encrypted data

        Returns:
            Decrypted plain text
        """
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
        decrypted = self.fernet.decrypt(encrypted_bytes)
        return decrypted.decode()

    def encrypt_bytes(self, data: bytes) -> bytes:
        """Encrypt raw bytes."""
        return self.fernet.encrypt(data)

    def decrypt_bytes(self, encrypted_data: bytes) -> bytes:
        """Decrypt raw bytes."""
        return self.fernet.decrypt(encrypted_data)


# Global instance (initialized at startup)
encryption_manager: Optional[EncryptionManager] = None


def get_encryption_manager() -> EncryptionManager:
    """Get or create global encryption manager."""
    global encryption_manager
    if encryption_manager is None:
        encryption_manager = EncryptionManager()
    return encryption_manager


# Field-level encryption helpers
def encrypt_pii_field(value: str) -> str:
    """Encrypt a PII field (patient name, phone, etc.)."""
    return get_encryption_manager().encrypt(value)


def decrypt_pii_field(encrypted_value: str) -> str:
    """Decrypt a PII field."""
    return get_encryption_manager().decrypt(encrypted_value)