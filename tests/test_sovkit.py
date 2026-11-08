import os
import shutil
import subprocess
import sys

import httpx
import pytest
from sovkit.cli import app
from sovkit.drill import run_drill, sanitize, verify_drill
from sovkit.inventory import finalize, write_inventory
from sovkit.mapping import KINDS, map_object
from sovkit.models import Estate, EstateObject
from sovkit.plan import build_runbook
from sovkit.risk import score_estate
from sovkit.signing import canonical
from sovkit.sources.fixture import load_fixture
from sovkit.sources.graph import Graph, GraphError, read_estate
from sovkit.verify_receipt import verify
from typer.testing import CliRunner

FIX = os.path.join(os.path.dirname(__file__), "..", "fixtures", "demo_municipality")
VERIFIER = os.path.join(os.path.dirname(__file__), "..", "sovkit", "verify_receipt.py")


@pytest.fixture(autouse=True)
def key(tmp_path, monkeypatch):
    monkeypatch.setenv("SOVKIT_KEY", str(tmp_path / "k" / "test.pem"))


@pytest.fixture
def demo(tmp_path):
    estate, _ = load_fixture(FIX)
    out = str(tmp_path / "out")
    write_inventory(estate, out)
    return out


def obj(kind, name="x", **kw):
    return EstateObject(id=kw.pop("id", "1"), kind=kind, name=name, **kw)


def test_fixture_has_40_objects_and_required_items():
    estate, _ = load_fixture(FIX)
    assert len(estate.objects) == 40
    names = [o.name for o in estate.objects]
    assert sum(n.lower().endswith((".accdb", ".mdb")) for n in names) == 3
    assert sum(n.endswith(".xlsm") for n in names) == 2
    assert sum(o.kind == "flow" for o in estate.objects) == 1
    assert {o.kind for o in estate.objects} == set(KINDS)


def test_canonical_json_stable():
    assert (
        canonical({"b": 1, "a": [2, 1]})
        == canonical({"a": [2, 1], "b": 1})
        == b'{"a":[2,1],"b":1}'
    )


def test_inventory_deterministic(tmp_path):
    estate, _ = load_fixture(FIX)
    write_inventory(estate, str(tmp_path / "a"))
    write_inventory(load_fixture(FIX)[0], str(tmp_path / "b"))
    assert (tmp_path / "a" / "inventory.json").read_bytes() == (
        tmp_path / "b" / "inventory.json"
    ).read_bytes()


def test_signature_verifies(demo):
    verify(f"{demo}/inventory.json", f"{demo}/inventory.sig", f"{demo}/pubkey.b64")


def test_tamper_fails(demo):
    p = f"{demo}/inventory.json"
    b = bytearray(open(p, "rb").read())
    b[10] ^= 1
    open(p, "wb").write(bytes(b))
    with pytest.raises(Exception):
        verify(p, f"{demo}/inventory.sig", f"{demo}/pubkey.b64")


def test_standalone_verifier_exit_codes(demo):
    args = [
        sys.executable,
        VERIFIER,
        f"{demo}/inventory.json",
        f"{demo}/inventory.sig",
        f"{demo}/pubkey.b64",
    ]
    assert subprocess.run(args).returncode == 0
    p = f"{demo}/inventory.json"
    b = bytearray(open(p, "rb").read())
    b[10] ^= 1
    open(p, "wb").write(bytes(b))
    assert subprocess.run(args).returncode != 0


@pytest.mark.parametrize("kind", KINDS)
def test_mapping_covers_every_kind(kind):
    m = map_object(obj(kind))
    assert m["risk"] in ("critical", "high", "medium", "low")
    assert m["mapped"] == (m["target"] is not None)


def test_accdb_critical_xlsm_high_forms_medium():
    assert map_object(obj("document", "a.accdb"))["risk"] == "critical"
    assert map_object(obj("document", "a.MDB"))["mapped"] is False
    assert map_object(obj("document", "a.xlsm"))["risk"] == "high"
    assert map_object(obj("form"))["risk"] == "medium"
    assert map_object(obj("flow"))["risk"] == "high"
    assert map_object(obj("document", "a.docx"))["risk"] == "low"


def test_risk_ordering_and_estate_score(demo):
    sc = score_estate(finalize(load_fixture(FIX)[0]))
    assert sc["max"] == 100
    assert 10 < sc["weighted_mean"] < 100
    scores = sorted((r["score"] for r in sc["rows"]), reverse=True)
    assert scores[:3] == [100, 100, 100]


def test_identity_collision_flagged_high():
    e = Estate(
        tenant_id="t",
        captured_at="x",
        objects=[
            obj("user", "A@x.eu", id="1", owner="A@x.eu"),
            obj("user", "a@X.eu", id="2", owner="a@X.eu"),
        ],
    )
    finalize(e)
    assert all("IDENTITY_COLLISION" in o.flags for o in e.objects)
    assert map_object(e.objects[0])["risk"] == "high"


def test_empty_estate(tmp_path):
    e = Estate(tenant_id="t", captured_at="x")
    out = str(tmp_path / "e")
    write_inventory(e, out)
    assert score_estate(e)["max"] == 0
    assert "Nothing to migrate" in build_runbook(e)


def test_runbook_order_and_manual(demo):
    from sovkit.inventory import load_inventory

    rb = build_runbook(load_inventory(demo))
    assert (
        rb.index("1. Identity")
        < rb.index("2. Mail")
        < rb.index("3. Files")
        < rb.index("4. Rooms")
    )
    assert "MANUAL" in rb and "permits.accdb" in rb


def test_sanitize_edge_cases():
    s = sanitize("a/b\\c:d?.docx")
    assert "/" not in s and "\\" not in s and s.endswith(".docx")
    long = sanitize("ü" * 400 + ".xlsx")
    assert len(long) <= 255 and long.endswith(".xlsx")


