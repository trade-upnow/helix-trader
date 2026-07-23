import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings


class EncryptionService:
    def __init__(self) -> None:
        settings = get_settings()
        self.key = base64.urlsafe_b64decode(settings.normalized_encryption_key)

    def encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(12)
        aesgcm = AESGCM(self.key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.urlsafe_b64encode(nonce + ciphertext).decode("utf-8")

    def decrypt(self, token: str) -> str:
        payload = base64.urlsafe_b64decode(token.encode("utf-8"))
        nonce, ciphertext = payload[:12], payload[12:]
        aesgcm = AESGCM(self.key)
        try:
            return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
        except InvalidTag as exc:
            raise ValueError(
                "Stored API credentials cannot be decrypted. "
                "The encryption key likely changed; please re-save credentials."
            ) from exc


def mask_api_key(api_key: str) -> str:
    visible = api_key[-4:] if len(api_key) >= 4 else api_key
    return f"{'*' * max(len(api_key) - len(visible), 4)}{visible}"
