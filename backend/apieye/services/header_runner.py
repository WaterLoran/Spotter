"""Execute user Python snippets to produce HTTP headers; TTL cache per (system_id, snippet_id)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

_cache_lock = threading.Lock()
_cache: dict[tuple[int, int], dict] = {}


def _code_hash(code: str) -> str:
    return hashlib.sha256((code or "").encode("utf-8")).hexdigest()


def invalidate(snippet_id: int) -> None:
    sid = int(snippet_id)
    with _cache_lock:
        keys = [k for k in list(_cache.keys()) if k[1] == sid]
        for k in keys:
            del _cache[k]


def compute_headers(system_id: int, snippet_id: int, code: str, ttl_seconds: int) -> dict[str, str]:
    """Run snippet in a subprocess; cache result until TTL expires or code changes."""
    sys_id = int(system_id)
    snip_id = int(snippet_id)
    ttl = max(1, int(ttl_seconds or 300))
    now = time.time()
    key = (sys_id, snip_id)
    ch = _code_hash(code or "")

    with _cache_lock:
        ent = _cache.get(key)
        if ent and ent.get("code_hash") == ch and float(ent.get("expires_at", 0)) > now:
            return dict(ent["headers"])

    exec_timeout = min(max(ttl, 5), 30)

    runner_suffix = (
        "\n\n"
        "import json, sys\n"
        "_h = None\n"
        "if callable(globals().get('get_headers')):\n"
        "    _h = get_headers()\n"
        "elif 'headers' in globals():\n"
        "    _h = headers\n"
        "if _h is None:\n"
        "    _h = {}\n"
        "if not isinstance(_h, dict):\n"
        "    raise TypeError('headers must be a dict')\n"
        "_out = {}\n"
        "for _k, _v in _h.items():\n"
        "    _out[str(_k)] = str(_v)\n"
        "sys.stdout.write('__HEADERS__\\n')\n"
        "sys.stdout.write(json.dumps(_out, ensure_ascii=False))\n"
    )

    path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix="_apieye_header.py",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(code or "")
            f.write(runner_suffix)
            path = f.name

        proc = subprocess.run(
            [sys.executable, path],
            capture_output=True,
            text=True,
            timeout=exec_timeout,
        )
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        err = err[:4000] if err else f"exit code {proc.returncode}"
        raise RuntimeError(err)

    out = proc.stdout or ""
    marker = "__HEADERS__\n"
    idx = out.rfind(marker)
    if idx < 0:
        raise RuntimeError("snippet did not emit __HEADERS__ marker")
    json_part = out[idx + len(marker) :].strip()
    try:
        headers = json.loads(json_part)
    except json.JSONDecodeError as ex:
        raise RuntimeError(f"invalid headers JSON: {ex}") from ex
    if not isinstance(headers, dict):
        raise RuntimeError("headers JSON must be an object")

    str_headers = {str(k): str(v) for k, v in headers.items()}

    with _cache_lock:
        _cache[key] = {
            "code_hash": ch,
            "headers": str_headers,
            "expires_at": now + ttl,
        }
    return dict(str_headers)
