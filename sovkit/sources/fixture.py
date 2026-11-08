import os

import yaml

from sovkit.models import Estate, EstateObject
from sovkit.signing import sha256_file


def load_fixture(path: str) -> tuple[Estate, dict[str, str]]:
    """Returns (estate, {object_id: file path}) for objects that have a backing file."""
    d = yaml.safe_load(open(os.path.join(path, "estate.yaml"), encoding="utf-8"))
    objs, files = [], {}
    for o in d.get("objects") or []:
        o = dict(o)
        f = o.pop("file", None)
        eo = EstateObject(**o)
        if f:
            fp = os.path.join(path, f)
            files[eo.id] = fp
            eo.sha256 = sha256_file(fp)
            eo.size_bytes = os.path.getsize(fp)
        objs.append(eo)
    return Estate(
        tenant_id=d["tenant_id"], captured_at=d["captured_at"], objects=objs
    ), files
