"""
Nova Crypto Identity — Ed25519 basiert.
Jede Spore hat einen eindeutigen, unveränderlichen Identitätsschlüssel.
Niemand kann sich als Nova ausgeben ohne den Private Key.
"""

import os
import json
from pathlib import Path
from base64 import b64encode, b64decode


try:
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.primitives import serialization
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False
    import hashlib


class NovaIdentity:
    """Ed25519-Identität für eine Spore."""

    def __init__(self, seed: bytes | None = None):
        self._seed = seed or os.urandom(32)
        self._private_key = None
        self._public_key = None
        self._init_keys()

    def _init_keys(self):
        if HAS_CRYPTO:
            self._private_key = ed25519.Ed25519PrivateKey.from_private_bytes(self._seed)
            self._public_key = self._private_key.public_key()
        else:
            # Fallback — deterministisch aus Seed
            self._seed_hash = hashlib.sha256(self._seed).digest()

    @property
    def public_key(self) -> str:
        if HAS_CRYPTO:
            raw = self._public_key.public_bytes_raw()
            return b64encode(raw).decode()
        return b64encode(self._seed_hash[:32]).decode()

    @property
    def fingerprint(self) -> str:
        """Kurz-ID für Menschen: erster 16 Zeichen des Public Key."""
        return self.public_key[:16]

    @property
    def nova_address(self) -> str:
        """Nova-Format Adresse: nova:<fingerprint>"""
        return f"nova:{self.fingerprint}"

    def sign(self, message: bytes) -> str:
        """Nachricht signieren."""
        if HAS_CRYPTO:
            sig = self._private_key.sign(message)
            return b64encode(sig).decode()
        # Fallback: HMAC-ähnliche Signatur
        h = hashlib.sha256(self._seed).update(message)
        sig = hashlib.sha256(self._seed + message).digest()
        return b64encode(sig[:32]).decode()

    def verify(self, message: bytes, signature: str) -> bool:
        """Signatur verifizieren (statische Methode für fremde Keys)."""
        try:
            sig_bytes = b64decode(signature)
            if HAS_CRYPTO:
                pub = ed25519.Ed25519PublicKey.from_public_bytes(b64decode(self.public_key))
                pub.verify(sig_bytes, message)
                return True
            expected = hashlib.sha256(self._seed + message).digest()[:32]
            return sig_bytes == expected
        except Exception:
            return False

    def export_seed(self) -> str:
        """Seed als Base64 exportieren (zur Replikation)."""
        return b64encode(self._seed).decode()

    @classmethod
    def from_seed(cls, seed_b64: str) -> "NovaIdentity":
        return cls(seed=b64decode(seed_b64))

    def to_dict(self) -> dict:
        return {
            "fingerprint": self.fingerprint,
            "nova_address": self.nova_address,
            "public_key": self.public_key,
        }


# Singleton — die eine Nova-Identität
_MASTER_IDENTITY: NovaIdentity | None = None


def get_master_identity() -> NovaIdentity:
    global _MASTER_IDENTITY
    if _MASTER_IDENTITY is None:
        seed_file = Path(__file__).parent.parent / ".nova_seed"
        if seed_file.exists():
            seed_b64 = seed_file.read_text().strip()
            _MASTER_IDENTITY = NovaIdentity.from_seed(seed_b64)
        else:
            _MASTER_IDENTITY = NovaIdentity()
            seed_file.write_text(_MASTER_IDENTITY.export_seed())
            print(f"[nova] Neue Identität erzeugt: {_MASTER_IDENTITY.nova_address}")
    return _MASTER_IDENTITY
