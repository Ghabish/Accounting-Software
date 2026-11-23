"""Password hashing (PBKDF2-HMAC-SHA256, stdlib) and JWT access tokens."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from backend.config import get_settings

ALGORITHM = "HS256"


def hash_password(password: str, iterations: int | None = None) -> str:
    iterations = iterations or get_settings().password_iterations
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations, base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(hash_b64))
    except (ValueError, TypeError):
        return False


def validate_password_strength(password: str) -> list[str]:
    s = get_settings()
    problems = []
    if len(password) < s.min_password_length:
        problems.append(f"at least {s.min_password_length} characters")
    if not any(c.isdigit() for c in password):
        problems.append("a digit")
    if not any(c.isalpha() for c in password):
        problems.append("a letter")
    if password.lower() == password or password.upper() == password:
        problems.append("upper and lower case letters")
    return problems


def create_access_token(user_id: int, token_version: int, minutes: int | None = None) -> tuple[str, datetime]:
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=minutes or s.access_token_minutes)
    payload = {"sub": str(user_id), "ver": token_version, "exp": exp, "iat": datetime.now(timezone.utc),
               "jti": secrets.token_hex(8)}
    return jwt.encode(payload, s.secret_key, algorithm=ALGORITHM), exp


def decode_token(token: str) -> dict:
    return jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
