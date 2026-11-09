import os
import xml.sax.saxutils as sx
from urllib.parse import unquote

import httpx
import pytest
from sovkit.cli import app
from sovkit.drill import remote_path, run_drill, verify_drill
from sovkit.inventory import write_inventory
from sovkit.models import EstateObject
from sovkit.signing import keyid
from sovkit.sources.fixture import load_fixture
from sovkit.webdav import DavError, WebDAV, seg_quote
from typer.testing import CliRunner

FIX = os.path.join(os.path.dirname(__file__), "..", "fixtures", "demo_municipality")
ROOT = "/remote.php/dav/files/admin"


class FakeNextcloud:
    """In-memory WebDAV server behind httpx.MockTransport."""

    def __init__(self):
        self.files, self.dirs, self.log = {}, {""}, []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        path = unquote(req.url.path)
        assert path.startswith(ROOT), path
        rel = path[len(ROOT):].strip("/")
        self.log.append((req.method, rel))
        if req.method == "MKCOL":
            if rel in self.dirs:
                return httpx.Response(405)
            parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
            if parent not in self.dirs:
                return httpx.Response(409)
            self.dirs.add(rel)
            return httpx.Response(201)
        if req.method == "PUT":
            self.files[rel] = req.content
            return httpx.Response(201)
        if req.method == "GET":
            return httpx.Response(200, content=self.files[rel]) if rel in self.files else httpx.Response(404)
        if req.method == "PROPFIND":
            if rel not in self.dirs:
                return httpx.Response(404)
            body = [self._resp(rel, None)]
            pre = rel + "/" if rel else ""
            for d in sorted(self.dirs):
                if d and d.startswith(pre) and "/" not in d[len(pre):]:
                    body.append(self._resp(d, None))
            for f, data in sorted(self.files.items()):
                if f.startswith(pre) and "/" not in f[len(pre):]:
                    body.append(self._resp(f, len(data)))
            xml = '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">' + "".join(body) + "</d:multistatus>"
            return httpx.Response(207, content=xml.encode())
        return httpx.Response(405)

    def _resp(self, rel, size):
        from urllib.parse import quote

        href = quote(ROOT + ("/" + rel if rel else "") + ("/" if size is None else ""))
        prop = "<d:getcontentlength></d:getcontentlength><d:resourcetype><d:collection/></d:resourcetype>" if size is None else f"<d:getcontentlength>{size}</d:getcontentlength><d:resourcetype/>"
        return f"<d:response><d:href>{sx.escape(href)}</d:href><d:propstat><d:prop>{prop}</d:prop></d:propstat></d:response>"


@pytest.fixture(autouse=True)
def key(tmp_path, monkeypatch):
    monkeypatch.setenv("SOVKIT_KEY", str(tmp_path / "k" / "test.pem"))


def dav_for(fake):
    return WebDAV("http://nc.test", "admin", "s", transport=httpx.MockTransport(fake))


def test_seg_quote_unicode_and_reserved():
    assert seg_quote("a b/Zoning über/Plan#1?.docx") == "a%20b/Zoning%20%C3%BCber/Plan%231%3F.docx"


def test_put_builds_folders_and_encodes_unicode_path():
    fake = FakeNextcloud()
    dav = dav_for(fake)
    dav.put("sovkit-drill/Finance Site/o022_Zoning über.docx", b"abc")
    assert [m for m, _ in fake.log if m == "MKCOL"] == ["MKCOL", "MKCOL"]
    assert fake.files["sovkit-drill/Finance Site/o022_Zoning über.docx"] == b"abc"
    assert dav.url("a/ü b") == "http://nc.test" + ROOT + "/a/%C3%BC%20b"


def test_propfind_lists_recursively_with_sizes():
    fake = FakeNextcloud()
    dav = dav_for(fake)
    dav.put("r/x/a.bin", b"12")
    dav.put("r/y/z/é.bin", b"12345")
    assert dav.list_files("r") == {"r/x/a.bin": 2, "r/y/z/é.bin": 5}
    assert dav.list_files("missing") == {}
    with pytest.raises(DavError):
        dav_for(lambda r: httpx.Response(500)).list_files("r")


def test_remote_path_one_folder_per_owner():
    o = EstateObject(id="o1", kind="document", name="Zoning über/Plan: v2?.docx", owner="Finance Site")
    assert remote_path(o).startswith("sovkit-drill/Finance Site/o1_")


def _setup(tmp_path):
    estate, _ = load_fixture(FIX)
    out = str(tmp_path / "out")
    write_inventory(estate, out)
    return out


def test_nextcloud_drill_and_verify_roundtrip(tmp_path):
    out = _setup(tmp_path)
    fake = FakeNextcloud()
    m = run_drill(out, "nextcloud://nc.test", FIX, dav=dav_for(fake))
    assert m["target"] == "nextcloud://nc.test" and fake.files
    assert any(p.startswith("sovkit-drill/Finance Site/") for p in fake.files)
    r = verify_drill(out, keyid(), True, dav=dav_for(fake))
    assert r["ok"] and r["diff"] == {"missing": [], "extra": [], "hash_mismatch": []}
    gets = [p for m_, p in fake.log if m_ == "GET"]
    assert len(gets) == len(set(gets))  # each remote file downloaded once
    assert os.path.exists(f"{out}/drill.dsse.json")


def test_nextcloud_verify_detects_tamper_and_extra(tmp_path):
    out = _setup(tmp_path)
    fake = FakeNextcloud()
    run_drill(out, "nextcloud://nc.test", FIX, dav=dav_for(fake))
    victim = sorted(fake.files)[0]
    fake.files[victim] = fake.files[victim][:-1] + bytes([fake.files[victim][-1] ^ 1])
    fake.files["sovkit-drill/stray.txt"] = b"s"
    r = verify_drill(out, keyid(), True, dav=dav_for(fake))
    assert not r["ok"]
    assert len(r["diff"]["hash_mismatch"]) == 1
    assert "nextcloud:sovkit-drill/stray.txt" in r["diff"]["extra"]
    del fake.files[victim]
    assert len(verify_drill(out, keyid(), True, dav=dav_for(fake))["diff"]["missing"]) == 1


def test_cli_needs_credentials_in_env(tmp_path, monkeypatch):
    out = _setup(tmp_path)
    monkeypatch.delenv("SOVKIT_NC_USER", raising=False)
    monkeypatch.delenv("SOVKIT_NC_PASS", raising=False)
    open(os.path.join(out, "fixture.path"), "w").write(os.path.abspath(FIX))
    r = CliRunner().invoke(app, ["drill", out, "--target", "nextcloud://localhost:8180"])
    assert r.exit_code != 0
