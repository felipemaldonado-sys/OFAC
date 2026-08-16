from __future__ import annotations

import json
import re
from pathlib import Path

from .matcher import fold
from .paths import BASES_DIR


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", fold(name)).strip("-")
    return (slug[:80] or "base")


def unique_slug(name: str, existing: set[str]) -> str:
    base = slugify(name)
    slug = base
    index = 2
    while slug in existing:
        slug = f"{base}-{index}"
        index += 1
    return slug


def write_base(meta: dict, records: list[dict]) -> Path:
    BASES_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": meta.get("id"),
        "slug": meta["slug"],
        "name": meta["name"],
        "filename": meta.get("filename") or "",
        "created_at": meta.get("created_at") or "",
        "active": int(meta.get("active", 1)),
        "row_count": len(records),
        "records": records,
    }
    path = BASES_DIR / f"{meta['slug']}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    write_index()
    return path


def read_base(slug: str) -> dict | None:
    path = BASES_DIR / f"{slug}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def read_all() -> list[dict]:
    if not BASES_DIR.exists():
        return []
    bases = []
    for path in sorted(BASES_DIR.glob("*.json")):
        if path.name == "index.json":
            continue
        bases.append(json.loads(path.read_text(encoding="utf-8")))
    return bases


def delete_base_file(slug: str) -> None:
    path = BASES_DIR / f"{slug}.json"
    path.unlink(missing_ok=True)
    write_index()


def write_index() -> Path:
    BASES_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for path in sorted(BASES_DIR.glob("*.json")):
        if path.name == "index.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        items.append(
            {
                "id": data.get("id"),
                "slug": data.get("slug") or path.stem,
                "name": data.get("name"),
                "filename": data.get("filename"),
                "created_at": data.get("created_at"),
                "active": int(data.get("active", 1)),
                "row_count": data.get("row_count") or len(data.get("records") or []),
            }
        )
    path = BASES_DIR / "index.json"
    path.write_text(json.dumps({"bases": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
