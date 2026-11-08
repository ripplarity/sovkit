# sovkit

Attested migration kit: Microsoft 365 estate to openDesk/Nextcloud. Signed inventory, risk map, runbook, and a dry-run drill with an offline-verifiable receipt.

    uv venv .venv && uv pip install -e .[dev]
    python -m sovkit inventory --fixture fixtures/demo_municipality --out work/demo
    python -m sovkit map work/demo
    python -m sovkit plan work/demo
    python -m sovkit drill work/demo --target work/demo/target
    python -m sovkit verify work/demo

See `docs/FOR_SIS.md`. Apache-2.0.

## Attestations (attest-spec v1)

`inventory` and `verify`/`drill` also write `inventory.dsse.json` / `drill.dsse.json` (DSSE + in-toto Statement v1, see attest-spec/SPEC.md). Verify with `python tools/attest_verify.py inventory.dsse.json --key pubkey.hex`. The older `.sig` files are deprecated and will be removed after one release. Canonical JSON is now ASCII-escaped (`ensure_ascii=True`), so inventory bytes for non-ASCII names differ from earlier runs.
