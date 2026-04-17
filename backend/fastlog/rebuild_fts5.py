import sqlite3

from config import MAIN_DB_PATH


def run():
    conn = sqlite3.connect(MAIN_DB_PATH)
    try:
        conn.execute("DROP TABLE IF EXISTS logs_fts;")
        conn.execute(
            """
            CREATE VIRTUAL TABLE logs_fts
            USING fts5(log_content, file_path, content='');
            """
        )
        rows = conn.execute("SELECT id, log_content, file_path FROM logs").fetchall()
        conn.executemany(
            "INSERT INTO logs_fts(rowid, log_content, file_path) VALUES (?, ?, ?)",
            rows,
        )
        conn.commit()
        print(f"rebuilt rows: {len(rows)}")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
