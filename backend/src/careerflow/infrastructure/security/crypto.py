"""Encryption of integration secrets at rest (OAuth tokens). Fernet = AES-128-CBC + HMAC.

Run ``python -m careerflow.infrastructure.security.crypto`` to print a new key for
INTEGRATION_ENCRYPTION_KEY.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from careerflow.domain.integrations.ports import IntegrationError


class TokenCipher:
    def __init__(self, key: str) -> None:
        if not key:
            raise IntegrationError(
                "INTEGRATION_ENCRYPTION_KEY is not set; integrations that store tokens are disabled"
            )
        try:
            self._fernet = Fernet(key.encode())
        except (ValueError, TypeError) as error:
            raise IntegrationError("INTEGRATION_ENCRYPTION_KEY is not a valid Fernet key") from error

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken as error:
            raise IntegrationError("stored token could not be decrypted (was the key changed?)") from error


def generate_key() -> str:
    return Fernet.generate_key().decode()


if __name__ == "__main__":
    print(generate_key())
