import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from config import DEFAULT_CONFIG, MAIN_DB_PATH


@contextmanager
def get_conn():
    conn = sqlite3.connect(MAIN_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS systems (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                system_id INTEGER NOT NULL DEFAULT 1,
                log_content TEXT NOT NULL,
                file_path TEXT NOT NULL,
                line_number INTEGER NOT NULL,
                search_text TEXT NOT NULL,
                notes TEXT,
                printed_at TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_logs_system_file_line ON logs(system_id, file_path, line_number);
            CREATE INDEX IF NOT EXISTS idx_logs_created_at ON logs(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_logs_file_path ON logs(file_path);
            CREATE INDEX IF NOT EXISTS idx_logs_printed_at ON logs(printed_at DESC);
            CREATE INDEX IF NOT EXISTS idx_logs_system_printed_at ON logs(system_id, printed_at DESC);
            CREATE TABLE IF NOT EXISTS file_states (
                system_id INTEGER NOT NULL DEFAULT 1,
                file_path TEXT NOT NULL,
                last_size INTEGER NOT NULL DEFAULT 0,
                last_position INTEGER NOT NULL DEFAULT 0,
                last_line_number INTEGER NOT NULL DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (system_id, file_path)
            );
            CREATE TABLE IF NOT EXISTS config (
                system_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (system_id, key)
            );
            CREATE TABLE IF NOT EXISTS search_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                system_id INTEGER NOT NULL DEFAULT 1,
                log_directory TEXT NOT NULL,
                search_text TEXT NOT NULL,
                init_time_range_minutes INTEGER NOT NULL DEFAULT 120,
                context_lines_before INTEGER NOT NULL DEFAULT 20,
                context_lines_after INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS log_views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                system_id INTEGER NOT NULL DEFAULT 1,
                name TEXT NOT NULL,
                search_query TEXT NOT NULL DEFAULT '',
                description TEXT DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS log_view_timeline_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                view_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                title TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (view_id) REFERENCES log_views(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS shell_queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                system_id INTEGER NOT NULL DEFAULT 1,
                name TEXT NOT NULL,
                command TEXT NOT NULL,
                preset_key TEXT DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 0,
                polling_interval INTEGER NOT NULL DEFAULT 60,
                ignore_patterns TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS shell_query_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_id INTEGER NOT NULL,
                executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                full_output TEXT NOT NULL,
                is_different INTEGER NOT NULL DEFAULT 0,
                diff_lines_json TEXT,
                FOREIGN KEY (query_id) REFERENCES shell_queries(id) ON DELETE CASCADE
            );
            """
        )
        cur.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS logs_fts
            USING fts5(log_content, file_path, content='');
            """
        )
        conn.commit()
        _ensure_file_states_schema(conn)
        _ensure_logs_ingest_chunk_schema(conn)
    ensure_default_system()


def _ensure_logs_ingest_chunk_schema(conn):
    """Allow same logical line_number for full-scan vs tail chunks (UNIQUE was blocking inserts)."""
    cur = conn.execute("PRAGMA table_info(logs)")
    cols = {row[1] for row in cur.fetchall()}
    if "ingest_chunk_start_byte" in cols:
        return
    conn.execute("DROP INDEX IF EXISTS idx_logs_system_file_line")
    conn.execute("ALTER TABLE logs ADD COLUMN ingest_chunk_start_byte INTEGER")
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_logs_system_file_line_chunk
        ON logs(system_id, file_path, line_number, COALESCE(ingest_chunk_start_byte, -1))
        """
    )
    conn.commit()


def _ensure_file_states_schema(conn):
    """Add last_remote_mtime for mtime+size based change detection (SQLite migrate)."""
    cur = conn.execute("PRAGMA table_info(file_states)")
    cols = {row[1] for row in cur.fetchall()}
    if "last_remote_mtime" not in cols:
        conn.execute("ALTER TABLE file_states ADD COLUMN last_remote_mtime INTEGER")
        conn.commit()


def ensure_default_system():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS c FROM systems")
        if cur.fetchone()["c"] == 0:
            cur.execute("INSERT INTO systems(name) VALUES (?)", ("默认系统",))
            conn.commit()
        cur.execute("SELECT id FROM systems ORDER BY id ASC LIMIT 1")
        system_id = int(cur.fetchone()["id"])
        for key, value in DEFAULT_CONFIG.items():
            cur.execute(
                "INSERT OR IGNORE INTO config(system_id, key, value) VALUES (?, ?, ?)",
                (system_id, key, str(value)),
            )
        cur.execute("SELECT COUNT(*) AS c FROM log_views WHERE system_id=?", (system_id,))
        if cur.fetchone()["c"] == 0:
            cur.execute(
                "INSERT INTO log_views(system_id, name, search_query, description, sort_order) VALUES (?, ?, ?, ?, ?)",
                (system_id, "默认视图", "", "", 0),
            )
        conn.commit()


def row_to_dict(row):
    return dict(row) if row is not None else None


def list_systems():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM systems ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]


def _copy_main_db_system_config(cur, source_system_id: int, target_system_id: int) -> None:
    """Copy per-system settings from source to target. Does not copy logs, file_states, or shell_query_history."""
    cur.execute(
        "INSERT INTO config(system_id, key, value) SELECT ?, key, value FROM config WHERE system_id=?",
        (target_system_id, source_system_id),
    )
    cur.execute(
        """
        INSERT INTO search_configs(
            system_id, log_directory, search_text, init_time_range_minutes,
            context_lines_before, context_lines_after, enabled, created_at, updated_at
        )
        SELECT ?, log_directory, search_text, init_time_range_minutes,
            context_lines_before, context_lines_after, enabled, created_at, updated_at
        FROM search_configs WHERE system_id=?
        """,
        (target_system_id, source_system_id),
    )
    view_rows = cur.execute(
        "SELECT id, name, search_query, description, sort_order FROM log_views WHERE system_id=? ORDER BY id ASC",
        (source_system_id,),
    ).fetchall()
    view_map: dict[int, int] = {}
    for v in view_rows:
        cur.execute(
            """
            INSERT INTO log_views(system_id, name, search_query, description, sort_order)
            VALUES (?, ?, ?, ?, ?)
            """,
            (target_system_id, v["name"], v["search_query"], v["description"], v["sort_order"]),
        )
        view_map[int(v["id"])] = int(cur.lastrowid)
    for old_vid, new_vid in view_map.items():
        notes = cur.execute(
            "SELECT title, content, tags FROM log_view_timeline_notes WHERE view_id=? ORDER BY id ASC",
            (old_vid,),
        ).fetchall()
        for n in notes:
            cur.execute(
                "INSERT INTO log_view_timeline_notes(view_id, title, content, tags) VALUES (?, ?, ?, ?)",
                (new_vid, n["title"], n["content"], n["tags"]),
            )
    cur.execute(
        """
        INSERT INTO shell_queries(
            system_id, name, command, preset_key, is_active, polling_interval, ignore_patterns, created_at, updated_at
        )
        SELECT ?, name, command, preset_key, is_active, polling_interval, ignore_patterns, created_at, updated_at
        FROM shell_queries WHERE system_id=?
        """,
        (target_system_id, source_system_id),
    )


def create_system(name):
    """Create a system row. Copies config from the current MAX(id) system when one exists; otherwise seeds defaults.

    Returns (new_system_id, source_system_id). source_system_id is None only when the table was empty before insert.
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT MAX(id) AS m FROM systems")
        row = cur.fetchone()
        max_before = row["m"] if row is not None else None

        cur.execute("INSERT INTO systems(name) VALUES (?)", (name,))
        new_id = cur.lastrowid

        if max_before is None:
            for key, value in DEFAULT_CONFIG.items():
                cur.execute(
                    "INSERT INTO config(system_id, key, value) VALUES (?, ?, ?)",
                    (new_id, key, str(value)),
                )
            cur.execute(
                "INSERT INTO log_views(system_id, name, search_query, description, sort_order) VALUES (?, ?, '', '', 0)",
                (new_id, "默认视图"),
            )
            source_id = None
        else:
            _copy_main_db_system_config(cur, max_before, new_id)
            source_id = int(max_before)

        conn.commit()
        return new_id, source_id


def rename_system(system_id, name):
    with get_conn() as conn:
        conn.execute("UPDATE systems SET name=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (name, system_id))
        conn.commit()


def delete_system(system_id):
    with get_conn() as conn:
        c = conn.execute("SELECT COUNT(*) AS c FROM systems").fetchone()["c"]
        if c <= 1:
            raise ValueError("至少保留一个系统")
        conn.execute("DELETE FROM logs WHERE system_id=?", (system_id,))
        conn.execute("DELETE FROM file_states WHERE system_id=?", (system_id,))
        conn.execute("DELETE FROM config WHERE system_id=?", (system_id,))
        conn.execute("DELETE FROM search_configs WHERE system_id=?", (system_id,))
        conn.execute("DELETE FROM shell_queries WHERE system_id=?", (system_id,))
        conn.execute("DELETE FROM log_views WHERE system_id=?", (system_id,))
        conn.execute("DELETE FROM systems WHERE id=?", (system_id,))
        conn.commit()


def parse_stored_int(value, default=0):
    """Coerce config table string values (or JSON numbers) to int; empty/invalid → default."""
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    s = str(value).strip()
    if not s:
        return default
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return default


def get_config(system_id):
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM config WHERE system_id=?", (system_id,)).fetchall()
        data = {r["key"]: r["value"] for r in rows}
        return {**DEFAULT_CONFIG, **data}


def update_config(system_id, payload):
    with get_conn() as conn:
        for key, value in payload.items():
            conn.execute(
                """
                INSERT INTO config(system_id, key, value) VALUES (?, ?, ?)
                ON CONFLICT(system_id, key) DO UPDATE SET value=excluded.value
                """,
                (system_id, key, str(value)),
            )
        conn.commit()


def create_log(
    system_id,
    log_content,
    file_path,
    line_number,
    search_text,
    notes=None,
    printed_at=None,
    *,
    ingest_chunk_start_byte=None,
):
    with get_conn() as conn:
        cur = conn.cursor()
        _before = conn.total_changes
        cur.execute(
            """
            INSERT OR IGNORE INTO logs(
                system_id, log_content, file_path, line_number, search_text, notes, printed_at,
                ingest_chunk_start_byte
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (system_id, log_content, file_path, line_number, search_text, notes, printed_at, ingest_chunk_start_byte),
        )
        if conn.total_changes <= _before:
            conn.commit()
            return 0
        log_id = cur.lastrowid
        cur.execute(
            "INSERT INTO logs_fts(rowid, log_content, file_path) VALUES (?, ?, ?)",
            (log_id, log_content, file_path),
        )
        conn.commit()
        return log_id


def list_logs(system_id, page=1, page_size=20, search="", notes_only=False):
    offset = max(page - 1, 0) * page_size
    where = ["system_id=?"]
    args = [system_id]
    if notes_only:
        where.append("notes IS NOT NULL AND TRIM(notes) <> ''")
    if search:
        keywords = [k.strip() for k in search.split(";") if k.strip()]
        if keywords:
            for kw in keywords:
                where.append("log_content LIKE ?")
                args.append(f"%{kw}%")
    query_where = " AND ".join(where)
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS c FROM logs WHERE {query_where}", args).fetchone()["c"]
        rows = conn.execute(
            f"""
            SELECT * FROM logs
            WHERE {query_where}
            ORDER BY printed_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            [*args, page_size, offset],
        ).fetchall()
        return {"items": [dict(r) for r in rows], "total": total}


def update_log_notes(system_id, log_id, notes):
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE logs SET notes=? WHERE id=? AND system_id=?",
            (notes, log_id, system_id),
        )
        conn.commit()
        return cur.rowcount > 0


def bulk_update_log_notes(system_id, log_ids, notes, append=False, only_empty=False):
    with get_conn() as conn:
        cur = conn.cursor()
        for log_id in log_ids:
            row = cur.execute(
                "SELECT notes FROM logs WHERE id=? AND system_id=?",
                (log_id, system_id),
            ).fetchone()
            if not row:
                continue
            old = row["notes"] or ""
            if only_empty and old.strip():
                continue
            value = f"{old}\n{notes}".strip() if append and old.strip() else notes
            cur.execute(
                "UPDATE logs SET notes=? WHERE id=? AND system_id=?",
                (value, log_id, system_id),
            )
        conn.commit()


def _fts5_delete_row(conn, log_id):
    """Contentless FTS5 forbids DELETE; remove one row by rowid.

    Use INSERT INTO logs_fts VALUES('delete', ?) — the (logs_fts) column form
    only accepts one value and breaks single-row deletes on SQLite 3.37+.
    """
    conn.execute("INSERT INTO logs_fts VALUES('delete', ?)", (log_id,))


def delete_log(system_id, log_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM logs WHERE id=? AND system_id=?",
            (log_id, system_id),
        ).fetchone()
        if not row:
            return False
        _fts5_delete_row(conn, log_id)
        conn.execute("DELETE FROM logs WHERE id=? AND system_id=?", (log_id, system_id))
        conn.commit()
        return True


def clear_logs(system_id):
    """Delete all locally collected logs for this system and resync FTS for remaining rows.

    Clears file_states for a clean slate; the log collector daemon does not rely on file_states
    (collection uses find -mmin + remote grep), so clearing logs does not break background collection.
    """
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM logs WHERE system_id=?", (system_id,)).fetchone()
        deleted = int(row["c"])
        conn.execute("DELETE FROM logs WHERE system_id=?", (system_id,))
        conn.execute("DELETE FROM file_states WHERE system_id=?", (system_id,))
        # Contentless FTS5: clear index then repopulate from surviving logs (other systems stay indexed).
        conn.execute("INSERT INTO logs_fts(logs_fts) VALUES('delete-all')")
        remaining = conn.execute(
            "SELECT id, log_content, file_path FROM logs ORDER BY id ASC"
        ).fetchall()
        if remaining:
            conn.executemany(
                "INSERT INTO logs_fts(rowid, log_content, file_path) VALUES (?, ?, ?)",
                [(r["id"], r["log_content"], r["file_path"]) for r in remaining],
            )
        conn.commit()
        return deleted


def dedupe_logs_by_content(system_id):
    with get_conn() as conn:
        # Fetch sorted in Python to avoid relying on ORDER BY inside GROUP_CONCAT
        # (that syntax requires SQLite ≥ 3.44 and silently misbehaves on older versions).
        rows = conn.execute(
            "SELECT id, log_content, notes FROM logs WHERE system_id=? ORDER BY id ASC",
            (system_id,),
        ).fetchall()

        groups: dict = {}
        for row in rows:
            groups.setdefault(row["log_content"], []).append((row["id"], row["notes"]))

        to_delete: list = []
        for entries in groups.values():
            if len(entries) <= 1:
                continue
            ids = [e[0] for e in entries]
            noted_ids = {e[0] for e in entries if e[1] and e[1].strip()}
            if noted_ids:
                to_delete.extend(i for i in ids if i not in noted_ids)
            else:
                to_delete.extend(ids[1:])

        if not to_delete:
            return 0

        placeholders = ",".join("?" * len(to_delete))
        conn.execute(f"DELETE FROM logs WHERE id IN ({placeholders})", to_delete)

        # Rebuild FTS: delete-all then repopulate from all surviving rows.
        # Per-row FTS deletes on a contentless table are unreliable; this matches
        # the pattern already used by clear_logs().
        conn.execute("INSERT INTO logs_fts(logs_fts) VALUES('delete-all')")
        remaining = conn.execute(
            "SELECT id, log_content, file_path FROM logs ORDER BY id ASC"
        ).fetchall()
        if remaining:
            conn.executemany(
                "INSERT INTO logs_fts(rowid, log_content, file_path) VALUES (?, ?, ?)",
                [(r["id"], r["log_content"], r["file_path"]) for r in remaining],
            )

        conn.commit()
        return len(to_delete)


def upsert_file_state(system_id, file_path, last_size, last_position, last_line_number, last_remote_mtime=None):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO file_states(system_id, file_path, last_size, last_position, last_line_number, last_remote_mtime, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(system_id, file_path) DO UPDATE SET
                last_size=excluded.last_size,
                last_position=excluded.last_position,
                last_line_number=excluded.last_line_number,
                last_remote_mtime=excluded.last_remote_mtime,
                last_updated=CURRENT_TIMESTAMP
            """,
            (system_id, file_path, last_size, last_position, last_line_number, last_remote_mtime),
        )
        conn.commit()


def get_file_state(system_id, file_path):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM file_states WHERE system_id=? AND file_path=?",
            (system_id, file_path),
        ).fetchone()
        return row_to_dict(row)


def _crud_simple(table, system_id, payload=None, row_id=None):
    with get_conn() as conn:
        cur = conn.cursor()
        if payload is None and row_id is None:
            rows = cur.execute(f"SELECT * FROM {table} WHERE system_id=? ORDER BY id ASC", (system_id,)).fetchall()
            return [dict(r) for r in rows]
        if payload is not None and row_id is None:
            keys = ",".join(payload.keys())
            marks = ",".join(["?"] * len(payload))
            values = list(payload.values())
            cur.execute(f"INSERT INTO {table}(system_id,{keys}) VALUES (?,{marks})", [system_id, *values])
            conn.commit()
            return cur.lastrowid
        if payload is not None and row_id is not None:
            set_sql = ",".join([f"{k}=?" for k in payload.keys()])
            cur.execute(
                f"UPDATE {table} SET {set_sql}, updated_at=CURRENT_TIMESTAMP WHERE id=? AND system_id=?",
                [*payload.values(), row_id, system_id],
            )
            conn.commit()
            return row_id
        cur.execute(f"DELETE FROM {table} WHERE id=? AND system_id=?", (row_id, system_id))
        conn.commit()
        return row_id


def list_search_configs(system_id):
    return _crud_simple("search_configs", system_id)


def create_search_config(system_id, payload):
    return _crud_simple("search_configs", system_id, payload=payload)


def update_search_config(system_id, cfg_id, payload):
    return _crud_simple("search_configs", system_id, payload=payload, row_id=cfg_id)


def delete_search_config(system_id, cfg_id):
    return _crud_simple("search_configs", system_id, row_id=cfg_id)


def list_log_views(system_id):
    return _crud_simple("log_views", system_id)


def create_log_view(system_id, payload):
    return _crud_simple("log_views", system_id, payload=payload)


def update_log_view(system_id, view_id, payload):
    return _crud_simple("log_views", system_id, payload=payload, row_id=view_id)


def delete_log_view(system_id, view_id):
    return _crud_simple("log_views", system_id, row_id=view_id)


def list_timeline_notes(view_id):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM log_view_timeline_notes WHERE view_id=? ORDER BY created_at DESC",
            (view_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def create_timeline_note(view_id, title, content, tags):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO log_view_timeline_notes(view_id, title, content, tags) VALUES (?, ?, ?, ?)",
            (view_id, title, content, json.dumps(tags or [])),
        )
        conn.commit()
        return cur.lastrowid


def update_timeline_note(note_id, payload):
    with get_conn() as conn:
        data = dict(payload)
        if "tags" in data and isinstance(data["tags"], list):
            data["tags"] = json.dumps(data["tags"])
        set_sql = ",".join([f"{k}=?" for k in data.keys()])
        conn.execute(
            f"UPDATE log_view_timeline_notes SET {set_sql}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            [*data.values(), note_id],
        )
        conn.commit()


def delete_timeline_note(note_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM log_view_timeline_notes WHERE id=?", (note_id,))
        conn.commit()


def list_shell_queries(system_id):
    return _crud_simple("shell_queries", system_id)


def create_shell_query(system_id, payload):
    return _crud_simple("shell_queries", system_id, payload=payload)


def update_shell_query(system_id, query_id, payload):
    return _crud_simple("shell_queries", system_id, payload=payload, row_id=query_id)


def delete_shell_query(system_id, query_id):
    with get_conn() as conn:
        c = conn.execute("SELECT COUNT(*) AS c FROM shell_queries WHERE system_id=?", (system_id,)).fetchone()["c"]
        if int(c) <= 1:
            raise ValueError("至少保留一个 Shell 查询任务")
    return _crud_simple("shell_queries", system_id, row_id=query_id)


def add_shell_query_history(query_id, full_output, is_different, diff_lines):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO shell_query_history(query_id, full_output, is_different, diff_lines_json)
            VALUES (?, ?, ?, ?)
            """,
            (query_id, full_output, 1 if is_different else 0, json.dumps(diff_lines)),
        )
        conn.commit()
        return cur.lastrowid


def list_shell_query_history(query_id):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM shell_query_history WHERE query_id=? ORDER BY executed_at DESC, id DESC",
            (query_id,),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["diff_lines_json"] = json.loads(item["diff_lines_json"] or "[]")
            result.append(item)
        return result


def delete_shell_query_history(history_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM shell_query_history WHERE id=?", (history_id,))
        conn.commit()
