from __future__ import annotations

from pathlib import Path

import pandas as pd

from .matcher import fold

REQUIRED = {
    "id interno": "ID interno",
    "nombre": "NOMBRE",
    "identificacion": "Identificación",
    "identificación": "Identificación",
    "lista": "LISTA",
}


def clean_id(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "nat"}:
        return ""
    if text.endswith(".0") and text.replace(".", "", 1).isdigit():
        text = text[:-2]
    return text


def parse_excel(path: str | Path) -> list[dict]:
    df = pd.read_excel(path)
    df.columns = [str(column).strip() for column in df.columns]

    mapped = {}
    for column in df.columns:
        key = fold(column).replace("ó", "o")
        if key in REQUIRED and REQUIRED[key] not in mapped:
            mapped[REQUIRED[key]] = column

    missing = [label for label in ("ID interno", "NOMBRE", "Identificación", "LISTA") if label not in mapped]
    if missing:
        raise ValueError(
            "El Excel debe tener las columnas: ID interno, NOMBRE, Identificación y LISTA. "
            f"Faltan: {', '.join(missing)}."
        )

    records = []
    for row in df.itertuples(index=False):
        data = {df.columns[index]: value for index, value in enumerate(row)}
        nombre = str(data[mapped["NOMBRE"]]).strip()
        if not nombre or nombre.lower() == "nan":
            continue
        id_interno = clean_id(data[mapped["ID interno"]]) or str(len(records) + 1)
        records.append(
            {
                "idInterno": id_interno,
                "nombre": nombre,
                "identificacion": clean_id(data[mapped["Identificación"]]),
                "lista": str(data[mapped["LISTA"]]).strip() if not pd.isna(data[mapped["LISTA"]]) else "",
            }
        )

    if not records:
        raise ValueError("El archivo no tiene registros válidos.")
    return records
