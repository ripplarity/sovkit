"""Excel long-tail scanner: local files only, no Microsoft API calls.

Risk rules (first match wins):
  HIGH   VBA project, Power Query (DataMashup), LAMBDA or LET in formulas,
         or a binary .xls/.xlsb that contains a VBA project.
  MEDIUM dynamic-array functions (FILTER, XLOOKUP, SORT, UNIQUE, SEQUENCE, ...),
         external links, data connections, pivot caches, any other _xlfn.
         function, a binary .xls/.xlsb with no macro found (manual review),
         or an unreadable file.
  LOW    none of the above.
"""

import html
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections import Counter

from sovkit.signing import canonical, sign_file

EXTS = (".xlsx", ".xlsm", ".xlsb", ".xls")
HIGH_FUNCS = {"LAMBDA", "LET"}
DYN_FUNCS = {
    "FILTER",
    "XLOOKUP",
    "XMATCH",
    "SORT",
    "SORTBY",
    "UNIQUE",
    "SEQUENCE",
    "RANDARRAY",
    "TEXTSPLIT",
    "VSTACK",
    "HSTACK",
    "TOCOL",
    "TOROW",
}
_FN = re.compile(r"(?:_xlfn\.)?(?:_xlws\.)?([A-Za-z][A-Za-z0-9.]*)\(")
_XLFN = re.compile(r"_xlfn\.(?:_xlws\.)?([A-Za-z][A-Za-z0-9.]*)")
BIN_NOTE = "binary: macro check only, flagged for manual review"
# Caps checked before any member is read (zip-bomb guard). Oversize -> MEDIUM "unreadable", never LOW.
MAX_MEMBERS = 10_000
MAX_MEMBER_BYTES = 64 * 1024**2
MAX_TOTAL_BYTES = 512 * 1024**2


class Oversize(Exception):
    pass


def _check_caps(z: zipfile.ZipFile):
    infos = z.infolist()
    if len(infos) > MAX_MEMBERS:
        raise Oversize(f"{len(infos)} members > {MAX_MEMBERS}")
    total = sum(i.file_size for i in infos)
    if total > MAX_TOTAL_BYTES:
        raise Oversize(f"declared uncompressed size {total} > {MAX_TOTAL_BYTES}")


def _read(z: zipfile.ZipFile, name: str) -> bytes:
    """Read one member, never more than MAX_MEMBER_BYTES (the declared size can lie)."""
    if z.getinfo(name).file_size > MAX_MEMBER_BYTES:
        raise Oversize(f"{name} declared size > {MAX_MEMBER_BYTES}")
    with z.open(name) as f:
        data = f.read(MAX_MEMBER_BYTES + 1)
    if len(data) > MAX_MEMBER_BYTES:
        raise Oversize(f"{name} inflates past {MAX_MEMBER_BYTES}")
    return data


def _formulas(z: zipfile.ZipFile):
    for n in z.namelist():
        if n.startswith("xl/worksheets/") and n.endswith(".xml"):
            data = _read(z, n)
            # optional namespace prefix (<x:f>) is valid OOXML
            for m in re.finditer(rb"<(?:[A-Za-z_][\w.-]*:)?f(?:\s[^>]*)?>([^<]*)</(?:[A-Za-z_][\w.-]*:)?f>", data):
                yield html.unescape(m.group(1).decode("utf-8", "replace"))


def scan_file(path: str) -> dict:
    ext = os.path.splitext(path)[1].lower()
    r = {
        "path": path,
        "ext": ext,
        "vba": False,
        "power_query": False,
        "external_links": 0,
        "pivot_caches": 0,
        "connections": False,
        "functions": [],
        "notes": [],
    }
    try:
        if ext == ".xls":
            data = open(path, "rb").read()
            r["vba"] = any(
                t in data for t in (b"_VBA_PROJECT", "_VBA_PROJECT".encode("utf-16le"))
            )
            r["notes"].append(BIN_NOTE)
        else:
            with zipfile.ZipFile(path) as z:
                _check_caps(z)
                names = z.namelist()
                r["vba"] = any(n.lower().endswith("vbaproject.bin") for n in names)
                if ext == ".xlsb":
                    r["notes"].append(BIN_NOTE)
                else:
                    for n in names:
                        if (
                            n.startswith("customXml/")
                            and n.endswith(".xml")
                            and "_rels" not in n
                        ):
                            d = _read(z, n)
                            if (
                                b"DataMashup" in d
                                or "DataMashup".encode("utf-16le") in d
                            ):
                                r["power_query"] = True
                    r["external_links"] = sum(
                        1 for n in names if re.match(r"xl/externalLinks/[^/]+\.xml$", n)
                    )
                    r["pivot_caches"] = sum(
                        1
                        for n in names
                        if n.startswith("xl/pivotCache/pivotCacheDefinition")
                    )
                    r["connections"] = "xl/connections.xml" in names
                    found = set()
                    for f in _formulas(z):
                        for m in _FN.finditer(f):
                            u = m.group(1).upper()
                            if u in HIGH_FUNCS | DYN_FUNCS:
                                found.add(u)
                        for m in _XLFN.finditer(f):
                            u = m.group(1).upper()
                            found.add(
                                u if u in HIGH_FUNCS | DYN_FUNCS else "_XLFN:" + u
                            )
                    r["functions"] = sorted(found)
    except Exception as e:  # any parse failure (bad zip, unsupported or corrupt compression, oversize) -> unreadable
        r["notes"].append(f"unreadable: {type(e).__name__}: {e}")
        r["unreadable"] = True
    r["risk"], r["reasons"] = classify(r)
    return r


