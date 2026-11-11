from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from cryptography.fernet import Fernet, InvalidToken
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from commerce_api.core.config import Settings

_password_hash = PasswordHash((Argon2Hasher(),))


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)


def create_access_token(user_id: UUID, settings: Settings) -> tuple[str, int]:
    now = datetime.now(UTC)
    expires_in = settings.access_token_minutes * 60
    token = jwt.encode(
        {"sub": str(user_id), "type": "access", "iat": now, "exp": now + timedelta(seconds=expires_in)},
        settings.jwt_secret_key.get_secret_value(),
        algorithm="HS256",
    )
    return token, expires_in


def decode_access_token(token: str, settings: Settings) -> UUID:
    claims = jwt.decode(
        token,
        settings.jwt_secret_key.get_secret_value(),
        algorithms=["HS256"],
        options={"require": ["sub", "exp", "iat", "type"]},
    )
    if claims.get("type") != "access":
        raise jwt.InvalidTokenError("Wrong token type")
    return UUID(claims["sub"])


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _digital_asset_fernet(settings: Settings) -> Fernet:
    configured_key = settings.digital_asset_encryption_key
    if configured_key is None or not configured_key.get_secret_value():
        raise RuntimeError("DIGITAL_ASSET_ENCRYPTION_KEY is required for digital inventory")
    try:
        return Fernet(configured_key.get_secret_value().encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        raise RuntimeError("DIGITAL_ASSET_ENCRYPTION_KEY must be a valid Fernet key") from None


def encrypt_digital_asset(value: str, settings: Settings) -> bytes:
    return _digital_asset_fernet(settings).encrypt(value.encode("utf-8"))


def decrypt_digital_asset(ciphertext: bytes, settings: Settings) -> str:
    try:
        return _digital_asset_fernet(settings).decrypt(ciphertext).decode("utf-8")
    except InvalidToken:
        raise RuntimeError("Digital asset could not be decrypted with the configured key") from None