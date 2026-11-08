#!/usr/bin/env python3
"""Standalone offline verifier (stdlib + cryptography only).

Usage: python verify_receipt.py <file> <file.sig> <pubkey>
  <file.sig>  base64 ed25519 signature over the exact bytes of <file>
  <pubkey>    path to a file holding the base64 raw 32-byte public key (or the key itself)
Exit 0 = valid, 1 = INVALID, 2 = usage/input error.
"""

import base64
import os
import sys


def verify(file_path, sig_path, pub):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    if os.path.exists(pub):
        pub = open(pub).read()
    sig = base64.b64decode(open(sig_path).read().strip())
    key = Ed25519PublicKey.from_public_bytes(base64.b64decode(pub.strip()))
    key.verify(sig, open(file_path, "rb").read())


def main(argv):
    if len(argv) != 4:
        print(__doc__)
        return 2
    try:
        verify(*argv[1:])
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
