"""Fernet encrypt/decrypt for any token persisted to the DB.

ponytail: integrations currently read keys straight from .env, nothing is
stored, so this is unused today. Kept minimal for the moment a token must be
saved (e.g. OAuth refresh tokens). Set TOKEN_ENCRYPTION_KEY to enable.
"""
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
