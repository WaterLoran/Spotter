#!/usr/bin/env python3
"""
Spotter API 自检：进程内 Flask 客户端（不依赖服务已启动）+ 可选 HTTP 探测。

用法:
  cd backend && source .venv/bin/activate
  SCHEDULER_ENABLED=false PYTHONPATH=. python ../scripts/verify_spotter_api.py

  # 同时检测已启动的后端（默认 5001，与 Vite 代理一致）
  python ../scripts/verify_spotter_api.py --http-backend

  # 检测经 Vite 转发的 /api（需 npm run dev 在 3000）
  python ../scripts/verify_spotter_api.py --http-vite
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

# 在导入 app 前关闭调度器，避免 SSH 后台报错干扰
os.environ.setdefault("SCHEDULER_ENABLED", "false")
os.environ.setdefault("PORT", "5001")


def _hdr(system_id: str = "1") -> dict[str, str]:
    return {"X-FastLog-System-Id": system_id, "Content-Type": "application/json"}


def _ok(resp_json: dict[str, Any]) -> bool:
    return bool(resp_json.get("success"))


def run_inprocess_tests() -> list[tuple[str, bool, str]]:
    """使用 Flask test_client 做增删查改，不占用端口。"""
    from app import app

    client = app.test_client()
    h = _hdr("1")
    results: list[tuple[str, bool, str]] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        results.append((name, cond, detail))

    # health + config 读
    r = client.get("/api/health", headers=h)
    j = r.get_json()
    check("GET /api/health", r.status_code == 200 and _ok(j), str(j)[:200])

    r = client.get("/api/config", headers=h)
    j = r.get_json()
    check("GET /api/config", r.status_code == 200 and _ok(j), "")

    # search-configs CRUD
    r = client.post(
        "/api/search-configs",
        json={
            "log_directory": "/tmp",
            "search_text": "verify",
            "init_time_range_minutes": 60,
            "context_lines_before": 0,
            "context_lines_after": 0,
            "enabled": True,
        },
        headers=h,
    )
    j = r.get_json() or {}
    sc_id = (j.get("data") or {}).get("id")
    check(
        "POST/PUT/DELETE search-configs",
        r.status_code == 200 and sc_id is not None,
        "",
    )
    if sc_id:
        r = client.put(
            f"/api/search-configs/{sc_id}",
            json={
                "log_directory": "/tmp",
                "search_text": "verify2",
                "init_time_range_minutes": 60,
                "context_lines_before": 0,
                "context_lines_after": 0,
                "enabled": False,
            },
            headers=h,
        )
        check("PUT search-config", r.status_code == 200 and _ok(r.get_json() or {}), "")
        r = client.delete(f"/api/search-configs/{sc_id}", headers=h)
        check("DELETE search-config", r.status_code == 200 and _ok(r.get_json() or {}), "")

    # log-views CRUD
    r = client.post(
        "/api/log-views",
        json={"name": "verify_view", "search_query": "test", "description": "", "sort_order": 99},
        headers=h,
    )
    j = r.get_json() or {}
    lv_id = (j.get("data") or {}).get("id")
    check("POST log-view", r.status_code == 200 and lv_id is not None, "")
    if lv_id:
        r = client.put(
            f"/api/log-views/{lv_id}",
            json={"name": "verify_view2", "search_query": "t2", "description": "d", "sort_order": 1},
            headers=h,
        )
        check("PUT log-view", r.status_code == 200 and _ok(r.get_json() or {}), "")
        r = client.delete(f"/api/log-views/{lv_id}", headers=h)
        check("DELETE log-view", r.status_code == 200 and _ok(r.get_json() or {}), "")

    # systems: 新建再删（保留默认系统）；新系统继承源 = 创建前 MAX(id)，与 database.create_system 一致
    r = client.get("/api/systems", headers=h)
    sys_items = ((r.get_json() or {}).get("data") or []) if r.status_code == 200 else []
    max_sid = max((int(x["id"]) for x in sys_items), default=1)
    r = client.get("/api/config", headers=_hdr(str(max_sid)))
    cfg_before_new_system = (r.get_json() or {}).get("data") or {}
    r = client.post("/api/systems", json={"name": "verify_system_tmp"}, headers=h)
    j = r.get_json() or {}
    new_sid = (j.get("data") or {}).get("id")
    check("POST system", r.status_code == 200 and new_sid is not None, "")
    if new_sid:
        r = client.get("/api/config", headers=_hdr(str(new_sid)))
        cfg_cloned = (r.get_json() or {}).get("data") or {}
        check("POST system clones main config", cfg_cloned == cfg_before_new_system, "")
        r = client.put(f"/api/systems/{new_sid}", json={"name": "verify_renamed"}, headers=h)
        check("PUT system", r.status_code == 200 and _ok(r.get_json() or {}), "")
        r = client.delete(f"/api/systems/{new_sid}", headers=h)
        check("DELETE system", r.status_code == 200 and _ok(r.get_json() or {}), "")

    # shell queries CRUD
    r = client.post(
        "/api/shell/queries",
        json={
            "name": "verify_shell",
            "command": "echo ok",
            "preset_key": "",
            "is_active": False,
            "polling_interval": 3600,
            "ignore_patterns": "",
        },
        headers=h,
    )
    j = r.get_json() or {}
    sh_id = (j.get("data") or {}).get("id")
    check("POST shell query", r.status_code == 200 and sh_id is not None, "")
    if sh_id:
        r = client.put(
            f"/api/shell/queries/{sh_id}",
            json={"name": "verify_shell2", "command": "echo ok2", "is_active": False},
            headers=h,
        )
        check("PUT shell query", r.status_code == 200 and _ok(r.get_json() or {}), "")
        r = client.delete(f"/api/shell/queries/{sh_id}", headers=h)
        check("DELETE shell query", r.status_code == 200 and _ok(r.get_json() or {}), "")

    # SQL: 先保存 session，再 queries CRUD（无真实 DB 连接，仅元数据）
    r = client.post(
        "/api/sql/sessions",
        json={
            "name": "verify_sql",
            "db_type": "sqlite",
            "host": "",
            "port": "",
            "username": "",
            "password": "",
            "database": ":memory:",
        },
        headers=h,
    )
    check("POST /api/sql/sessions", r.status_code == 200 and _ok(r.get_json() or {}), "")
    r = client.post(
        "/api/sql/queries",
        json={"name": "q_verify", "sql": "SELECT 1 AS n", "polling_interval": 999, "is_active": False},
        headers=h,
    )
    j = r.get_json() or {}
    qid = (j.get("data") or {}).get("id")
    check("POST /api/sql/queries", r.status_code == 200 and qid is not None, "")
    if qid:
        r = client.put(
            f"/api/sql/queries/{qid}",
            json={"name": "q_verify2", "sql": "SELECT 2", "polling_interval": 998, "is_active": False},
            headers=h,
        )
        check("PUT /api/sql/queries", r.status_code == 200 and _ok(r.get_json() or {}), "")
        r = client.delete(f"/api/sql/queries/{qid}", headers=h)
        check("DELETE /api/sql/queries", r.status_code == 200 and _ok(r.get_json() or {}), "")

    # 新建系统继承「当前 MAX(id) 系统」的 SQL Session，模板需与该源系统一致（不一定是 id=1）
    r = client.get("/api/systems", headers=h)
    sys_list = (r.get_json() or {}).get("data") or []
    max_sid = max(int(s["id"]) for s in sys_list) if sys_list else 1
    r = client.get("/api/sql/sessions", headers=_hdr(str(max_sid)))
    template_sql = (r.get_json() or {}).get("data")
    r = client.post("/api/systems", json={"name": "verify_clone_sql"}, headers=h)
    j = r.get_json() or {}
    clone_sql_sid = (j.get("data") or {}).get("id")
    check("POST system (for sql clone)", r.status_code == 200 and clone_sql_sid is not None, "")
    if clone_sql_sid:
        r = client.get("/api/sql/sessions", headers=_hdr(str(clone_sql_sid)))
        j = r.get_json() or {}
        cloned_sql = j.get("data")

        def _sql_session_compare(a: Any, b: Any) -> bool:
            if a is None and b is None:
                return True
            if not isinstance(a, dict) or not isinstance(b, dict):
                return False
            keys = ("name", "db_type", "host", "port", "username", "password", "database")
            return all(a.get(k) == b.get(k) for k in keys)

        sql_clone_ok = r.status_code == 200 and _ok(j) and _sql_session_compare(template_sql, cloned_sql)
        check("GET sql/sessions on cloned system", sql_clone_ok, str(j)[:300])
        r = client.delete(f"/api/systems/{clone_sql_sid}", headers=h)
        check("DELETE cloned system (sql)", r.status_code == 200 and _ok(r.get_json() or {}), "")

    # timeline notes（需要已有 log view；若无则临时创建一个）
    r = client.get("/api/log-views", headers=h)
    j = r.get_json() or {}
    views = (j.get("data") or []) if _ok(j) else []
    first_view = views[0]["id"] if views else None
    if not first_view:
        r = client.post(
            "/api/log-views",
            json={"name": "verify_timeline_view", "search_query": "", "description": "", "sort_order": 0},
            headers=h,
        )
        j = r.get_json() or {}
        first_view = (j.get("data") or {}).get("id")
    if first_view:
        r = client.post(
            f"/api/log-views/{first_view}/timeline-notes",
            json={"title": "t", "content": "c", "tags": []},
            headers=h,
        )
        j = r.get_json() or {}
        nid = (j.get("data") or {}).get("id")
        check("POST timeline-note", r.status_code == 200 and nid is not None, "")
        if nid:
            r = client.put(
                f"/api/log-views/timeline-notes/{nid}",
                json={"title": "t2", "content": "c2", "tags": ["a"]},
                headers=h,
            )
            check("PUT timeline-note", r.status_code == 200 and _ok(r.get_json() or {}), "")
            r = client.delete(f"/api/log-views/timeline-notes/{nid}", headers=h)
            check("DELETE timeline-note", r.status_code == 200 and _ok(r.get_json() or {}), "")
    else:
        check("timeline-note CRUD", False, "no log view")

    return results


def _http_json(method: str, url: str, body: dict | None = None, timeout: float = 10.0) -> tuple[int, dict | None, str | None]:
    data = None
    headers = _hdr()
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw) if raw else None, None
            except json.JSONDecodeError:
                return resp.status, None, raw[:500]
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw) if raw else None, None
        except json.JSONDecodeError:
            return e.code, None, raw[:500]
    except OSError as e:
        return -1, None, str(e)


def run_http_checks(base: str, retries: int = 5, retry_delay: float = 1.0) -> list[tuple[str, bool, str]]:
    """base 例如 http://127.0.0.1:5001 或 http://127.0.0.1:3000（Vite 代理）。会先重试 health 以便服务刚启动时也能过。"""
    base = base.rstrip("/")
    results: list[tuple[str, bool, str]] = []

    code, j, err = -1, None, None
    for attempt in range(retries + 1):
        code, j, err = _http_json("GET", f"{base}/api/health")
        if code == 200 and j and _ok(j):
            break
        if attempt < retries:
            time.sleep(retry_delay)

    ok = code == 200 and j and _ok(j)
    results.append(("HTTP GET /api/health", ok, err or (str(j)[:120] if j else f"code={code}")))

    code, j, err = _http_json("GET", f"{base}/api/systems")
    ok = code == 200 and j and _ok(j)
    results.append(("HTTP GET /api/systems", ok, err or ""))

    code, j, err = _http_json(
        "POST",
        f"{base}/api/search-configs",
        {
            "log_directory": "/tmp",
            "search_text": "http_verify",
            "init_time_range_minutes": 60,
            "context_lines_before": 0,
            "context_lines_after": 0,
            "enabled": True,
        },
    )
    sc_id = (j.get("data") or {}).get("id") if j else None
    ok = code == 200 and sc_id is not None
    results.append(("HTTP POST search-config", ok, err or str(j)[:200]))

    if sc_id:
        _http_json("DELETE", f"{base}/api/search-configs/{sc_id}")

    return results


