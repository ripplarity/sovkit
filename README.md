# sovkit

Attested migration kit: Microsoft 365 estate to openDesk/Nextcloud. Signed inventory, risk map, runbook, and a dry-run drill with an offline-verifiable receipt.

    uv venv .venv && uv pip install -e .[dev]
    python -m sovkit inventory --fixture fixtures/demo_municipality --out work/demo
    python -m sovkit map work/demo
    python -m sovkit plan work/demo
    python -m sovkit drill work/demo --target work/demo/target
    python -m sovkit verify work/demo

See `docs/FOR_SIS.md`. Apache-2.0.
