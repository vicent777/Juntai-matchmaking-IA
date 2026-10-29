"""Duplicatas idênticas são reportadas; IDs conflitantes são erros."""

from app.supervised.schemas import QualityIssue


def unique_by_id(items, attribute, issues):
    seen = {}
    for item in items:
        key = getattr(item, attribute)
        if key in seen:
            if seen[key] != item:
                raise ValueError(f"ID conflitante em {attribute}: {key}")
            issues.append(QualityIssue(codigo="duplicata_" + attribute, referencia=key))
        else:
            seen[key] = item
    return list(seen.values())
