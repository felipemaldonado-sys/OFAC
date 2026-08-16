from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "ofac.db"


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS bases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                filename TEXT NOT NULL,
                created_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                row_count INTEGER NOT NULL DEFAULT 0,
                slug TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                base_id INTEGER NOT NULL REFERENCES bases(id) ON DELETE CASCADE,
                id_interno TEXT NOT NULL,
                nombre TEXT NOT NULL,
                identificacion TEXT NOT NULL DEFAULT '',
                lista TEXT NOT NULL DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_records_base ON records(base_id);
            """
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(bases)").fetchall()}
        if "slug" not in columns:
            conn.execute("ALTER TABLE bases ADD COLUMN slug TEXT NOT NULL DEFAULT ''")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def list_bases() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, name, filename, created_at, active, row_count, slug FROM bases ORDER BY id"
        ).fetchall()
    return [dict(row) for row in rows]


def stats() -> dict:
    with connect() as conn:
        total = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM records r
            JOIN bases b ON b.id = r.base_id
            WHERE b.active = 1
            """
        ).fetchone()["total"]
        bases = conn.execute(
            "SELECT id, name, filename, created_at, active, row_count, slug FROM bases ORDER BY id"
        ).fetchall()
    payload = [dict(row) for row in bases]
    return {
        "total": total,
        "baseCount": sum(1 for base in payload if base["active"]),
        "bases": payload,
    }


def create_base(name: str, filename: str, records: list[dict], slug: str = "", created_at: str = "", active: int = 1) -> dict:
    from .store import unique_slug

    stamp = created_at or now_iso()
    with connect() as conn:
        existing = {row["slug"] for row in conn.execute("SELECT slug FROM bases").fetchall() if row["slug"]}
        resolved_slug = slug or unique_slug(name, existing)
        cursor = conn.execute(
            "INSERT INTO bases (name, filename, created_at, active, row_count, slug) VALUES (?, ?, ?, ?, ?, ?)",
            (name, filename, stamp, 1 if active else 0, len(records), resolved_slug),
        )
        base_id = cursor.lastrowid
        conn.executemany(
            """
            INSERT INTO records (base_id, id_interno, nombre, identificacion, lista)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    base_id,
                    row["idInterno"],
                    row["nombre"],
                    row["identificacion"],
                    row["lista"],
                )
                for row in records
            ],
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, name, filename, created_at, active, row_count, slug FROM bases WHERE id = ?",
            (base_id,),
        ).fetchone()
    return dict(row)


def set_base_active(base_id: int, active: bool) -> dict | None:
    with connect() as conn:
        existing = conn.execute("SELECT id FROM bases WHERE id = ?", (base_id,)).fetchone()
        if not existing:
            return None
        conn.execute("UPDATE bases SET active = ? WHERE id = ?", (1 if active else 0, base_id))
        conn.commit()
        row = conn.execute(
            "SELECT id, name, filename, created_at, active, row_count, slug FROM bases WHERE id = ?",
            (base_id,),
        ).fetchone()
    return dict(row) if row else None


def get_base(base_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, name, filename, created_at, active, row_count, slug FROM bases WHERE id = ?",
            (base_id,),
        ).fetchone()
    return dict(row) if row else None


def records_for_base(base_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id_interno, nombre, identificacion, lista FROM records WHERE base_id = ? ORDER BY id",
            (base_id,),
        ).fetchall()
    return [
        {
            "idInterno": row["id_interno"],
            "nombre": row["nombre"],
            "identificacion": row["identificacion"],
            "lista": row["lista"],
        }
        for row in rows
    ]


def import_missing_files(files: list[dict]) -> int:
    imported = 0
    with connect() as conn:
        slugs = {row["slug"] for row in conn.execute("SELECT slug FROM bases").fetchall() if row["slug"]}
    for data in files:
        slug = data.get("slug")
        if not slug or slug in slugs:
            continue
        create_base(
            data.get("name") or slug,
            data.get("filename") or f"{slug}.json",
            data.get("records") or [],
            slug=slug,
            created_at=data.get("created_at") or "",
            active=int(data.get("active", 1)),
        )
        imported += 1
    return imported


def delete_base(base_id: int) -> bool:
    with connect() as conn:
        cursor = conn.execute("DELETE FROM bases WHERE id = ?", (base_id,))
        conn.commit()
        return cursor.rowcount > 0


def active_records() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT r.id_interno, r.nombre, r.identificacion, r.lista, b.name AS base
            FROM records r
            JOIN bases b ON b.id = r.base_id
            WHERE b.active = 1
            ORDER BY b.id, r.id
            """
        ).fetchall()
    return [
        {
            "idInterno": row["id_interno"],
            "nombre": row["nombre"],
            "identificacion": row["identificacion"],
            "lista": row["lista"],
            "base": row["base"],
        }
        for row in rows
    ]
