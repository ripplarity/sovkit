import json
import os
from collections import Counter

from sovkit.mapping import CONTENT_KINDS
from sovkit.models import Estate
from sovkit.signing import canonical, pubkey_b64, sha256_bytes, sign_file, write_pubkey


def finalize(estate: Estate) -> Estate:
    """Flag duplicate UPNs (case-insensitive) and content objects without a hash."""
    seen: dict[str, list] = {}
    for o in estate.objects:
        if o.kind == "user":
            seen.setdefault((o.owner or o.name).lower(), []).append(o)
        if o.kind in CONTENT_KINDS and o.sha256 is None and "UNHASHED" not in o.flags:
            o.flags.append("UNHASHED")
    for group in seen.values():
        if len(group) > 1:
            for o in group:
                if "IDENTITY_COLLISION" not in o.flags:
                    o.flags.append("IDENTITY_COLLISION")
    return estate


def canonical_estate(estate: Estate) -> bytes:
    return canonical(estate.model_dump())


def receipt_md(estate: Estate, digest: str) -> str:
    kinds = Counter(o.kind for o in estate.objects)
    flags = Counter(f for o in estate.objects for f in o.flags)
    lines = [
        "# sovkit inventory receipt",
        "",
        f"- tenant: {estate.tenant_id}",
        f"- captured_at: {estate.captured_at}",
        f"- objects: {len(estate.objects)}",
        f"- total bytes: {sum(o.size_bytes for o in estate.objects)}",
        f"- inventory.json sha256: {digest}",
        f"- public key (ed25519, base64): {pubkey_b64()}",
        "",
        "## Counts by kind",
        "",
    ]
    lines += [f"- {k}: {v}" for k, v in sorted(kinds.items())] or ["- (none)"]
    lines += ["", "## Flags", ""]
    lines += [f"- {k}: {v}" for k, v in sorted(flags.items())] or ["- (none)"]
    lines += [
        "",
        "Verify offline: `python verify_receipt.py inventory.json inventory.sig pubkey.b64`",
        "",
    ]
    return "\n".join(lines)


def write_inventory(estate: Estate, out: str) -> str:
    estate = finalize(estate)
    os.makedirs(out, exist_ok=True)
    data = canonical_estate(estate)
    p = os.path.join(out, "inventory.json")
    with open(p, "wb") as f:
        f.write(data)
    sign_file(p, os.path.join(out, "inventory.sig"))
    write_pubkey(out)
    with open(os.path.join(out, "inventory.receipt.md"), "w", encoding="utf-8") as f:
        f.write(receipt_md(estate, sha256_bytes(data)))
    return p


def load_inventory(out: str) -> Estate:
    return Estate(
        **json.load(open(os.path.join(out, "inventory.json"), encoding="utf-8"))
    )
