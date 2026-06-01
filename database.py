import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

_BASE = Path("/app/data") if Path("/app/data").exists() else Path(".")
DB_PATH = _BASE / "styleverse.db"

FREE_LIMIT = 3
SUB_LIMIT = 20


def _conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    with _conn() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id            INTEGER PRIMARY KEY,
                username           TEXT,
                full_name          TEXT,
                joined_at          TEXT DEFAULT (datetime('now')),
                gen_count          INTEGER DEFAULT 0,
                status             TEXT DEFAULT 'active',
                subscription_until TEXT DEFAULT NULL,
                sub_gens_used      INTEGER DEFAULT 0
            )
        """)
        for col, definition in [
            ("subscription_until", "TEXT DEFAULT NULL"),
            ("sub_gens_used",      "INTEGER DEFAULT 0"),
        ]:
            try:
                db.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
            except Exception:
                pass


def register_user(user_id: int, username: str | None, full_name: str):
    with _conn() as db:
        db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
            (user_id, username, full_name),
        )


def increment_generation(user_id: int):
    with _conn() as db:
        db.execute(
            "UPDATE users SET gen_count = gen_count + 1, sub_gens_used = sub_gens_used + 1 WHERE user_id = ?",
            (user_id,),
        )


def get_user(user_id: int) -> tuple | None:
    with _conn() as db:
        return db.execute(
            "SELECT user_id, username, full_name, joined_at, gen_count, status, subscription_until, sub_gens_used "
            "FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()


def get_users(limit: int = 10, offset: int = 0) -> list[tuple]:
    with _conn() as db:
        return db.execute(
            "SELECT user_id, username, full_name, joined_at, gen_count, status "
            "FROM users ORDER BY joined_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()


def set_status(user_id: int, status: str):
    with _conn() as db:
        if status == "active":
            db.execute(
                "UPDATE users SET status = ?, subscription_until = NULL, sub_gens_used = 0 WHERE user_id = ?",
                (status, user_id),
            )
        else:
            db.execute("UPDATE users SET status = ? WHERE user_id = ?", (status, user_id))


def set_vip(user_id: int):
    with _conn() as db:
        db.execute(
            "UPDATE users SET status = 'vip', subscription_until = NULL WHERE user_id = ?",
            (user_id,),
        )


def activate_subscription(user_id: int, days: int = 30) -> str:
    until = (datetime.utcnow() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as db:
        db.execute(
            "UPDATE users SET status = 'vip', subscription_until = ?, sub_gens_used = 0 WHERE user_id = ?",
            (until, user_id),
        )
    return until


def get_stats() -> dict:
    with _conn() as db:
        total  = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        today  = db.execute("SELECT COUNT(*) FROM users WHERE date(joined_at) = date('now')").fetchone()[0]
        gens   = db.execute("SELECT COALESCE(SUM(gen_count), 0) FROM users").fetchone()[0]
        vip    = db.execute("SELECT COUNT(*) FROM users WHERE status = 'vip'").fetchone()[0]
        banned = db.execute("SELECT COUNT(*) FROM users WHERE status = 'banned'").fetchone()[0]
        subs   = db.execute(
            "SELECT COUNT(*) FROM users WHERE status = 'vip' AND subscription_until IS NOT NULL "
            "AND subscription_until > datetime('now')"
        ).fetchone()[0]
    return {"total": total, "today": today, "generations": gens, "vip": vip, "banned": banned, "subs": subs}


def is_banned(user_id: int) -> bool:
    with _conn() as db:
        row = db.execute("SELECT status FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return bool(row and row[0] == "banned")


def get_generation_status(user_id: int) -> str | None:
    """Returns a counter string to show after generation, or None for VIP unlimited."""
    row = get_user(user_id)
    if not row:
        return None
    _, _, _, _, gen_count, status, subscription_until, sub_gens_used = row
    if status == "vip" and not subscription_until:
        return None  # безлимитный VIP — не показываем
    if status == "vip" and subscription_until:
        remaining = SUB_LIMIT - sub_gens_used
        return f"Использовано {sub_gens_used} из {SUB_LIMIT} генераций в этом месяце"
    remaining = FREE_LIMIT - gen_count
    if remaining > 0:
        return f"Использовано {gen_count} из {FREE_LIMIT} бесплатных генераций"
    return None


def check_generation_access(user_id: int) -> tuple[bool, str]:
    row = get_user(user_id)
    if not row:
        return False, "not_found"

    _, _, _, _, gen_count, status, subscription_until, sub_gens_used = row

    if status == "banned":
        return False, "banned"

    if status == "vip":
        if not subscription_until:
            return True, "ok"  # безлимитный VIP
        until = datetime.strptime(subscription_until, "%Y-%m-%d %H:%M:%S")
        if datetime.utcnow() > until:
            with _conn() as db:
                db.execute("UPDATE users SET status = 'active' WHERE user_id = ?", (user_id,))
            return False, "sub_expired"
        if sub_gens_used >= SUB_LIMIT:
            return False, "sub_limit"
        return True, "ok"

    if gen_count >= FREE_LIMIT:
        return False, "free_limit"

    return True, "ok"
