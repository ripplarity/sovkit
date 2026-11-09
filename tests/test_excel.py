import io
import zipfile

import openpyxl
from sovkit.cli import app
from sovkit.excel import scan_dir, scan_file
from typer.testing import CliRunner


def _wb(path, formula=None):
    wb = openpyxl.Workbook()
    wb.active["A1"] = 1
    if formula:
        wb.active["B1"] = formula
    wb.save(path)


def _inject(path, name, data=b"x"):
    buf = io.BytesIO(open(path, "rb").read())
    with zipfile.ZipFile(buf, "a") as z:
        z.writestr(name, data)
    open(path, "wb").write(buf.getvalue())


def test_plain(tmp_path):
    p = str(tmp_path / "a.xlsx")
    _wb(p)
    assert scan_file(p)["risk"] == "LOW"


def test_dynamic(tmp_path):
    p = str(tmp_path / "a.xlsx")
    _wb(p, "=_xlfn._xlws.FILTER(A1:A3,A1:A3>0)")
    r = scan_file(p)
    assert r["risk"] == "MEDIUM" and "FILTER" in r["functions"]


def test_lambda(tmp_path):
    p = str(tmp_path / "a.xlsx")
    _wb(p, "=_xlfn.LAMBDA(x,x+1)(2)")
    r = scan_file(p)
    assert r["risk"] == "HIGH" and "LAMBDA" in r["functions"]


def test_vba(tmp_path):
    p = str(tmp_path / "a.xlsm")
    _wb(p)
    _inject(p, "xl/vbaProject.bin")
    r = scan_file(p)
    assert r["risk"] == "HIGH" and r["vba"]


def test_power_query(tmp_path):
    p = str(tmp_path / "a.xlsx")
    _wb(p)
    _inject(p, "customXml/item1.xml", "<DataMashup xmlns='x'/>".encode("utf-16le"))
    r = scan_file(p)
    assert r["power_query"] and r["risk"] == "HIGH"


def test_external_link(tmp_path):
    p = str(tmp_path / "a.xlsx")
    _wb(p)
    _inject(p, "xl/externalLinks/externalLink1.xml")
    r = scan_file(p)
    assert r["risk"] == "MEDIUM" and r["external_links"] == 1


def test_binary_and_corrupt(tmp_path):
    p = tmp_path / "old.xls"
    p.write_bytes(b"\xd0\xcf\x11\xe0 nothing")
    r = scan_file(str(p))
    assert r["risk"] == "MEDIUM" and "manual review" in r["notes"][0]
    q = tmp_path / "bad.xlsx"
    q.write_bytes(b"nope")
    assert scan_file(str(q))["risk"] == "MEDIUM"


def test_dir_cli_signed(tmp_path):
    (tmp_path / "Finance").mkdir()
    _wb(str(tmp_path / "Finance" / "a.xlsx"))
    _wb(str(tmp_path / "top.xlsx"), "=_xlfn.LET(a,1,a)")
    res = scan_dir(str(tmp_path))
    assert res["by_folder"] == {"(root)": {"HIGH": 1}, "Finance": {"LOW": 1}}
    out = tmp_path.parent / (tmp_path.name + "_w")
    r = CliRunner().invoke(
        app, ["excel-scan", str(tmp_path), "--out", str(out), "--roundtrip"]
    )
    assert r.exit_code == 0, r.output
    assert (out / "excel_scan.sig").exists()
    assert "roundtrip" in r.output


# --- adversarial regressions (one per finding) ---


def _zip(path, members, comp=zipfile.ZIP_DEFLATED):
    with zipfile.ZipFile(path, "w", comp) as z:
        for n, b in members:
            z.writestr(n, b)


def test_s1_namespace_prefixed_formula_is_seen(tmp_path):
    p = str(tmp_path / "ns.xlsx")
    sheet = (
        '<x:worksheet xmlns:x="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<x:sheetData><x:row><x:c r="A1"><x:f>_xlfn.LAMBDA(x,x+1)(2)</x:f></x:c></x:row>'
        "</x:sheetData></x:worksheet>"
    )
    _zip(p, [("[Content_Types].xml", "<Types/>"), ("xl/worksheets/sheet1.xml", sheet)])
    r = scan_file(p)
    assert r["risk"] == "HIGH" and "LAMBDA" in r["functions"]


def test_s2_unsupported_compression_is_unreadable_not_crash(tmp_path):
    p = tmp_path / "comp.xlsx"
    _zip(
        str(p),
        [
            ("[Content_Types].xml", "<Types/>"),
            ("xl/worksheets/sheet1.xml", "<f>SUM(1)</f>"),
        ],
    )
    b = bytearray(p.read_bytes())
    i = b.find(b"PK\x03\x04", 10)
    b[i + 8 : i + 10] = (99).to_bytes(2, "little")
    j = b.find(b"PK\x01\x02")
    j = b.find(b"PK\x01\x02", j + 4)
    b[j + 10 : j + 12] = (99).to_bytes(2, "little")
    p.write_bytes(bytes(b))
    r = scan_file(str(p))
    assert r["risk"] == "MEDIUM" and r.get("unreadable")


def test_s2_corrupt_deflate_does_not_abort_scan_dir(tmp_path):
    bad = tmp_path / "bad.xlsx"
    _zip(
        str(bad),
        [
            ("[Content_Types].xml", "<Types/>"),
            ("xl/worksheets/sheet1.xml", "<f>SUM(1)</f>" * 1000),
        ],
    )
    b = bytearray(bad.read_bytes())
    k = b.find(b"sheet1.xml") + 10
    for x in range(k + 5, k + 40):
        b[x] ^= 0xFF
    bad.write_bytes(bytes(b))
    _wb(str(tmp_path / "good.xlsx"))
    res = scan_dir(str(tmp_path))
    assert res["total"] == 2
    assert {f["path"]: f["risk"] for f in res["files"]} == {
        "bad.xlsx": "MEDIUM",
        "good.xlsx": "LOW",
    }


def test_s3_zip_bomb_is_capped_and_medium(tmp_path, monkeypatch):
    import sovkit.excel as E

    monkeypatch.setattr(E, "MAX_MEMBER_BYTES", 1024 * 1024)
    monkeypatch.setattr(E, "MAX_TOTAL_BYTES", 4 * 1024 * 1024)
    p = str(tmp_path / "bomb.xlsx")
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/worksheets/sheet1.xml", b"\0" * (2 * 1024 * 1024))
    r = scan_file(p)
    assert r["risk"] == "MEDIUM" and r.get("unreadable")


def test_s3_lying_declared_size_is_capped(tmp_path, monkeypatch):
    import sovkit.excel as E

    monkeypatch.setattr(E, "MAX_MEMBER_BYTES", 1024)
    p = str(tmp_path / "lie.xlsx")
    _zip(
        p,
        [
            ("[Content_Types].xml", "<Types/>"),
            ("xl/worksheets/sheet1.xml", b"<f>A</f>" + b" " * 4096),
        ],
    )
    assert scan_file(p)["risk"] == "MEDIUM"


def test_s3_member_count_cap(tmp_path, monkeypatch):
    import sovkit.excel as E

    monkeypatch.setattr(E, "MAX_MEMBERS", 5)
    p = str(tmp_path / "many.xlsx")
    _zip(p, [(f"m{i}.xml", "x") for i in range(10)])
    r = scan_file(p)
    assert r["risk"] == "MEDIUM" and r.get("unreadable")
