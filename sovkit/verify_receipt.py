#!/usr/bin/env python3
"""Standalone offline verifier (stdlib + cryptography only).

Usage: python verify_receipt.py <file> <file.sig> <pubkey> --expect-keyid <hex>
  <file.sig>  base64 ed25519 signature over the exact bytes of <file>
  <pubkey>    path to a file holding the base64 raw 32-byte public key (or the key itself)
  --expect-keyid  REQUIRED trusted pin: sha256 hex of the raw public key. A key found beside the
              artefact is untrusted unless its keyid matches the pin.
Exit 0 = valid, 1 = INVALID, 2 = usage/input error.
"""

import base64
import os
import sys


def verify(file_path, sig_path, pub, expect_keyid=None):
    import hashlib

    if not expect_keyid:
        raise ValueError("expect_keyid is required: no unpinned verification")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    if os.path.exists(pub):
        pub = open(pub).read()
    sig = base64.b64decode(open(sig_path).read().strip())
    raw = base64.b64decode(pub.strip())
    if hashlib.sha256(raw).hexdigest() != expect_keyid.strip().lower():
        raise ValueError("key does not match pin")
    key = Ed25519PublicKey.from_public_bytes(raw)
    key.verify(sig, open(file_path, "rb").read())


def main(argv):
    if len(argv) != 6 or argv[4] != "--expect-keyid":
        print(__doc__)
        return 2
    try:
        verify(argv[1], argv[2], argv[3], argv[5])
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return 2
    except Exception:
        print("INVALID signature")
        return 1
    print("OK signature valid")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
