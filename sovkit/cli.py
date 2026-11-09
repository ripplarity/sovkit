import json
import os
import time

import typer

from sovkit.drill import run_drill, verify_drill
from sovkit.inventory import load_inventory, write_inventory
from sovkit.plan import build_runbook
from sovkit.risk import risk_markdown, score_estate
from sovkit.sources.fixture import load_fixture

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command("excel-scan")
def excel_scan(
    directory: str,
    out: str = typer.Option(
        "work/out", help="work dir; adds a signed section to its inventory receipt"
    ),
    roundtrip: bool = typer.Option(
        False, "--roundtrip", help="soffice ods round-trip value diff"
    ),
):
    """Scan local workbooks for macros, Power Query, LAMBDA, links (no network)."""
    from sovkit.excel import scan_dir, write_scan

    res = scan_dir(directory, roundtrip)
    write_scan(res, out)
    typer.echo(f"excel-scan: {res['total']} workbooks {res['risk_counts']} -> {out}")
    for r in res["files"]:
        typer.echo(f"{r['risk']:6} {r['path']}  {'; '.join(r['reasons'])}")
        if roundtrip:
            typer.echo(f"       {r['roundtrip']}")


@app.command()
def inventory(
    fixture: str = typer.Option(None, help="fixture folder"),
    graph: bool = typer.Option(
        False, help="read a live tenant via Graph (env SOVKIT_*)"
    ),
    out: str = typer.Option("work/out"),
):
    """Write a signed inventory."""
    if graph:
        from sovkit.sources.graph import Graph, GraphError, read_estate

        try:
            tenant = os.environ["SOVKIT_TENANT"]
            estate = read_estate(
                Graph(), tenant, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            )
        except (GraphError, KeyError) as e:
            typer.echo(f"error: {e}", err=True)
            raise typer.Exit(2)
    elif fixture:
        estate, _ = load_fixture(fixture)
    else:
        typer.echo("error: give --fixture or --graph", err=True)
        raise typer.Exit(2)
    os.makedirs(out, exist_ok=True)
    if fixture:
        with open(os.path.join(out, "fixture.path"), "w") as f:
            f.write(os.path.abspath(fixture))
    write_inventory(estate, out)
    typer.echo(f"inventory: {len(estate.objects)} objects -> {out}")


@app.command("map")
def map_cmd(out: str):
    """Map objects to openDesk targets and score risk."""
    estate = load_inventory(out)
    sc = score_estate(estate)
    json.dump(
        {
            "estate_score": {"max": sc["max"], "weighted_mean": sc["weighted_mean"]},
            "objects": sc["rows"],
        },
        open(os.path.join(out, "mapping.json"), "w", encoding="utf-8"),
        indent=1,
    )
    open(os.path.join(out, "risk.md"), "w", encoding="utf-8").write(risk_markdown(sc))
    typer.echo(f"mapped {len(estate.objects)} objects, max risk {sc['max']}")


@app.command()
def plan(out: str):
    """Emit runbook.md."""
    open(os.path.join(out, "runbook.md"), "w", encoding="utf-8").write(
        build_runbook(load_inventory(out))
    )
    typer.echo("runbook.md written")


@app.command()
def drill(
    out: str,
    target: str = typer.Option(
        ...,
        help="local folder, or nextcloud://host:port (env SOVKIT_NC_USER / SOVKIT_NC_PASS)",
    ),
    fixture: str = typer.Option(None),
):
    """Dry-run migration into a local target tree or a Nextcloud over WebDAV."""
    fx = fixture
    if not fx:
        pp = os.path.join(out, "fixture.path")
        if not os.path.exists(pp):
            typer.echo("error: drill needs a fixture estate (--fixture)", err=True)
            raise typer.Exit(2)
        fx = open(pp).read().strip()
    from sovkit.webdav import DavError

    try:
        m = run_drill(out, target, fx)
    except DavError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(2)
    typer.echo(
        f"drill: {len(m['entries'])} objects copied in {m['copy_seconds']}s, {len(m['skipped_unmapped'])} unmapped skipped"
    )


@app.command()
def verify(
    out: str,
    expect_keyid: str = typer.Option(
        ...,
        help="trusted producer keyid (sha256 hex of the public key); see `sovkit keyid`",
    ),
    allow_size_only: bool = typer.Option(
        False, help="accept UNHASHED objects verified by size only"
    ),
):
    """Re-inventory the drill target; write diff.json and signed drill.receipt.md.
    Exit 0 only if diff empty and every object is hash-verified; 2 = PASS-SIZE-ONLY."""
    from sovkit.webdav import DavError

    try:
        r = verify_drill(out, expect_keyid, allow_size_only)
    except DavError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(2)
    d = r["diff"]
    if r["sig_error"]:
        typer.echo(f"verify: FAIL {r['sig_error']}", err=True)
        raise typer.Exit(1)
    if r["ok"] and r["size_only"]:
        typer.echo(
            f"PASS-SIZE-ONLY ({len(r['unhashed'])}: {', '.join(r['unhashed'])})",
            err=True,
        )
        raise typer.Exit(2)
    typer.echo(
        f"verify: {'PASS' if r['ok'] else 'FAIL'} missing={len(d['missing'])} extra={len(d['extra'])} mismatch={len(d['hash_mismatch'])} disagree={len(d.get('drill_json_disagrees', []))}"
    )
    raise typer.Exit(0 if r["ok"] else 1)


@app.command()
def keyid():
    """Print this install's producer keyid (publish it; verifiers pin it)."""
    from sovkit.signing import keyid as _kid

    typer.echo(_kid())
