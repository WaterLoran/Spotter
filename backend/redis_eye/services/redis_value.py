"""从 Redis 读取任意类型 key 的展示用字符串。"""
from __future__ import annotations

import json
from typing import Any, Tuple


def fetch_value_display(client: Any, key: str) -> Tuple[str, str]:
    """
    返回 (展示文本, redis 类型名)。
    client 为 redis.Redis 实例，建议 decode_responses=True。
    """
    try:
        t = client.type(key)
    except Exception as ex:
        return f"(读取失败: {ex})", "error"

    if not t or str(t).lower() == "none":
        return "(nil)", "none"

    t = str(t).lower()

    try:
        if t == "string":
            v = client.get(key)
            if v is None:
                return "(nil)", "string"
            return str(v), "string"

        if t == "hash":
            d = client.hgetall(key)
            if not d:
                return "{}", "hash"
            return json.dumps(dict(d), ensure_ascii=False), "hash"

        if t == "list":
            items = client.lrange(key, 0, 99)
            return json.dumps(list(items), ensure_ascii=False), "list"

        if t == "set":
            members = sorted(client.smembers(key))
            return json.dumps(list(members), ensure_ascii=False), "set"

        if t == "zset":
            pairs = client.zrange(key, 0, 99, withscores=True)
            out = [{"member": m, "score": float(s)} for m, s in pairs]
            return json.dumps(out, ensure_ascii=False), "zset"

        if t == "stream":
            entries = client.xrange(key, min="-", max="+", count=100)
            out = []
            for entry_id, fields in entries:
                out.append({"id": entry_id, "fields": dict(fields)})
            return json.dumps(out, ensure_ascii=False), "stream"

        return f"(不支持展示的类型: {t})", t
    except Exception as ex:
        return f"(读取失败: {ex})", t
