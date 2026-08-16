from __future__ import annotations

import re
import unicodedata
from typing import Any

NAME_THRESHOLD = 50
ID_THRESHOLD = 95
TOKEN_FUZZY = 0.8

STOPWORDS = {
    "de",
    "del",
    "la",
    "el",
    "los",
    "las",
    "y",
    "e",
    "o",
    "en",
    "un",
    "una",
    "the",
    "of",
    "and",
    "for",
    "al",
    "bin",
    "bint",
    "ben",
    "von",
    "van",
    "da",
    "das",
    "do",
    "dos",
    "ltda",
    "ltd",
    "sas",
    "sa",
    "scs",
    "cia",
    "llc",
    "inc",
    "corp",
    "co",
}

WORD_RE = re.compile(r"[^a-z0-9]+")


def fold(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.lower()


def tokenize(value: Any) -> list[str]:
    parts = WORD_RE.sub(" ", fold(value)).strip().split()
    return [token for token in parts if len(token) >= 2 and token not in STOPWORDS]


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def token_similarity(a: str, b: str) -> float:
    if a == b:
        return 1.0
    longest = max(len(a), len(b))
    if not longest:
        return 0.0
    if abs(len(a) - len(b)) / longest > 1 - TOKEN_FUZZY:
        return 0.0
    return 1 - levenshtein(a, b) / longest


def match_tokens(query_tokens: list[str], target_tokens: list[str]) -> list[dict]:
    used: set[int] = set()
    pairs: list[dict] = []
    for query_index, query_token in enumerate(query_tokens):
        best = 0.0
        best_index = -1
        for target_index, target_token in enumerate(target_tokens):
            if target_index in used:
                continue
            similarity = token_similarity(query_token, target_token)
            if similarity > best:
                best = similarity
                best_index = target_index
        if best_index >= 0 and best >= TOKEN_FUZZY:
            used.add(best_index)
            pairs.append(
                {
                    "queryIndex": query_index,
                    "targetIndex": best_index,
                    "queryToken": query_token,
                    "targetToken": target_tokens[best_index],
                    "similarity": best,
                }
            )
    return pairs


def name_score(query: str, target_name: str, target_tokens: list[str] | None = None) -> dict:
    query_tokens = tokenize(query)
    resolved_target = target_tokens if target_tokens is not None else tokenize(target_name)
    if not query_tokens or not resolved_target:
        return {"score": 0.0, "pairs": [], "queryTokens": query_tokens, "targetTokens": resolved_target}

    pairs = match_tokens(query_tokens, resolved_target)
    intersection = sum(pair["similarity"] for pair in pairs)
    union = len(query_tokens) + len(resolved_target) - intersection
    score = (intersection / union) * 100 if union else 0.0
    return {
        "score": score,
        "pairs": pairs,
        "queryTokens": query_tokens,
        "targetTokens": resolved_target,
    }


def normalize_id(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]", "", fold(value)).upper()
    if text.isdigit():
        text = text.lstrip("0") or "0"
    return text


def id_score(query: str, identification: str, id_interno: Any) -> dict:
    query_id = normalize_id(query)
    if not query_id:
        return {"score": 0.0, "field": None, "value": ""}

    best = {"score": 0.0, "field": None, "value": ""}
    for field, value in (
        ("identificacion", identification or ""),
        ("idInterno", str(id_interno or "")),
    ):
        target = normalize_id(value)
        if not target:
            continue
        longest = max(len(query_id), len(target))
        similarity = (1 - levenshtein(query_id, target) / longest) * 100
        if similarity > best["score"]:
            best = {"score": similarity, "field": field, "value": value}
    return best


def search_records(records: list[dict], nombre: str = "", identificacion: str = "") -> list[dict]:
    name_query = (nombre or "").strip()
    id_query = (identificacion or "").strip()
    results: list[dict] = []

    for record in records:
        name_result = (
            name_score(name_query, record["nombre"], record.get("tokens"))
            if name_query
            else {"score": 0.0, "pairs": []}
        )
        ident_result = (
            id_score(id_query, record.get("identificacion") or "", record.get("idInterno"))
            if id_query
            else {"score": 0.0, "field": None, "value": ""}
        )

        name_hit = bool(name_query) and name_result["score"] >= NAME_THRESHOLD
        id_hit = bool(id_query) and ident_result["score"] >= ID_THRESHOLD
        if not name_hit and not id_hit:
            continue

        risk_score = max(
            name_result["score"] if name_hit else 0.0,
            ident_result["score"] if id_hit else 0.0,
        )
        results.append(
            {
                "record": record,
                "riskScore": risk_score,
                "nameScore": name_result["score"],
                "idScore": ident_result["score"],
                "nameHit": name_hit,
                "idHit": id_hit,
                "pairs": name_result["pairs"],
                "idField": ident_result["field"],
            }
        )

    results.sort(key=lambda item: (-item["riskScore"], item["record"]["nombre"]))
    return results