def print_results(title: str, rows: list[tuple[str, bool, str]], verbose: bool) -> int:
    print(f"\n=== {title} ===")
    failed = 0
    for name, ok, detail in rows:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
        if not ok or (verbose and detail):
            if detail:
                print(f"         {detail}")
        if not ok:
            failed += 1
    return failed


def main() -> int:
    parser = argparse.ArgumentParser(description="Spotter API 验证")
    parser.add_argument("--http-backend", action="store_true", help="探测 http://127.0.0.1:5001/api")
    parser.add_argument("--http-vite", action="store_true", help="探测 http://127.0.0.1:3000/api（需 Vite）")
    parser.add_argument("--backend-url", default="http://127.0.0.1:5001", help="自定义后端基址")
    parser.add_argument("--vite-url", default="http://127.0.0.1:3000", help="自定义前端基址（代理 /api）")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "--http-retries",
        type=int,
        default=5,
        help="HTTP 模式下 health 重试次数（默认 5，间隔 1s）",
    )
    args = parser.parse_args()

    # 确保从 backend 目录运行时能找到模块
    backend_dir = os.path.join(os.path.dirname(__file__), "..", "backend")
    backend_dir = os.path.abspath(backend_dir)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    os.chdir(backend_dir)

    total_fail = 0

    rows = run_inprocess_tests()
    total_fail += print_results("Flask 进程内 API（CRUD）", rows, args.verbose)

    if args.http_backend:
        rows = run_http_checks(args.backend_url, retries=max(0, args.http_retries))
        total_fail += print_results(f"HTTP 后端 {args.backend_url}", rows, args.verbose)
        if any(not r[1] for r in rows):
            print(
                "\n提示: 若连接失败，请在 backend 目录执行:\n"
                f"  SCHEDULER_ENABLED=false PORT=5001 PYTHONPATH=. python app.py\n"
                "或使用项目根目录 ./start.sh"
            )

    if args.http_vite:
        rows = run_http_checks(args.vite_url, retries=max(0, args.http_retries))
        total_fail += print_results(f"HTTP 经 Vite {args.vite_url}", rows, args.verbose)
        if any(not r[1] for r in rows):
            print(
                "\n提示: 需前端开发服务:\n"
                "  cd frontend && npm run dev\n"
                "并确认 frontend/vite.config.js 中 proxy /api 指向你的后端端口。"
            )

    print()
    if total_fail == 0:
        print("全部通过。")
        return 0
    print(f"失败项: {total_fail}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
