"""Minimal WebDAV client for a Nextcloud files endpoint (httpx; basic auth from the environment)."""

import os
import xml.etree.ElementTree as ET
from urllib.parse import quote, unquote, urlsplit

import httpx

NS = {"d": "DAV:"}
PROPFIND_BODY = (
    '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop>'
    "<d:getcontentlength/><d:resourcetype/></d:prop></d:propfind>"
)


class DavError(Exception):
    pass


def seg_quote(path: str) -> str:
    """Percent-encode each path segment (UTF-8); '/' separators are kept."""
    return "/".join(quote(s, safe="") for s in path.strip("/").split("/") if s != "")


class WebDAV:
    def __init__(self, base_url: str, user: str, secret: str, transport=None):
        self.base = base_url.rstrip("/")
        self.root = f"{self.base}/remote.php/dav/files/{quote(user, safe='')}"
        self.root_path = urlsplit(self.root).path
        self.client = httpx.Client(
            auth=(user, secret),
            transport=transport,
            timeout=60.0,
            follow_redirects=False,
        )

    @classmethod
    def from_env(cls, target: str, transport=None):
        """target = nextcloud://host:port ; SOVKIT_NC_USER / SOVKIT_NC_PASS come from the environment."""
        try:
            user, secret = os.environ["SOVKIT_NC_USER"], os.environ["SOVKIT_NC_PASS"]
        except KeyError as e:
            raise DavError(f"set {e.args[0]} in the environment") from None
        return cls("http://" + target[len("nextcloud://") :], user, secret, transport)

    def url(self, path: str) -> str:
        q = seg_quote(path)
        return self.root + ("/" + q if q else "")

    def _req(self, method, path, ok, **kw):
        r = self.client.request(method, self.url(path), **kw)
        if r.status_code not in ok:
            raise DavError(f"{method} {path}: HTTP {r.status_code} {r.text[:200]}")
        return r

    def mkcol_p(self, path: str):
        """Create every folder on the path; an existing folder (405) is fine."""
        cur = ""
        for seg in [s for s in path.strip("/").split("/") if s]:
            cur = f"{cur}/{seg}" if cur else seg
            self._req("MKCOL", cur, (201, 405))

    def put(self, path: str, data: bytes):
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        if parent:
            self.mkcol_p(parent)
        self._req("PUT", path, (201, 204), content=data)

    def get(self, path: str) -> bytes:
        return self._req("GET", path, (200,)).content

    def delete(self, path: str):
        self._req("DELETE", path, (204, 404))

    def _list(self, path: str):
        """One PROPFIND (Depth 1): list of (relative path, size, is_dir) for the children."""
        r = self._req(
            "PROPFIND", path, (207,), headers={"Depth": "1"}, content=PROPFIND_BODY
        )
        out = []
        base = unquote(urlsplit(self.url(path)).path).rstrip("/")
        for resp in ET.fromstring(r.content).findall("d:response", NS):
            href = unquote(urlsplit(resp.findtext("d:href", "", NS)).path)
            if href.rstrip("/") == base:
                continue
            is_dir = resp.find(".//d:resourcetype/d:collection", NS) is not None
            size = resp.findtext(".//d:getcontentlength", None, NS)
            rel = href[len(self.root_path) :].strip("/")
            out.append((rel, int(size) if size else 0, is_dir))
        return out

    def list_files(self, path: str) -> dict:
        """Recursive {relative path: size} for files under path (Depth 1 per folder)."""
        files, todo = {}, [path.strip("/")]
        while todo:
            cur = todo.pop()
            try:
                items = self._list(cur)
            except DavError as e:
                if "HTTP 404" in str(e) and cur == path.strip("/"):
                    return {}
                raise
            for rel, size, is_dir in items:
                if is_dir:
                    todo.append(rel)
                else:
                    files[rel] = size
        return files
