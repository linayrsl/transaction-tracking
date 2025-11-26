from datetime import datetime, timedelta, timezone
from typing import Any
import jwt
from pwdlib import PasswordHash
from app.config import settings

# Initialize password hasher with Argon2
pwd_context = PasswordHash.recommended()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password using Argon2."""
    return pwd_context.hash(password)


def create_access_token(data: dict[str, Any]) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_EXPIRY_MINUTES
    )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate JWT token."""
    return jwt.decode(
        token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )
