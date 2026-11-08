# sovkit

Attested migration kit: Microsoft 365 estate to openDesk/Nextcloud. Signed inventory, risk map, runbook, and a dry-run drill with an offline-verifiable receipt.

    uv venv .venv && uv pip install -e .[dev]
    python -m sovkit inventory --fixture fixtures/demo_municipality --out work/demo
    python -m sovkit map work/demo
    python -m sovkit plan work/demo
    python -m sovkit drill work/demo --target work/demo/target
    python -m sovkit verify work/demo --expect-keyid <your keyid>

See `docs/FOR_SIS.md`. Apache-2.0.

## Attestations (attest-spec v1)

`inventory` and `verify`/`drill` also write `inventory.dsse.json` / `drill.dsse.json` (DSSE + in-toto Statement v1, see attest-spec/SPEC.md). Verify with `python tools/attest_verify.py inventory.dsse.json --key pubkey.hex`. The older `.sig` files are deprecated and will be removed after one release. Canonical JSON is now ASCII-escaped (`ensure_ascii=True`), so inventory bytes for non-ASCII names differ from earlier runs.

## Key pinning

Every verifier needs a trusted key from OUT OF BAND; a key file beside the artefact is untrusted unless it matches your pin. Your keyid is generated per install: run `python -m sovkit keyid`, then publish it in this README (replace the placeholder below), in `https://ripplarity.com/.well-known/attestation-keys.json` (a founder action), and in the key's first transparency-log entry.

    producer keyid (sovkit): <PUBLISH YOURS HERE - per-install, from `sovkit keyid`>

Verify with `sovkit verify OUT --expect-keyid <keyid>`, `python sovkit/verify_receipt.py FILE SIG PUB --expect-keyid <keyid>`, or `python tools/attest_verify.py X.dsse.json --key pubkey.hex --expect-keyid <keyid>`. `sovkit verify` takes expected hashes only from the signed `inventory.json`, fails if `drill.json` disagrees, and exits 2 with `PASS-SIZE-ONLY (n: names)` when UNHASHED objects were checked by size only (`--allow-size-only` accepts that).