def classify(r: dict):
    fs = set(r["functions"])
    high, med = [], []
    if r["vba"]:
        high.append("VBA project")
    if r["power_query"]:
        high.append("Power Query")
    if fs & HIGH_FUNCS:
        high.append("LAMBDA/LET: " + ",".join(sorted(fs & HIGH_FUNCS)))
    if fs & DYN_FUNCS:
        med.append("dynamic-array functions: " + ",".join(sorted(fs & DYN_FUNCS)))
    if any(f.startswith("_XLFN:") for f in fs):
        med.append("other _xlfn functions")
    if r["external_links"]:
        med.append(f"{r['external_links']} external link(s)")
    if r["connections"]:
        med.append("data connections")
    if r["pivot_caches"]:
        med.append(f"{r['pivot_caches']} pivot cache(s)")
    if r["ext"] in (".xls", ".xlsb") and not r["vba"]:
        med.append("binary format, manual review")
    if r.get("unreadable"):
        med.append("unreadable")
    if high:
        return "HIGH", high + med
    if med:
        return "MEDIUM", med
    return "LOW", []


def _values(path):
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True)
    return {
        (ws.title, c.coordinate): c.value
        for ws in wb
        for row in ws.iter_rows()
        for c in row
        if c.value is not None
    }


def roundtrip(path: str) -> str:
    """xlsx -> ods -> xlsx via soffice, then diff cached values. Never raises."""
    exe = shutil.which("soffice")
    if not exe:
        return "roundtrip: soffice not found (UNTESTED)"
    if os.path.splitext(path)[1].lower() not in (".xlsx", ".xlsm"):
        return "roundtrip: skipped (binary format)"
    try:
        stem = os.path.splitext(os.path.basename(path))[0]
        with tempfile.TemporaryDirectory() as t:
            a, b = os.path.join(t, "a"), os.path.join(t, "b")
            subprocess.run(
                [exe, "--headless", "--convert-to", "ods", "--outdir", a, path],
                check=True,
                capture_output=True,
                timeout=180,
            )
            subprocess.run(
                [
                    exe,
                    "--headless",
                    "--convert-to",
                    "xlsx",
                    "--outdir",
                    b,
                    os.path.join(a, stem + ".ods"),
                ],
                check=True,
                capture_output=True,
                timeout=180,
            )
            o, n = _values(path), _values(os.path.join(b, stem + ".xlsx"))
            diff = [k for k in o if o[k] != n.get(k)]
            return (
                "roundtrip: OK"
                if not diff
                else f"roundtrip: {len(diff)} cell value diff(s), e.g. {diff[0]}"
            )
    except Exception as e:  # never fail because of roundtrip
        return f"roundtrip: error ({type(e).__name__}) (UNTESTED)"


def scan_dir(root: str, do_roundtrip: bool = False) -> dict:
    root = os.path.abspath(root)
    files = []
    for dp, _, fns in os.walk(root):
        for fn in sorted(fns):
            if fn.lower().endswith(EXTS) and not fn.startswith("~$"):
                p = os.path.join(dp, fn)
                r = scan_file(p)
                rel = os.path.relpath(p, root).replace("\\", "/")
                r["path"] = rel
                r["folder"] = rel.split("/")[0] if "/" in rel else "(root)"
                if do_roundtrip:
                    r["roundtrip"] = roundtrip(p)
                files.append(r)
    files.sort(key=lambda r: r["path"])
    by_folder: dict[str, Counter] = {}
    for r in files:
        by_folder.setdefault(r["folder"], Counter())[r["risk"]] += 1
    return {
        "schema": "sovkit/excel-scan/v1",
        "root_name": os.path.basename(root),
        "total": len(files),
        "risk_counts": dict(Counter(r["risk"] for r in files)),
        "by_folder": {k: dict(v) for k, v in sorted(by_folder.items())},
        "files": files,
    }


def section_md(res: dict) -> str:
    lines = [
        "",
        "## Excel long-tail scan",
        "",
        f"- workbooks: {res['total']}",
        f"- risk: {res['risk_counts'] or '(none)'}",
        "",
        "By top-level folder:",
        "",
    ]
    for k, v in res["by_folder"].items():
        lines.append(f"- {k}: " + ", ".join(f"{a}={b}" for a, b in sorted(v.items())))
    lines += ["", "Signed detail: `excel_scan.json` + `excel_scan.sig`.", ""]
    return "\n".join(lines)


def write_scan(res: dict, out: str) -> str:
    os.makedirs(out, exist_ok=True)
    p = os.path.join(out, "excel_scan.json")
    with open(p, "wb") as f:
        f.write(canonical(res))
    sign_file(p, os.path.join(out, "excel_scan.sig"))
    rec = os.path.join(out, "inventory.receipt.md")
    if os.path.exists(rec):
        txt = open(rec, encoding="utf-8").read()
        txt = txt.split("\n## Excel long-tail scan")[0].rstrip("\n") + "\n"
        with open(rec, "w", encoding="utf-8") as f:
            f.write(txt + section_md(res))
    return p
