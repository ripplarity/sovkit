# sovkit

Attested migration kit: Microsoft 365 estate to openDesk/Nextcloud. Signed inventory, risk map, runbook, and a dry-run drill with an offline-verifiable receipt.

    uv venv .venv && uv pip install -e .[dev]
    python -m sovkit inventory --fixture fixtures/demo_municipality --out work/demo
    python -m sovkit map work/demo
    python -m sovkit plan work/demo
    python -m sovkit drill work/demo --target work/demo/target
    KID=$(python -m sovkit keyid)
    python -m sovkit verify work/demo --expect-keyid $KID

The last command prints `PASS-SIZE-ONLY (1: remote_large.pdf)` and exits 2 on the demo fixture. That is correct: one
object (`remote_large.pdf`) has no content hash in the inventory (flag `UNHASHED`), so the drill could only check its
size, and `verify` refuses to call that a full pass. To accept size-only checks explicitly, add `--allow-size-only`
(exit 0 when everything else matches).

See `docs/FOR_SIS.md`. Code licence: Apache-2.0.

## Attestations (attest-spec v1)

`inventory` and `drill`/`verify` also write `inventory.dsse.json` / `drill.dsse.json` (DSSE + in-toto Statement v1, see attest-spec/SPEC.md). Payloads are RFC 8785 (JCS) canonical JSON. Verify with `python tools/attest_verify.py inventory.dsse.json --key pubkey.hex --expect-keyid $KID`; the pin is required. The older `.sig` files are deprecated and will be removed after one release. The inventory file's canonical JSON is ASCII-escaped, so inventory bytes for non-ASCII names differ from earlier runs.

## Key pinning

Every verifier needs a trusted key from OUT OF BAND; a key file beside the artefact is untrusted unless it matches your pin. Your keyid is generated per install. No Ripplarity keyid is published yet.

Maintainer keyid: run `sovkit keyid`; publish it in your README and at `https://<your-domain>/.well-known/attestation-keys.json`.

Verify with `sovkit verify OUT --expect-keyid <keyid>`, `python sovkit/verify_receipt.py FILE SIG PUB --expect-keyid <keyid>`, or `python tools/attest_verify.py X.dsse.json --key pubkey.hex --expect-keyid <keyid>`. `sovkit verify` takes expected hashes only from the signed `inventory.json`, fails if `drill.json` disagrees, and exits 2 with `PASS-SIZE-ONLY (n: names)` when UNHASHED objects were checked by size only. A wrong pin fails with "key does not match pin".

## Real Nextcloud drill

`python -m sovkit drill OUT --target nextcloud://localhost:8180` uploads documents to a Nextcloud over WebDAV (credentials from env `SOVKIT_NC_USER` / `SOVKIT_NC_PASS`); `verify` re-inventories it with PROPFIND. Local throwaway server: `drill/docker-compose.yml`. Measured run and exact commands: `docs/DRILL_NEXTCLOUD.md`.
