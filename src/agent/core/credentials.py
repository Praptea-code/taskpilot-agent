from cryptography.fernet import Fernet


def encrypt_credential(value: str, key: str) -> str:
    return Fernet(key).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_credential(value: str, key: str) -> str:
    return Fernet(key).decrypt(value.encode("ascii")).decode("utf-8")
