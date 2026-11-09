<p align="center">
  <img src="assets/logo.svg" width="112" alt="sovkit logo: an arrow moving a document from one box to another">
</p>

<h1 align="center">sovkit: attested Microsoft 365 migration</h1>

<p align="center">
  <b>Move off Microsoft 365 with a signed record of what moved.</b><br>
  Inventory, risk map, runbook and a dry-run drill to openDesk or Nextcloud, each with a receipt you can verify offline.
</p>

<p align="center">
  <img src="assets/badges.svg" alt="Microsoft 365 to openDesk/Nextcloud · signed inventory + drill · Python · Apache-2.0">
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> · <a href="#what-you-get">What you get</a> · <a href="#evidence">Evidence</a> · <a href="#faq">FAQ</a>
</p>

<p align="center"><code>python -m sovkit inventory --fixture fixtures/demo_municipality --out work/demo</code></p>

---

## Why

A migration plan is a promise; a drill is a test. sovkit inventories an estate, maps the risks, writes the runbook, rehearses the move, and signs each step, so an auditor or client can check what was moved and what was only size-checked.

## Quick start

```bash
uv venv .venv && uv pip install -e .[dev]
python -m sovkit inventory --fixture fixtures/demo_municipality --out work/demo
python -m sovkit map work/demo
python -m sovkit plan work/demo
python -m sovkit drill work/demo --target work/demo/target
KID=$(python -m sovkit keyid)
python -m sovkit verify work/demo --expect-keyid $KID
```

The last command prints `PASS-SIZE-ONLY (1: remote_large.pdf)` and exits 2 on the demo. That is correct: one object has no content hash in the inventory (flag `UNHASHED`), so it could only be size-checked, and `verify` refuses to call that a full pass. Add `--allow-size-only` to accept size-only checks explicitly (exit 0 when everything else matches).

## What you get

| Step | Command | Output |
|---|---|---|
| Inventory | `sovkit inventory` | signed `inventory.json` + `inventory.dsse.json` |
| Risk map | `sovkit map` | what will and will not move cleanly |
| Runbook | `sovkit plan` | the migration steps |
| Drill | `sovkit drill` (local folder or `nextcloud://` over WebDAV) | the rehearsed move + `drill.dsse.json` |
| Verify | `sovkit verify --expect-keyid` | hashes checked against the signed inventory |

## Excel long-tail scan

`sovkit excel-scan <dir> [--out work/demo] [--roundtrip]` walks a synced OneDrive/SharePoint folder (local files only, no Microsoft API) for `.xlsx/.xlsm/.xlsb/.xls` and flags VBA, Power Query, external links, pivot caches, data connections, and LAMBDA/LET/dynamic-array functions. HIGH = VBA, Power Query, LAMBDA/LET; MEDIUM = dynamic arrays, external links, connections, pivot caches, binary formats (manual review), unreadable; LOW = none. Counts per top-level folder; the result is a signed `excel_scan.json` and a section appended to the inventory receipt. `--roundtrip` diffs values through LibreOffice if `soffice` is on PATH, else reports UNTESTED.

## Evidence

| Result | Where |
|---|---|
| A real drill against Nextcloud 34.0.5 over WebDAV, with the exact commands and measured timings | [`docs/DRILL_NEXTCLOUD.md`](docs/DRILL_NEXTCLOUD.md) |
| Throwaway Nextcloud for the drill (pinned image, health wait) | `drill/docker-compose.yml`, `drill/wait_healthy.sh` |

## Limits

- Users, groups, mailboxes (`.eml`), teams and planners go to a local tree; Open-Xchange mail import is out of scope.
- Objects without a content hash can only be size-checked, and `verify` says so.
- No Ripplarity keyid is published yet; publish your own (`sovkit keyid`).

## FAQ

**Who is it for?** System integrators and IT teams moving organisations to openDesk or Nextcloud. See [`docs/FOR_SIS.md`](docs/FOR_SIS.md).

**Where do credentials go?** In the environment (`SOVKIT_NC_USER`, `SOVKIT_NC_PASS`) or a gitignored `drill/.env` copied from `drill/.env.example`; never committed.

**How do I check a receipt?** `python tools/attest_verify.py X.dsse.json --key pubkey.hex --expect-keyid $KID`. The pin is required, and a key beside the artefact is untrusted unless it matches.

**What format are the receipts?** [attest-spec](https://github.com/ripplarity/attest-spec) v1: DSSE + in-toto, JCS canonical payloads.

---

<p align="center"><sub>Apache-2.0 · Ripplarity Inc.</sub></p>
