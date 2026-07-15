from cryptography.fernet import Fernet
from config import Config

_fernet = None


def _get_fernet():
    global _fernet
    if _fernet is None:
        if not Config.PHONE_ENCRYPTION_KEY:
            raise RuntimeError("PHONE_ENCRYPTION_KEY is not set in .env")
        _fernet = Fernet(Config.PHONE_ENCRYPTION_KEY.encode())
    return _fernet


def encrypt_phone(phone_number: str) -> str:
    """Encrypts a phone number for storage. Returns a string safe to store in the DB."""
    return _get_fernet().encrypt(phone_number.encode()).decode()


def decrypt_phone(encrypted_phone: str) -> str:
    """Decrypts a stored phone number back to plain E.164 format for sending SMS."""
    return _get_fernet().decrypt(encrypted_phone.encode()).decode()