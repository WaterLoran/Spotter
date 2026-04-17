import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqleye.services.db_connector import connect_db


def _json_safe_value(value):
    """MySQL/PG 常见类型转为可 json.dumps / 可入库 JSON 的值。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, timedelta):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (bytearray, memoryview)):
        return bytes(value).decode("utf-8", errors="replace")
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (int, float, str, bool)):
        return value
    return str(value)


def _normalize_row(row: dict) -> dict:
    return {str(k): _json_safe_value(v) for k, v in row.items()}


def execute_sql(session_obj, sql):
    conn = connect_db(session_obj)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        if isinstance(rows, list) and rows and isinstance(rows[0], tuple):
            cols = [d[0] for d in cur.description or []]
            cols = [str(c) for c in cols]
            data = [_normalize_row(dict(zip(cols, row))) for row in rows]
        elif isinstance(rows, list) and rows and isinstance(rows[0], dict):
            data = [_normalize_row(r) for r in rows]
        elif isinstance(rows, list):
            data = rows
        else:
            data = []
        return data
    finally:
        conn.close()
