import hashlib
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.low_level import Type
from starlette.concurrency import run_in_threadpool


SESSION_COOKIE_NAME = "assistant_session"
SESSION_MAX_AGE_SECONDS = 2_592_000

PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65_536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


def normalize_username(raw: str) -> str:
    canonical = raw.strip().lower()
    if not 3 <= len(canonical) <= 50 or re.fullmatch(r"[a-z0-9_]+", canonical) is None:
        raise ValueError("Invalid username.")
    return canonical


def validate_password(password: str) -> None:
    if not 15 <= len(password) <= 128:
        raise ValueError("Invalid password.")


async def hash_password(password: str) -> str:
    validate_password(password)
    return await run_in_threadpool(PASSWORD_HASHER.hash, password)


async def verify_password(encoded_hash: str, password: str) -> bool:
    try:
        return await run_in_threadpool(PASSWORD_HASHER.verify, encoded_hash, password)
    except InvalidHashError, VerificationError:
        return False


def password_needs_rehash(encoded_hash: str) -> bool:
    return PASSWORD_HASHER.check_needs_rehash(encoded_hash)


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
