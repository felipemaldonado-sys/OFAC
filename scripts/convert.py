#!/usr/bin/env python3
"""Convierte el Excel de listas restrictivas a data/ofac-data.js."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def clean_id(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "nat"}:
        return ""
    if text.endswith(".0") and text.replace(".", "", 1).isdigit():
        text = text[:-2]
    return text


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "xlsx",
        nargs="?",
        default=str(root / "data" / "Lista Ofac 14082026.xlsx"),
    )
    args = parser.parse_args()

    source = Path(args.xlsx)
    if not source.exists():
        raise SystemExit(f"No se encontró el Excel: {source}")

    df = pd.read_excel(source)
    expected = {"ID interno", "NOMBRE", "Identificación", "LISTA"}
    missing = expected - set(df.columns)
    if missing:
        raise SystemExit(f"Faltan columnas {missing}. Encontradas: {list(df.columns)}")

    records = []
    for row in df.itertuples(index=False):
        records.append(
            {
                "idInterno": int(row[0]),
                "nombre": str(row[1]).strip(),
                "identificacion": clean_id(row[2]),
                "lista": str(row[3]).strip(),
            }
        )

    payload = {
        "sourceFile": source.name,
        "total": len(records),
        "records": records,
    }

    out_dir = root / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    js_path = out_dir / "ofac-data.js"
    js_path.write_text(
        "window.OFAC_LIST = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    print(f"OK {len(records)} registros → {js_path}")


if __name__ == "__main__":
    main()
