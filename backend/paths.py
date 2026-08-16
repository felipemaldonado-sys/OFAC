from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR") or (ROOT / "data"))
SEED_DIR = ROOT / "data"
SEED_XLSX = SEED_DIR / "Lista Ofac 14082026.xlsx"
BASES_DIR = DATA_DIR / "bases"
UPLOADS_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "ofac.db"
HOSTING_PATH = DATA_DIR / "hosting.json"


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BASES_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    seed_bases = SEED_DIR / "bases"
    if seed_bases.exists() and not any(BASES_DIR.glob("*.json")):
        for path in seed_bases.glob("*.json"):
            target = BASES_DIR / path.name
            if not target.exists():
                target.write_bytes(path.read_bytes())
