"""Generate fixtures/demo_municipality (40 objects). Deterministic; run once and commit the output."""

import os

import yaml

root = os.path.join(os.path.dirname(__file__), "..", "fixtures", "demo_municipality")
os.makedirs(os.path.join(root, "files"), exist_ok=True)
objs = []
n = 0


def add(kind, name, owner="", items=0, content=None, ext_flags=None, fname=None):
    global n
    n += 1
    o = {
        "id": f"o{n:03d}",
        "kind": kind,
        "name": name,
        "owner": owner,
        "item_count": items,
        "last_modified": "2026-10-01T08:00:00Z",
        "flags": list(ext_flags or []),
    }
    if content is not None:
        fn = fname or f"o{n:03d}.dat"
        with open(os.path.join(root, "files", fn), "wb") as f:
            f.write(content)
        o["file"] = f"files/{fn}"
    objs.append(o)


depts = [
    "Finance",
    "Building Permits",
    "Social Services",
    "Schools",
    "Waste Management",
]
for i, d in enumerate(depts):
    add("user", f"clerk{i}@gemeente.example", f"clerk{i}@gemeente.example")
add("group", "All Staff")
add("group", "Finance Team")
for i in range(5):
    add(
        "mailbox",
        f"clerk{i}@gemeente.example",
        f"clerk{i}@gemeente.example",
        items=12,
        content=f"From: a@gemeente.example\nTo: clerk{i}@gemeente.example\nSubject: demo {i}\n\nHello {i}\n".encode(),
    )
for d in depts[:3]:
    add("site", f"{d} Site", items=4, content=f"site {d}\n".encode())
add(
    "onedrive",
    "clerk0 OneDrive",
    "clerk0@gemeente.example",
    items=3,
    content=b"onedrive clerk0\n",
)
add("team", "Council Meetings")
add("team", "Emergency Response")
for nm in [
    "budget2026.xlsx",
    "minutes.docx",
    "slides.pptx",
    "Zoning über/Plan: v2?.docx",
]:
    add(
        "document",
        nm,
        "Finance Site",
        items=1,
        content=("doc " + nm).encode(),
        ext_flags=[],
    )
for nm in ["permits.accdb", "citizens.accdb", "legacy_assets.mdb"]:
    add(
        "document",
        nm,
        "Building Permits Site",
        items=1,
        content=b"ACCESS " + nm.encode(),
    )
for nm in ["payroll.xlsm", "invoice_macro.xlsm"]:
    add("document", nm, "Finance Site", items=1, content=b"MACRO " + nm.encode())
add("planner", "Road Works 2027")
add("planner", "School Renovation")
add("form", "Citizen Survey")
add("form", "Event Signup")
add("flow", "Approve Permit Flow")
add("powerapp", "Fleet Inspection App")
add("document", "annual_report.docx", "Finance Site", items=1, content=b"report")
add(
    "document", "remote_large.pdf", "Finance Site", items=1
)  # no content file: UNHASHED
objs[-1]["size_bytes"] = 2048
add("planner", "Library Move")
add(
    "onedrive",
    "clerk1 OneDrive",
    "clerk1@gemeente.example",
    items=2,
    content=b"onedrive clerk1\n",
)
add("group", "Schools Team")
add("team", "IT Helpdesk")
add("document", "timetable.xlsx", "Schools Site", items=1, content=b"timetable")
assert len(objs) == 40, len(objs)
with open(os.path.join(root, "estate.yaml"), "w", encoding="utf-8") as f:
    yaml.safe_dump(
        {
            "tenant_id": "demo-gemeente",
            "captured_at": "2026-11-08T00:00:00Z",
            "objects": objs,
        },
        f,
        allow_unicode=True,
        sort_keys=False,
    )
print("objects", len(objs))
