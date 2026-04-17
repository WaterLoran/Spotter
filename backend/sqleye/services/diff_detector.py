import hashlib
import json


def _as_row_list(rows):
    if not rows:
        return []
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def result_hash(rows):
    rows = _as_row_list(rows)
    raw = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def detect_diff(prev_rows, curr_rows):
    prev_rows = _as_row_list(prev_rows)
    curr_rows = _as_row_list(curr_rows)

    def key(r):
        return json.dumps(r, ensure_ascii=False, sort_keys=True, default=str)

    prev_idx = {key(r): r for r in prev_rows}
    curr_idx = {key(r): r for r in curr_rows}
    added_keys = set(curr_idx.keys()) - set(prev_idx.keys())
    removed_keys = set(prev_idx.keys()) - set(curr_idx.keys())
    return {
        "added_rows": [curr_idx[k] for k in added_keys],
        "removed_rows": [prev_idx[k] for k in removed_keys],
        "different_rows": [],
    }
