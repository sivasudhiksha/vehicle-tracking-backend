from datetime import datetime, timedelta, timezone
from typing import Any
import bcrypt
import jwt

from app.core.config import settings


def get_password_hash(password: str) -> str:
    """Hashes a plaintext password string using bcrypt.

    Generates a secure salt and returns a standard $2b$ bcrypt hash string.
    """
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a bcrypt hashed password string.

    Returns True if the password matches the hash, False otherwise.
    Uses constant-time comparison internally via bcrypt.
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def create_access_token(
    subject: str | int,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Creates an encoded JWT access token with subject, expiration, and optional claims."""
    now = datetime.now(timezone.utc)
    if expires_delta is not None:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": now,
        "exp": expire,
    }

    if extra_claims:
        payload.update(extra_claims)

    encoded_jwt = jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any]:
    """Decodes and validates a JWT access token.

    Raises:
        jwt.ExpiredSignatureError: If token has expired.
        jwt.InvalidTokenError: If signature or format is invalid.

    Returns:
        dict[str, Any]: Decoded token payload claims.
    """
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )
    return payload
