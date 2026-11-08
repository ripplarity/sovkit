from sovkit.mapping import map_object

PHASES = [
    (
        "1. Identity (first)",
        ("user", "group"),
        "keycloak import",
        "kcadm.sh get users --realm opendesk | wc -l  (expect {n})",
    ),
    (
        "2. Mail",
        ("mailbox",),
        "imapsync",
        "imapsync --dry --host1 <m365> --host2 <ox> --user1 <upn>  (message counts equal)",
    ),
    (
        "3. Files",
        ("site", "onedrive", "document"),
        "rclone",
        "rclone check <source> <nextcloud-webdav> --one-way  (0 differences)",
    ),
    (
        "4. Rooms",
        ("team",),
        "nextcloud occ / Element admin API",
        "occ group:list | grep -c <team>  (expect {n})",
    ),
    (
        "5. Projects",
        ("planner",),
        "OpenProject API import",
        "GET /api/v3/projects  (count equals {n})",
    ),
]


def build_runbook(estate) -> str:
    out = ["# Migration runbook", ""]
    if not estate.objects:
        return "\n".join(out + ["Nothing to migrate.", ""])
    mapped = [(o, map_object(o)) for o in estate.objects]
    for title, kinds, tool, verify in PHASES:
        items = [(o, m) for o, m in mapped if o.kind in kinds and m["mapped"]]
        if not items:
            continue
        out += [
            f"## {title}",
            "",
            f"- tool: `{tool}`",
            f"- verify: `{verify.format(n=len(items))}`",
            "",
        ]
        for o, m in items:
            out.append(
                f"- {o.kind} `{o.name}` -> {m['target']} ({m['method']}) risk={m['risk']}"
            )
        out.append("")
    manual = [(o, m) for o, m in mapped if not m["mapped"]]
    out += ["## MANUAL (unmapped; no automated path)", ""]
    out += [
        f"- {o.kind} `{o.name}` risk={m['risk']}: {m['reason']}" for o, m in manual
    ] or ["- (none)"]
    return "\n".join(out) + "\n"
