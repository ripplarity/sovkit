"""Read-only Microsoft Graph client (client-credentials). Credentials ONLY from env vars."""

import os

import httpx

from sovkit.models import Estate, EstateObject

BASE = "https://graph.microsoft.com/v1.0"


class GraphError(RuntimeError):
    pass


class Graph:
    def __init__(self, token=None, transport=None, base=BASE):
        self.base = base
        self.http = httpx.Client(transport=transport, timeout=60)
        self.token = token or self._login()

    def _login(self) -> str:
        try:
            t, c, s = (
                os.environ[k]
                for k in ("SOVKIT_TENANT", "SOVKIT_CLIENT_ID", "SOVKIT_CLIENT_SECRET")
            )
        except KeyError as e:
            raise GraphError(
                f"missing env var {e.args[0]} (need SOVKIT_TENANT, SOVKIT_CLIENT_ID, SOVKIT_CLIENT_SECRET)"
            )
        r = self.http.post(
            f"https://login.microsoftonline.com/{t}/oauth2/v2.0/token",
            data={
                "client_id": c,
                "client_secret": s,
                "grant_type": "client_credentials",
                "scope": "https://graph.microsoft.com/.default",
            },
        )
        self._check(r)
        return r.json()["access_token"]

    @staticmethod
    def _check(r) -> None:
        if r.status_code in (401, 403):
            raise GraphError(
                f"Graph returned {r.status_code}: credentials invalid or the app lacks read-only "
                "application permissions (admin consent required)"
            )
        r.raise_for_status()

    def pages(self, path: str):
        url = path if path.startswith("http") else self.base + path
        while url:
            r = self.http.get(url, headers={"Authorization": f"Bearer {self.token}"})
            self._check(r)
            j = r.json()
            yield from j.get("value", [])
            url = j.get("@odata.nextLink")


def read_estate(g: Graph, tenant_id: str, captured_at: str) -> Estate:
    objs: list[EstateObject] = []
    for u in g.pages("/users"):
        upn = u.get("userPrincipalName", u["id"])
        objs.append(
            EstateObject(
                id=u["id"], kind="user", name=upn, owner=upn, flags=["UNHASHED"]
            )
        )
    for gr in g.pages("/groups"):
        objs.append(
            EstateObject(
                id=gr["id"],
                kind="group",
                name=gr.get("displayName", gr["id"]),
                flags=["UNHASHED"],
            )
        )
    for s in g.pages("/sites?search=*"):
        objs.append(
            EstateObject(
                id=s["id"],
                kind="site",
                name=s.get("displayName") or s.get("name", s["id"]),
                flags=["UNHASHED"],
            )
        )
        for dr in g.pages(f"/sites/{s['id']}/drives"):
            for it in g.pages(f"/drives/{dr['id']}/root/children"):
                if "file" in it:
                    h = it["file"].get("hashes", {}).get("sha256Hash")
                    objs.append(
                        EstateObject(
                            id=it["id"],
                            kind="document",
                            name=it["name"],
                            owner=s["id"],
                            size_bytes=it.get("size", 0),
                            item_count=1,
                            last_modified=it.get("lastModifiedDateTime", ""),
                            flags=[] if h else ["UNHASHED"],
                            sha256=h.lower() if h else None,
                        )
                    )
    for t in g.pages("/teams"):
        objs.append(
            EstateObject(
                id=t["id"],
                kind="team",
                name=t.get("displayName", t["id"]),
                flags=["UNHASHED"],
            )
        )
    return Estate(tenant_id=tenant_id, captured_at=captured_at, objects=objs)
