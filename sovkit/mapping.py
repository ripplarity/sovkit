"""Hardcoded M365 -> openDesk mapping table."""

import os

# kind -> (target product, method, base risk, reason)
KIND_MAP = {
    "user": (
        "Keycloak/UCS (Univention)",
        "realm export/import",
        "low",
        "identity export to Keycloak realm",
    ),
    "group": (
        "Keycloak/UCS (Univention)",
        "realm export/import",
        "low",
        "group export to Keycloak realm",
    ),
    "mailbox": (
        "Open-Xchange",
        "IMAP/CalDAV import (imapsync)",
        "low",
        "mailbox imported over IMAP/CalDAV",
    ),
    "site": (
        "Nextcloud",
        "WebDAV upload",
        "low",
        "SharePoint site becomes a Nextcloud group folder",
    ),
    "onedrive": (
        "Nextcloud",
        "WebDAV upload (user folder)",
        "low",
        "OneDrive becomes a Nextcloud user folder",
    ),
    "team": (
        "Element",
        "room creation; files to Nextcloud",
        "low",
        "Teams team/channel becomes an Element room",
    ),
    "document": (
        "Collabora/Nextcloud",
        "pass-through",
        "low",
        "Office document opens in Collabora",
    ),
    "planner": (
        "OpenProject",
        "API import",
        "low",
        "Planner plan becomes an OpenProject project",
    ),
    "form": (None, "manual", "medium", "Microsoft Forms has no openDesk equivalent"),
    "flow": (
        None,
        "manual",
        "high",
        "Power Automate flow has no openDesk equivalent; rebuild by hand",
    ),
    "powerapp": (
        None,
        "manual",
        "high",
        "Power Apps app has no openDesk equivalent; rebuild by hand",
    ),
}
KINDS = sorted(KIND_MAP)
CONTENT_KINDS = {
    "document",
    "onedrive",
    "mailbox",
    "site",
}  # objects whose content is hashed from files

MACRO_EXT = {".docm", ".xlsm", ".pptm"}
ACCESS_EXT = {".accdb", ".mdb"}
SCORES = {"critical": 100, "high": 70, "medium": 40, "low": 10}


def ext_of(name: str) -> str:
    return os.path.splitext(name)[1].lower()


def map_object(o) -> dict:
    """Returns {target, method, risk, mapped, reason} for an EstateObject."""
    target, method, risk, reason = KIND_MAP[o.kind]
    if o.kind == "document":
        e = ext_of(o.name)
        if e in ACCESS_EXT:
            return {
                "target": None,
                "method": "manual",
                "risk": "critical",
                "mapped": False,
                "reason": "Access database (.accdb/.mdb) has no openDesk equivalent; manual rebuild required",
            }
        if e in MACRO_EXT:
            target, risk, reason = (
                "Collabora/Nextcloud",
                "high",
                "macro-enabled file: VBA macros do not run in Collabora; review required",
            )
    if "IDENTITY_COLLISION" in o.flags and risk != "critical":
        risk, reason = (
            "high",
            "duplicate UPN (case-insensitive): two users would map to one identity",
        )
    return {
        "target": target,
        "method": method,
        "risk": risk,
        "mapped": target is not None,
        "reason": reason,
    }
