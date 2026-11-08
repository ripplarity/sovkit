# sovkit for systems integrators (Dataport, Bechtle, Open Productivity, B1)

## What the kit proves
- A signed, canonical inventory of a Microsoft 365 estate (Graph, read-only, or a fixture folder).
- Each object mapped to an openDesk target with a risk score; unmapped items (Access databases, Power Automate flows, Power Apps, Forms) are listed as MANUAL, never silently dropped.
- A dry-run migration into a local target tree, re-inventoried, with `diff.json` (missing, extra, hash mismatch) and a signed `drill.receipt.md` with timings.
- Receipts verify offline by a third party: `python verify_receipt.py <file> <file.sig> pubkey.b64` (stdlib + `cryptography`; exit 0 valid, 1 invalid).

## What it does not do
- It does not perform the production migration. The runbook names the tools (`imapsync`, `rclone`, `nextcloud occ`, `keycloak import`); you run them.
- It does not convert macros, Access databases, flows or apps.
- Objects whose content hash is not available are flagged `UNHASHED` and checked by size only; the receipt states how many.
- The drill runs against a local folder tree, not a live openDesk instance.

## Running it
1. Fixture mode: `sovkit inventory --fixture <dir> --out work/x`, then `map`, `plan`, `drill work/x --target work/x/target`, `verify work/x`.
2. Live tenant: create an Entra app with read-only application permissions (admin consent), set `SOVKIT_TENANT`, `SOVKIT_CLIENT_ID`, `SOVKIT_CLIENT_SECRET` in the environment (never in files), run `sovkit inventory --graph --out work/x`. 401/403 produce a plain message.
3. Signing keys are generated at `~/.sovkit/sovkit_ed25519.pem` on first run and never committed. Hand the customer `pubkey.b64`.

## Licence
Apache-2.0, open source so the code can be audited inside a sovereignty project.
