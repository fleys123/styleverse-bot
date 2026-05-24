import sqlite3
from pathlib import Path

_BASE = Path("/app/data") if Path("/app/data").exists() else Path(".")
DB_PATH = _BASE / "styleverse.db"


def _conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    with _conn() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id      INTEGER PRIMARY KEY,
                username     TEXT,
                full_name    TEXT,
                joined_at    TEXT DEFAULT (datetime('now')),
                gen_count    INTEGER DEFAULT 0,
                status       TEXT DEFAULT 'active'
            )
        """)


def register_user(user_id: int, username: str | None, full_name: str):
    with _conn() as db:
        db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
            (user_id, username, full_name),
        )


def increment_generation(user_id: int):
    with _conn() as db:
        db.execute(
            "UPDATE users SET gen_count = gen_count + 1 WHERE user_id = ?",
            (user_id,),
        )


def get_user(user_id: int) -> tuple | None:
    with _conn() as db:
        return db.execute(
            "SELECT user_id, username, full_name, joined_at, gen_count, status FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()


def get_users(limit: int = 10, offset: int = 0) -> list[tuple]:
    with _conn() as db:
        return db.execute(
            "SELECT user_id, username, full_name, joined_at, gen_count, status FROM users ORDER BY joined_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()


def set_status(user_id: int, status: str):
    with _conn() as db:
        db.execute("UPDATE users SET status = ? WHERE user_id = ?", (status, user_id))


def get_stats() -> dict:
    with _conn() as db:
        total = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        today = db.execute("SELECT COUNT(*) FROM users WHERE date(joined_at) = date('now')").fetchone()[0]
        gens = db.execute("SELECT COALESCE(SUM(gen_count), 0) FROM users").fetchone()[0]
        vip = db.execute("SELECT COUNT(*) FROM users WHERE status = 'vip'").fetchone()[0]
        banned = db.execute("SELECT COUNT(*) FROM users WHERE status = 'banned'").fetchone()[0]
    return {"total": total, "today": today, "generations": gens, "vip": vip, "banned": banned}


def is_banned(user_id: int) -> bool:
    with _conn() as db:
        row = db.execute("SELECT status FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return bool(row and row[0] == "banned")
