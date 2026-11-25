import hashlib
import secrets


def hash_api_key(token: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{token}".encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    salt = secrets.token_hex(16)
    token = secrets.token_urlsafe(32)
    return token, salt, hash_api_key(token, salt)
