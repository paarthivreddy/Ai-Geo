"""Password hashing and patient ID hashing utilities."""

import bcrypt
import hashlib
import hmac
import secrets
from typing import Tuple


def generate_salt() -> str:
    """Generate a cryptographically secure salt."""
    return secrets.token_hex(16)


def hash_password(password: str, salt: str | None = None) -> Tuple[str, str]:
    """
    Hash a password with bcrypt.

    Args:
        password: Plain text password
        salt: Optional pre-existing salt (for verification)

    Returns:
        Tuple of (password_hash, salt)
    """
    if salt:
        # Use existing salt for verification
        salt_bytes = salt.encode()
    else:
        # Generate new salt
        salt_bytes = bcrypt.gensalt(12)

    password_hash = bcrypt.hashpw(password.encode(), salt_bytes)
    return password_hash.decode(), salt_bytes.decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except Exception:
        return False


def hash_patient_id(patient_id: str, salt: str) -> str:
    """
    Create a deterministic hash of a patient ID for privacy.

    Uses HMAC-SHA256 with a secret salt.

    Args:
        patient_id: Raw patient ID
        salt: Secret salt from settings

    Returns:
        Hex-encoded hash
    """
    return hmac.new(salt.encode(), patient_id.encode(), hashlib.sha256).hexdigest()