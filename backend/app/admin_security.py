"""Small, dependency-free password and signed-session helpers for the local MVP."""

import base64
import hashlib
import hmac
import json
import secrets
import time

from .config import ADMIN_PASSWORD_HASH, ADMIN_SESSION_SECRET, ADMIN_SESSION_TTL_SECONDS


HASH_ALGORITHM = "pbkdf2_sha256"
HASH_ITERATIONS = 310_000


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("รหัสผ่านต้องมีความยาวอย่างน้อย 12 ตัวอักษร")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, HASH_ITERATIONS)
    return f"{HASH_ALGORITHM}${HASH_ITERATIONS}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str) -> bool:
    try:
        algorithm, iteration_text, salt_text, digest_text = ADMIN_PASSWORD_HASH.split("$", 3)
        if algorithm != HASH_ALGORITHM:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), _b64decode(salt_text), int(iteration_text)
        )
        return hmac.compare_digest(digest, _b64decode(digest_text))
    except (TypeError, ValueError):
        return False


def admin_access_configured() -> bool:
    return bool(ADMIN_PASSWORD_HASH) and len(ADMIN_SESSION_SECRET) >= 32


def create_session_token() -> str:
    if not admin_access_configured():
        raise RuntimeError("ยังไม่ได้ตั้งค่า administrator access")
    payload = {"purpose": "admin", "exp": int(time.time()) + max(900, ADMIN_SESSION_TTL_SECONDS)}
    encoded = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(ADMIN_SESSION_SECRET.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{_b64encode(signature)}"


def valid_session_token(token: str | None) -> bool:
    if not token or not admin_access_configured():
        return False
    try:
        encoded, signature_text = token.split(".", 1)
        expected = hmac.new(ADMIN_SESSION_SECRET.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64decode(signature_text)):
            return False
        payload = json.loads(_b64decode(encoded))
        return payload.get("purpose") == "admin" and int(payload.get("exp", 0)) >= int(time.time())
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
