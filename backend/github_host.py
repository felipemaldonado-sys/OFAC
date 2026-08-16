from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from pathlib import Path

from .paths import BASES_DIR, HOSTING_PATH

CONFIG_PATH = HOSTING_PATH
REMOTE_DIR = "bases"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_config(repo: str, token: str, branch: str = "main") -> dict:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    current = load_config()
    payload = {
        "repo": repo.strip().strip("/"),
        "token": token.strip() or current.get("token", ""),
        "branch": (branch or "main").strip() or "main",
    }
    if not payload["repo"] or "/" not in payload["repo"]:
        raise ValueError("El repo debe verse así: usuario/nombre-del-repo")
    if not payload["token"]:
        raise ValueError("Falta el token de GitHub.")
    CONFIG_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return public_status()


def clear_config() -> None:
    CONFIG_PATH.unlink(missing_ok=True)


def public_status(error: str = "") -> dict:
    config = load_config()
    repo = config.get("repo") or ""
    configured = bool(repo and config.get("token"))
    return {
        "configured": configured,
        "repo": repo,
        "branch": config.get("branch") or "main",
        "url": f"https://github.com/{repo}/tree/{config.get('branch') or 'main'}/{REMOTE_DIR}" if repo else "",
        "ok": configured and not error,
        "error": error,
        "message": (
            f"Las bases se publican en GitHub: {repo}"
            if configured and not error
            else error
            or "Aún no está conectado. Cree un repo privado y pegue un token para alojar las bases en internet."
        ),
    }


def _request(method: str, url: str, token: str, body: dict | None = None) -> dict | list | None:
    request = urllib.request.Request(url, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    request.add_header("User-Agent", "ofac-buscador")
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, data=data, timeout=60) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code == 404 and method == "GET":
            return None
        raise RuntimeError(f"GitHub {exc.code}: {detail}") from exc


def verify() -> dict:
    config = load_config()
    if not config.get("repo") or not config.get("token"):
        return public_status()
    try:
        _request("GET", f"https://api.github.com/repos/{config['repo']}", config["token"])
        return public_status()
    except Exception as exc:
        return public_status(str(exc))


def _file_sha(remote_path: str) -> str | None:
    config = load_config()
    url = f"https://api.github.com/repos/{config['repo']}/contents/{remote_path}?ref={config.get('branch') or 'main'}"
    payload = _request("GET", url, config["token"])
    if isinstance(payload, dict):
        return payload.get("sha")
    return None


def push_file(local_path: Path, message: str) -> None:
    config = load_config()
    if not config.get("repo") or not config.get("token"):
        raise RuntimeError("GitHub no está conectado.")
    remote_path = f"{REMOTE_DIR}/{local_path.name}"
    content = base64.b64encode(local_path.read_bytes()).decode("ascii")
    body = {
        "message": message,
        "content": content,
        "branch": config.get("branch") or "main",
    }
    sha = _file_sha(remote_path)
    if sha:
        body["sha"] = sha
    _request(
        "PUT",
        f"https://api.github.com/repos/{config['repo']}/contents/{remote_path}",
        config["token"],
        body,
    )


def delete_remote(slug: str) -> None:
    config = load_config()
    if not config.get("repo") or not config.get("token"):
        return
    remote_path = f"{REMOTE_DIR}/{slug}.json"
    sha = _file_sha(remote_path)
    if not sha:
        return
    _request(
        "DELETE",
        f"https://api.github.com/repos/{config['repo']}/contents/{remote_path}",
        config["token"],
        {
            "message": f"Borrar base {slug}",
            "sha": sha,
            "branch": config.get("branch") or "main",
        },
    )


def publish_local_bases() -> dict:
    BASES_DIR.mkdir(parents=True, exist_ok=True)
    files = [path for path in sorted(BASES_DIR.glob("*.json"))]
    if not files:
        raise RuntimeError("No hay bases locales para publicar.")
    for path in files:
        push_file(path, f"Publicar {path.name}")
    return verify()


def pull_remote_bases() -> int:
    config = load_config()
    if not config.get("repo") or not config.get("token"):
        return 0
    url = f"https://api.github.com/repos/{config['repo']}/contents/{REMOTE_DIR}?ref={config.get('branch') or 'main'}"
    listing = _request("GET", url, config["token"])
    if not isinstance(listing, list):
        return 0
    BASES_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for item in listing:
        name = item.get("name") or ""
        if not name.endswith(".json"):
            continue
        file_url = item.get("download_url")
        if not file_url:
            continue
        request = urllib.request.Request(file_url, headers={"User-Agent": "ofac-buscador"})
        with urllib.request.urlopen(request, timeout=60) as response:
            (BASES_DIR / name).write_bytes(response.read())
        count += 1
    return count
