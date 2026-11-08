"""attest-spec v1 writer: DSSE envelope over an in-toto Statement v1 (see attest-spec/SPEC.md)."""

import base64
import hashlib
import json
import os
import platform
import time

from cryptography.hazmat.primitives import serialization

from sovkit import __version__
from sovkit.signing import load_key, sha256_file

PAYLOAD_TYPE = "application/vnd.in-toto+json"
BASE = "https://ripplarity.com/attestation/"


def utc(t=None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def pae(payload_type: str, payload: bytes) -> bytes:
    t = payload_type.encode("utf-8")
    return b"DSSEv1 %d %s %d %s" % (len(t), t, len(payload), payload)


def pub_raw(key) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )


def keyid(key) -> str:
    return hashlib.sha256(pub_raw(key)).hexdigest()


def statement(subject_paths, ptype, extra, started, ended, run_mode) -> dict:
    return {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [
            {"name": os.path.basename(p), "digest": {"sha256": sha256_file(p)}}
            for p in subject_paths
        ],
        "predicateType": BASE + ptype,
        "predicate": {
            "producer": {"tool": "sovkit", "version": __version__},
            "started": started,
            "ended": ended,
            "environment": {"host_os": platform.system().lower(), "run_mode": run_mode},
            **extra,
        },
    }


def make_envelope(stmt: dict, key) -> dict:
    payload = json.dumps(
        stmt, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    sig = key.sign(pae(PAYLOAD_TYPE, payload))
    return {
        "payloadType": PAYLOAD_TYPE,
        "payload": base64.b64encode(payload).decode(),
        "signatures": [{"keyid": keyid(key), "sig": base64.b64encode(sig).decode()}],
    }


def write_attestation(out_path, subject_paths, ptype, extra, started, ended, run_mode):
    key = load_key()
    env = make_envelope(
        statement(subject_paths, ptype, extra, started, ended, run_mode), key
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(env, f, indent=2)
        f.write("\n")
    return out_path


def run_mode(out: str) -> str:
    return "FIXTURE" if os.path.exists(os.path.join(out, "fixture.path")) else "REAL"
