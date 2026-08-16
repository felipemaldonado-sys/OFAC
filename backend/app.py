from __future__ import annotations

from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openpyxl import Workbook
from pydantic import BaseModel

from . import db
from . import github_host
from .excel import parse_excel
from .matcher import search_records, tokenize
from .paths import ROOT, SEED_XLSX, UPLOADS_DIR, ensure_data_dirs
from .store import delete_base_file, read_all, write_base, write_index

UPLOADS = UPLOADS_DIR

_cache: dict = {"records": None}


def invalidate_cache() -> None:
    _cache["records"] = None


def cached_records() -> list[dict]:
    if _cache["records"] is None:
        records = db.active_records()
        for record in records:
            record["tokens"] = tokenize(record["nombre"])
        _cache["records"] = records
    return _cache["records"]


def persist_base(meta: dict, records: list[dict] | None = None, publish: bool = True) -> None:
    payload = records if records is not None else db.records_for_base(meta["id"])
    path = write_base(meta, payload)
    if publish and github_host.load_config().get("token"):
        github_host.push_file(path, f"Actualizar base {meta['slug']}")
        github_host.push_file(write_index(), "Actualizar índice de bases")


def export_db_bases() -> None:
    from .store import unique_slug

    existing = {base.get("slug") for base in db.list_bases() if base.get("slug")}
    for base in db.list_bases():
        if not base.get("slug"):
            slug = unique_slug(base["name"], existing)
            with db.connect() as conn:
                conn.execute("UPDATE bases SET slug = ? WHERE id = ?", (slug, base["id"]))
                conn.commit()
            base["slug"] = slug
            existing.add(slug)
        persist_base(base, publish=False)


def seed_if_empty() -> None:
    db.init_db()
    if github_host.load_config().get("token"):
        try:
            github_host.pull_remote_bases()
        except Exception:
            pass
    db.import_missing_files(read_all())
    if not db.list_bases() and SEED_XLSX.exists():
        records = parse_excel(SEED_XLSX)
        created = db.create_base("Lista OFAC / ONU 14/08/2026", SEED_XLSX.name, records)
        persist_base(created, records, publish=False)
    export_db_bases()
    invalidate_cache()


def with_hosting(stats: dict) -> dict:
    stats["hosting"] = github_host.public_status()
    return stats


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_data_dirs()
    UPLOADS.mkdir(parents=True, exist_ok=True)
    seed_if_empty()
    cached_records()
    yield


app = FastAPI(title="Buscador OFAC", lifespan=lifespan)
app.mount("/css", StaticFiles(directory=ROOT / "css"), name="css")
app.mount("/js", StaticFiles(directory=ROOT / "js"), name="js")


@app.get("/")
def searcher():
    return FileResponse(ROOT / "index.html")


@app.get("/admin")
def admin():
    return FileResponse(ROOT / "admin.html")


@app.get("/api/stats")
def api_stats():
    return with_hosting(db.stats())


@app.get("/api/bases")
def api_bases():
    return {"bases": db.list_bases()}


class SearchBody(BaseModel):
    nombre: str = ""
    identificacion: str = ""


@app.post("/api/search")
def api_search(body: SearchBody):
    if not body.nombre.strip() and not body.identificacion.strip():
        return {"results": []}
    results = search_records(cached_records(), body.nombre, body.identificacion)
    clean = []
    for item in results:
        record = {key: item["record"][key] for key in ("idInterno", "nombre", "identificacion", "lista", "base")}
        clean.append({**item, "record": record})
    return {"results": clean}


@app.post("/api/bases")
async def api_upload_base(
    archivo: UploadFile = File(...),
    nombre: str = Form(""),
):
    filename = archivo.filename or "lista.xlsx"
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(400, "Suba un archivo Excel (.xlsx).")

    raw = await archivo.read()
    if not raw:
        raise HTTPException(400, "El archivo está vacío.")

    UPLOADS.mkdir(parents=True, exist_ok=True)
    stored = UPLOADS / f"{db.now_iso().replace(':', '').replace(' ', '_')}_{filename}"
    stored.write_bytes(raw)

    try:
        records = parse_excel(stored)
    except ValueError as exc:
        stored.unlink(missing_ok=True)
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        stored.unlink(missing_ok=True)
        raise HTTPException(400, "No se pudo leer el Excel. Revise que tenga la estructura requerida.") from exc

    label = nombre.strip() or Path(filename).stem
    created = db.create_base(label, filename, records)
    try:
        persist_base(created, records, publish=True)
        hosting_error = ""
    except Exception as exc:
        hosting_error = str(exc)
    invalidate_cache()
    stats = with_hosting(db.stats())
    if hosting_error:
        stats["hosting"] = github_host.public_status(hosting_error)
    return {"ok": True, "base": created, "stats": stats}


class ActiveBody(BaseModel):
    active: bool


@app.patch("/api/bases/{base_id}")
def api_toggle_base(base_id: int, body: ActiveBody):
    updated = db.set_base_active(base_id, body.active)
    if not updated:
        raise HTTPException(404, "No existe esa base.")
    try:
        persist_base(updated, publish=True)
    except Exception:
        pass
    invalidate_cache()
    return {"ok": True, "base": updated, "stats": with_hosting(db.stats())}


@app.delete("/api/bases/{base_id}")
def api_delete_base(base_id: int):
    current = db.get_base(base_id)
    if not current or not db.delete_base(base_id):
        raise HTTPException(404, "No existe esa base.")
    if current.get("slug"):
        delete_base_file(current["slug"])
        try:
            github_host.delete_remote(current["slug"])
            if github_host.load_config().get("token"):
                github_host.push_file(write_index(), "Actualizar índice de bases")
        except Exception:
            pass
    invalidate_cache()
    return {"ok": True, "stats": with_hosting(db.stats())}


class HostingBody(BaseModel):
    repo: str
    token: str = ""
    branch: str = "main"


@app.get("/api/hosting")
def api_hosting():
    return github_host.verify() if github_host.load_config() else github_host.public_status()


@app.post("/api/hosting")
def api_hosting_save(body: HostingBody):
    try:
        github_host.save_config(body.repo, body.token, body.branch)
        status = github_host.verify()
        if status.get("error"):
            raise HTTPException(400, status["error"])
        return status
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/hosting/publish")
def api_hosting_publish():
    try:
        github_host.pull_remote_bases()
        db.import_missing_files(read_all())
        export_db_bases()
        status = github_host.publish_local_bases()
        invalidate_cache()
        return status
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.delete("/api/hosting")
def api_hosting_clear():
    github_host.clear_config()
    return github_host.public_status()


@app.get("/api/plantilla.xlsx")
def api_template():
    book = Workbook()
    sheet = book.active
    sheet.title = "Hoja1"
    sheet.append(["ID interno", "NOMBRE", "Identificación", "LISTA"])
    sheet.append([10000, "Juan Felipe Castro Maldonado", "123456789", "OFAC"])
    sheet.append([10001, "Ejemplo Empresa SAS", "900123456", "ONU"])
    buffer = BytesIO()
    book.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=plantilla-listas.xlsx"},
    )
