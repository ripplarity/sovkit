"""Dry-run migration into a local target tree, then verification by re-inventory."""

import json
import os
import re
import time

from sovkit.inventory import load_inventory
from sovkit.mapping import map_object
from sovkit.signing import canonical, sha256_bytes, sha256_file, sign_file
from sovkit.sources.fixture import load_fixture
from sovkit.verify_receipt import verify as verify_sig

LAYOUT = {
    "user": "keycloak/users",
    "group": "keycloak/groups",
    "mailbox": "ox/mail",
    "site": "nextcloud/sites",
    "onedrive": "nextcloud/users",
    "team": "element/rooms",
    "document": "nextcloud/documents",
    "planner": "openproject/projects",
}
_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def sanitize(name: str, limit: int = 200) -> str:
    """Safe single path component; keeps the extension, caps length."""
    stem, ext = os.path.splitext(_BAD.sub("_", name).strip(" ."))
    ext = ext[:16]
    return (stem[: max(1, limit - len(ext))] or "_") + ext


def target_rel(o) -> str:
    if o.kind == "mailbox":
        ext = ".eml"
    elif o.kind == "document":
        ext = os.path.splitext(o.name)[1][:16]
    else:
        ext = ".json"
    stem = sanitize(
        os.path.splitext(o.name)[0] if o.kind == "document" else o.name, 150
    )
    return f"{LAYOUT[o.kind]}/{sanitize(o.id, 40)}_{stem}{ext}"


def run_drill(out: str, target: str, fixture: str) -> dict:
    estate = load_inventory(out)
    _, files = load_fixture(fixture)
    t0 = time.time()
    entries, skipped = [], []
    for o in estate.objects:
        if not map_object(o)["mapped"]:
            skipped.append(o.id)
            continue
        if o.id in files:
            data = open(files[o.id], "rb").read()
        elif o.kind in ("document", "onedrive", "mailbox", "site"):
            data = b"\0" * o.size_bytes
        else:
            data = canonical(o.model_dump())
        rel = target_rel(o)
        p = os.path.join(target, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
        mode = "size" if "UNHASHED" in o.flags and o.id not in files else "hash"
        entries.append(
            {
                "id": o.id,
                "path": rel,
                "mode": mode,
                "size": len(data),
                "sha256": sha256_bytes(data),
                "original_name": o.name,
            }
        )
    t1 = time.time()
    manifest = {
        "fixture": fixture,
        "target": os.path.abspath(target),
        "started": t0,
        "ended": t1,
        "copy_seconds": round(t1 - t0, 3),
        "entries": entries,
        "skipped_unmapped": skipped,
    }
    with open(os.path.join(out, "drill.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    return manifest


def verify_drill(out: str) -> dict:
    t0 = time.time()
    m = json.load(open(os.path.join(out, "drill.json"), encoding="utf-8"))
    target = m["target"]
    expected = {e["path"]: e for e in m["entries"]}
    actual = set()
    for root, _, fs in os.walk(target):
        for fn in fs:
            actual.add(
                os.path.relpath(os.path.join(root, fn), target).replace(os.sep, "/")
            )
    missing = sorted(set(expected) - actual)
    extra = sorted(actual - set(expected))
    mismatch, by_size = [], 0
    for rel, e in expected.items():
        if rel in missing:
            continue
        p = os.path.join(target, *rel.split("/"))
        if e["mode"] == "size":
            by_size += 1
            if os.path.getsize(p) != e["size"]:
                mismatch.append(rel)
        elif sha256_file(p) != e["sha256"]:
            mismatch.append(rel)
    diff = {"missing": missing, "extra": extra, "hash_mismatch": sorted(mismatch)}
    inv = os.path.join(out, "inventory.json")
    sig_ok = True
    try:
        verify_sig(
            inv, os.path.join(out, "inventory.sig"), os.path.join(out, "pubkey.b64")
        )
    except Exception:
        sig_ok = False
    ok = sig_ok and not (missing or extra or mismatch)
    verify_seconds = round(time.time() - t0, 3)
    with open(os.path.join(out, "diff.json"), "w", encoding="utf-8") as f:
        json.dump(diff, f, indent=1, sort_keys=True)
    md = [
        "# sovkit drill receipt",
        "",
        f"- result: {'PASS' if ok else 'FAIL'}",
        f"- inventory signature valid: {sig_ok}",
        f"- inventory.json sha256: {sha256_file(inv)}",
        f"- before: {len(m['entries']) + len(m['skipped_unmapped'])} objects ({len(m['skipped_unmapped'])} unmapped, left for manual)",
        f"- after: {len(actual)} files in target",
        f"- missing: {len(missing)}, extra: {len(extra)}, hash mismatch: {len(mismatch)}",
        f"- verified_by_size only (UNHASHED, no content hash available): {by_size}",
        f"- copy seconds: {m['copy_seconds']}, verify seconds: {verify_seconds}",
        f"- diff.json sha256: {sha256_file(os.path.join(out, 'diff.json'))}",
        "",
    ]
    rp = os.path.join(out, "drill.receipt.md")
    with open(rp, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    sign_file(rp, os.path.join(out, "drill.receipt.sig"))
    from sovkit.attest import utc, write_attestation

    write_attestation(
        os.path.join(out, "drill.dsse.json"),
        [os.path.join(out, "drill.json"), os.path.join(out, "diff.json"), rp],
        "sovkit/drill/v1",
        {
            "result": "PASS" if ok else "FAIL",
            "missing": len(missing),
            "extra": len(extra),
            "hash_mismatch": len(mismatch),
            "copied": len(m["entries"]),
        },
        utc(m["started"]),
        utc(),
        "DRY-RUN",
    )
    return {"ok": ok, "diff": diff, "sig_ok": sig_ok, "by_size": by_size}
