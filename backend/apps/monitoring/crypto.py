from cryptography.fernet import Fernet
from django.conf import settings


def _fernet():
    key = settings.TOKEN_ENCRYPTION_KEY
    if not key:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY not set; cannot encrypt tokens.")
    return Fernet(key.encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