def test_drill_demo_diff_empty(demo, tmp_path):
    t = str(tmp_path / "t")
    run_drill(demo, t, FIX)
    r = verify_drill(demo)
    assert r["ok"] and r["diff"] == {"missing": [], "extra": [], "hash_mismatch": []}
    assert r["by_size"] == 1  # remote_large.pdf is UNHASHED
    verify(
        f"{demo}/drill.receipt.md", f"{demo}/drill.receipt.sig", f"{demo}/pubkey.b64"
    )


def test_drill_detects_tamper_missing_extra(demo, tmp_path):
    t = str(tmp_path / "t")
    m = run_drill(demo, t, FIX)
    victim = os.path.join(t, *m["entries"][0]["path"].split("/"))
    open(victim, "ab").write(b"x")
    os.remove(os.path.join(t, *m["entries"][1]["path"].split("/")))
    open(os.path.join(t, "stray.txt"), "w").write("s")
    r = verify_drill(demo)
    assert not r["ok"]
    assert (
        len(r["diff"]["hash_mismatch"]) == 1
        and len(r["diff"]["missing"]) == 1
        and r["diff"]["extra"] == ["stray.txt"]
    )


def test_graph_pagination_and_estate():
    def handler(req: httpx.Request) -> httpx.Response:
        u = str(req.url)
        if u.endswith("/users"):
            return httpx.Response(
                200,
                json={
                    "value": [{"id": "u1", "userPrincipalName": "a@x.eu"}],
                    "@odata.nextLink": "https://graph.microsoft.com/v1.0/users?page=2",
                },
            )
        if "users?page=2" in u:
            return httpx.Response(
                200, json={"value": [{"id": "u2", "userPrincipalName": "b@x.eu"}]}
            )
        if "/sites/s1/drives" in u:
            return httpx.Response(200, json={"value": [{"id": "d1"}]})
        if "/drives/d1/root/children" in u:
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": "f1",
                            "name": "a.docx",
                            "size": 5,
                            "file": {"hashes": {"sha256Hash": "AB"}},
                        }
                    ]
                },
            )
        if "/sites" in u:
            return httpx.Response(
                200, json={"value": [{"id": "s1", "displayName": "S"}]}
            )
        return httpx.Response(200, json={"value": []})

    g = Graph(token="t", transport=httpx.MockTransport(handler))
    assert [u["id"] for u in g.pages("/users")] == ["u1", "u2"]
    est = read_estate(g, "ten", "now")
    assert {o.id for o in est.objects} == {"u1", "u2", "s1", "f1"}
    assert next(o for o in est.objects if o.id == "f1").sha256 == "ab"


@pytest.mark.parametrize("code", [401, 403])
def test_graph_auth_errors_clear(code):
    g = Graph(token="t", transport=httpx.MockTransport(lambda r: httpx.Response(code)))
    with pytest.raises(GraphError, match=str(code)):
        list(g.pages("/users"))


def test_graph_missing_env_is_clear(monkeypatch):
    monkeypatch.delenv("SOVKIT_TENANT", raising=False)
    with pytest.raises(GraphError, match="SOVKIT_TENANT"):
        Graph()


def test_cli_smoke(tmp_path):
    r = CliRunner()
    out = str(tmp_path / "w")
    tgt = str(tmp_path / "w" / "target")
    assert r.invoke(app, ["inventory", "--fixture", FIX, "--out", out]).exit_code == 0
    assert r.invoke(app, ["map", out]).exit_code == 0
    assert r.invoke(app, ["plan", out]).exit_code == 0
    assert r.invoke(app, ["drill", out, "--target", tgt]).exit_code == 0
    assert r.invoke(app, ["verify", out]).exit_code == 0
    assert os.path.exists(f"{out}/drill.receipt.md")
    shutil.rmtree(tgt)
    assert r.invoke(app, ["verify", out]).exit_code == 1


ATTEST_SPEC = os.path.join(
    os.path.dirname(__file__), "..", "..", "attest-spec", "attest_verify.py"
)
LOCAL_VERIFIER = os.path.join(
    os.path.dirname(__file__), "..", "tools", "attest_verify.py"
)


def _attest(env_path, key_path, *extra):
    return subprocess.run(
        [sys.executable, LOCAL_VERIFIER, env_path, "--key", key_path, *extra],
        capture_output=True,
        text=True,
    ).returncode


def test_inventory_dsse_verifies_and_detects_tamper(demo):
    assert _attest(f"{demo}/inventory.dsse.json", f"{demo}/pubkey.hex") == 0
    assert (
        _attest(
            f"{demo}/inventory.dsse.json", f"{demo}/pubkey.hex", "--check-subjects", demo
        )
        == 0
    )
    with open(f"{demo}/inventory.json", "ab") as f:
        f.write(b" ")
    assert (
        _attest(
            f"{demo}/inventory.dsse.json", f"{demo}/pubkey.hex", "--check-subjects", demo
        )
        == 3
    )


def test_drill_dsse_verifies(demo, tmp_path):
    run_drill(demo, str(tmp_path / "t"), FIX)
    verify_drill(demo)
    assert (
        _attest(
            f"{demo}/drill.dsse.json", f"{demo}/pubkey.hex", "--check-subjects", demo
        )
        == 0
    )


def test_canonical_is_ascii_only():
    assert canonical({"a": "é"}) == b'{"a":"\u00e9"}'


def test_verifier_copy_identical_to_spec_repo():
    import hashlib

    if not os.path.exists(ATTEST_SPEC):
        pytest.skip("attest-spec repo not alongside")
    h = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()  # noqa: E731
    assert h(LOCAL_VERIFIER) == h(ATTEST_SPEC)
