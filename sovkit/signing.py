"""ed25519 signing, adapted from the nukekit receipt pattern. Keys live under ~/.sovkit/."""

import base64
import hashlib
import json
import os

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def key_path() -> str:
    return os.environ.get("SOVKIT_KEY") or os.path.join(
        os.path.expanduser("~"), ".sovkit", "sovkit_ed25519.pem"
    )


def load_key() -> Ed25519PrivateKey:
    p = key_path()
    if os.path.exists(p):
        return serialization.load_pem_private_key(open(p, "rb").read(), password=None)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    k = Ed25519PrivateKey.generate()
    with open(p, "wb") as f:
        f.write(
            k.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
    return k


def pubkey_b64() -> str:
    raw = (
        load_key()
        .public_key()
        .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    )
    return base64.b64encode(raw).decode()


def keyid() -> str:
    """Lowercase hex sha256 of the raw public key (publish this; verifiers pin it)."""
    return sha256_bytes(base64.b64decode(pubkey_b64()))


def canonical(obj) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def sign_file(path: str, sig_path: str) -> None:
    """Signature is base64 ed25519 over the exact file bytes."""
    sig = load_key().sign(open(path, "rb").read())
    with open(sig_path, "w") as f:
        f.write(base64.b64encode(sig).decode() + "\n")


def write_pubkey(out_dir: str) -> str:
    with open(os.path.join(out_dir, "pubkey.hex"), "w") as f:
        f.write(base64.b64decode(pubkey_b64()).hex() + "\n")
    p = os.path.join(out_dir, "pubkey.b64")
    with open(p, "w") as f:
        f.write(pubkey_b64() + "\n")
    return p
