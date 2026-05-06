"""Execute HTTP requests for API query tasks."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

import requests


def _merge_query(url: str, query_params: list | None) -> str:
    if not query_params:
        return url
    pairs = []
    for item in query_params:
        if not isinstance(item, dict):
            continue
        if not item.get("enabled", True):
            continue
        k = item.get("key")
        if k is None or str(k).strip() == "":
            continue
        pairs.append((str(k), str(item.get("value", ""))))
    if not pairs:
        return url
    q = urlencode(pairs)
    parts = urlsplit(url)
    existing = parts.query
    new_q = f"{existing}&{q}" if existing else q
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_q, parts.fragment))


def _normalize_body(body_type: str, body: str | None) -> tuple[Any, str | None]:
    bt = (body_type or "none").lower()
    raw = body if body is not None else ""
    if bt == "none":
        return None, None
    if bt == "json":
        if not raw.strip():
            return None, None
        try:
            return json.loads(raw), None
        except json.JSONDecodeError:
            raise ValueError("请求体不是合法 JSON") from None
    if bt == "form":
        if not raw.strip():
            return None, None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError("form 请求体需为 JSON 对象，如 {\"a\":\"1\"}") from None
        if not isinstance(data, dict):
            raise ValueError("form 请求体需为 JSON 对象")
        return data, None
    if bt == "form-data":
        # body is a JSON array: [{key, value, enabled}, ...]
        if not raw.strip():
            return [], None
        try:
            pairs = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError("form-data 请求体格式有误") from None
        if not isinstance(pairs, list):
            raise ValueError("form-data 请求体需为键值对数组")
        return pairs, None
    if bt == "raw":
        return raw, None
    return None, None


def rows_for_history_hash(
    status_code: int | None,
    response_data: Any,
    response_text: str | None,
    error: str | None,
) -> list[dict]:
    """Build row list for result_hash / diff (aligned with SQL row semantics)."""
    if error:
        return [{"_error": error, "_status": status_code}]
    if isinstance(response_data, list) and response_data and all(isinstance(x, dict) for x in response_data):
        return response_data
    if isinstance(response_data, dict):
        for v in response_data.values():
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                return v
        return [response_data]
    if response_text is not None and str(response_text).strip() != "":
        return [{"_raw": str(response_text), "_status": status_code}]
    return [{"_status": status_code}]


def execute_http_task(
    method: str,
    url: str,
    query_params: list | None,
    body_type: str,
    body: str | None,
    extra_headers: dict[str, str] | None,
    timeout_sec: int,
) -> dict[str, Any]:
    """
    Perform HTTP request. Returns dict with status_code, response_headers, response_data,
    response_text, error (only on transport/timeout/validation failure).
    """
    m = (method or "GET").upper()
    final_url = _merge_query(url or "", query_params)
    if not final_url or not final_url.strip():
        raise ValueError("URL 不能为空")

    headers: dict[str, str] = {"Accept": "application/json"}
    if extra_headers:
        headers.update({str(k): str(v) for k, v in extra_headers.items()})

    timeout = max(1, min(int(timeout_sec or 30), 300))

    try:
        body_obj, raw_body = _normalize_body(body_type, body)
    except ValueError as ex:
        raise ValueError(str(ex)) from ex

    kwargs: dict[str, Any] = {"headers": headers, "timeout": timeout}
    if m in ("GET", "HEAD", "DELETE"):
        resp = requests.request(m, final_url, **kwargs)
    elif m in ("POST", "PUT", "PATCH"):
        bt = (body_type or "none").lower()
        if bt == "json" and body_obj is not None:
            kwargs["json"] = body_obj
        elif bt == "form" and body_obj is not None:
            kwargs["data"] = body_obj
        elif bt == "form-data":
            # multipart/form-data — let requests set Content-Type with boundary
            pairs = body_obj if isinstance(body_obj, list) else []
            files = {
                str(item["key"]): (None, str(item.get("value", "")))
                for item in pairs
                if isinstance(item, dict) and item.get("enabled", True) and str(item.get("key", "")).strip()
            }
            kwargs["files"] = files
        elif bt == "raw" and raw_body is not None:
            rb = raw_body.encode("utf-8") if isinstance(raw_body, str) else raw_body
            kwargs["data"] = rb
            if "Content-Type" not in kwargs["headers"]:
                kwargs["headers"]["Content-Type"] = "application/octet-stream"
        resp = requests.request(m, final_url, **kwargs)
    else:
        raise ValueError(f"不支持的 HTTP 方法: {m}")

    status_code = int(resp.status_code)
    resp_headers = {k: v for k, v in resp.headers.items()}
    text = resp.text
    response_data = None
    try:
        if text.strip():
            response_data = resp.json()
    except ValueError:
        response_data = None

    return {
        "status_code": status_code,
        "response_headers": resp_headers,
        "response_data": response_data,
        "response_text": text,
        "error": None,
    }
