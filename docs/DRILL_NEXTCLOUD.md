# Real drill against Nextcloud

Run on 2026-11-08 (UTC) on a Windows 11 workstation, Docker 29.4.2, image `nextcloud:stable` (Nextcloud 34.0.5, SQLite).
Fixture: `fixtures/demo_municipality` (40 objects: 33 mapped, 7 unmapped left for manual).

## What goes where
- Documents (SharePoint library / OneDrive owner files) are uploaded over WebDAV to `sovkit-drill/<owner>/<id>_<name>` on the
  Nextcloud, one folder per owner (for example `sovkit-drill/Finance Site/`).
- Everything else (users, groups, mailboxes as `.eml`, teams, planners) still goes to a local tree at `<out>/target_local`.
  Open-Xchange mail import is out of scope for this pass.
- `verify` lists the Nextcloud with PROPFIND (size), downloads each remote file once and hashes it, compares against the
  hashes of the signed `inventory.json`, and writes the same `diff.json`, `drill.receipt.md` and `drill.dsse.json`.

## Commands (credentials only in the environment, never in a file)

    cd drill
    export SOVKIT_NC_USER=admin SOVKIT_NC_PASS=<choose a long random value>   # see drill/.env.example
    docker compose up -d                 # pulls nextcloud:stable, starts on http://localhost:8180
    # wait until `docker inspect -f '{{.State.Health.Status}}' sovkit-nextcloud` prints healthy
    cd ..
    python -m sovkit inventory --fixture fixtures/demo_municipality --out work/nc
    python -m sovkit drill work/nc --target nextcloud://localhost:8180
    KID=$(python -m sovkit keyid)
    python -m sovkit verify work/nc --expect-keyid $KID                      # strict
    python -m sovkit verify work/nc --expect-keyid $KID --allow-size-only
    python tools/attest_verify.py work/nc/drill.dsse.json --key work/nc/pubkey.hex --expect-keyid $KID --check-subjects work/nc
    cd drill && docker compose down -v

## Measured
| step | time |
|---|---|
| `docker compose up -d` (image pull + start) | 73 s |
| wait for healthy (install on first start) | 24 s |
| drill: 33 objects, 7 unmapped skipped (copy time reported by the tool) | 3.96 s (5.1 s wall) |
| verify, strict | 4.8 s wall |
| verify, `--allow-size-only` | 5.7 s wall |
| `docker compose down -v` | 4 s |

## Output
    drill: 33 objects copied in 3.956s, 7 unmapped skipped
    PASS-SIZE-ONLY (1: remote_large.pdf)            # strict verify, exit 2
    verify: PASS missing=0 extra=0 mismatch=0 disagree=0   # with --allow-size-only, exit 0
    VALID-SIGNATURE
    VALID https://ripplarity.com/attestation/sovkit/drill/v1   # attest_verify on drill.dsse.json

The strict result is expected: `remote_large.pdf` has no content hash in the inventory, so it can only be checked by size.
PROPFIND of the target afterwards showed folders `sovkit-drill/Finance Site/` and `sovkit-drill/Schools Site/` (and the
other owners).

## Notes
- First live attempt failed in `verify` with `ValueError: invalid literal for int()`: Nextcloud returns an empty
  `getcontentlength` element for folders. Fixed in `sovkit/webdav.py` and covered by the mock server in
  `tests/test_webdav.py`; the table above is from the run after the fix.
- Tamper detection against the live server was not exercised (it is covered by the mock-server tests).
- The live run is a manual acceptance, not a unit test.
