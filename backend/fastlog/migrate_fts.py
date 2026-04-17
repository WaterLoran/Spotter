import sqlite3

from config import MAIN_DB_PATH


def run():
    conn = sqlite3.connect(MAIN_DB_PATH)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS logs_fts
            USING fts5(log_content, file_path, content='');
            """
        )
        rows = conn.execute("SELECT id, log_content, file_path FROM logs").fetchall()
        conn.execute("INSERT INTO logs_fts(logs_fts) VALUES('delete-all')")
        conn.executemany(
            "INSERT INTO logs_fts(rowid, log_content, file_path) VALUES (?, ?, ?)",
            rows,
        )
        conn.commit()
        print(f"migrated rows: {len(rows)}")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
