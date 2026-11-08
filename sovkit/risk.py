from sovkit.mapping import SCORES, map_object


def score_estate(estate) -> dict:
    rows = []
    for o in estate.objects:
        m = map_object(o)
        rows.append(
            {
                "id": o.id,
                "kind": o.kind,
                "name": o.name,
                **m,
                "score": SCORES[m["risk"]],
                "weight": o.item_count + 1,
            }
        )
    if not rows:
        return {"max": 0, "weighted_mean": 0.0, "rows": []}
    wsum = sum(r["weight"] for r in rows)
    return {
        "max": max(r["score"] for r in rows),
        "weighted_mean": round(sum(r["score"] * r["weight"] for r in rows) / wsum, 2),
        "rows": rows,
    }


def risk_markdown(sc: dict, top: int = 20) -> str:
    out = [
        "# Migration risk",
        "",
        f"Estate score: max={sc['max']}, weighted mean={sc['weighted_mean']}",
        "",
    ]
    if not sc["rows"]:
        return "\n".join(out + ["Empty estate: nothing to migrate, risk 0.", ""])
    out += [f"## Top {top} risks", ""]
    for r in sorted(sc["rows"], key=lambda r: (-r["score"], r["kind"], r["name"]))[
        :top
    ]:
        out.append(
            f"- [{r['risk']}] ({r['score']}) {r['kind']} `{r['name']}`: {r['reason']}"
        )
    return "\n".join(out) + "\n"
