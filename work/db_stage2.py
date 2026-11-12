"""SQLite storage for the anonymous heart wall."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator


DB_PATH = Path(__file__).resolve().parent / "heart_wall.db"
MAX_CONTENT_LENGTH = 3000


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    """Commit successful writes, roll back failed writes, and always close."""
    connection = sqlite3.connect(DB_PATH, timeout=10)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            yield connection
    finally:
        connection.close()


def init_db() -> None:
    """Create the three tables and indexes without deleting existing data."""
    with _connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL CHECK (length(trim(content)) > 0),
                category TEXT,
                intensity INTEGER,
                ai_reply TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'rejected', 'crisis')),
                consent_public INTEGER NOT NULL DEFAULT 0
                    CHECK (consent_public IN (0, 1)),
                created_at TEXT NOT NULL
                    DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
                content TEXT NOT NULL CHECK (length(trim(content)) > 0),
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'rejected')),
                created_at TEXT NOT NULL
                    DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS reactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
                type TEXT NOT NULL
                    CHECK (type IN ('understand', 'hug', 'metoo', 'worried')),
                created_at TEXT NOT NULL
                    DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE INDEX IF NOT EXISTS idx_posts_public_wall
                ON posts(status, consent_public, created_at DESC, id DESC);
            CREATE INDEX IF NOT EXISTS idx_replies_post_id ON replies(post_id);
            CREATE INDEX IF NOT EXISTS idx_reactions_post_id ON reactions(post_id);
            """
        )


def create_post(
    content: str,
    consent_public: bool,
    *,
    category: str | None = None,
    intensity: int | None = None,
    ai_reply: str | None = None,
    status: str = "pending",
) -> int:
    """Atomically save a post with optional AI analysis; never auto-approve."""
    if not isinstance(content, str):
        raise ValueError("心声内容必须是文字。")
    content = content.strip()
    if not content:
        raise ValueError("请先写下一点心声，再提交。")
    if len(content) > MAX_CONTENT_LENGTH:
        raise ValueError(f"心声最多支持 {MAX_CONTENT_LENGTH} 个字符。")
    if not isinstance(consent_public, bool):
        raise ValueError("公开同意选项必须是勾选或未勾选。")
    if category is not None and category not in ("学业", "家庭", "社交", "情绪"):
        raise ValueError("心声分类无效。")
    if intensity is not None and (
        type(intensity) is not int or not 1 <= intensity <= 5
    ):
        raise ValueError("心声强度必须是 1 到 5 的整数。")
    if ai_reply is not None and (
        not isinstance(ai_reply, str) or not ai_reply.strip()
    ):
        raise ValueError("AI 回应不能为空。")
    if status not in ("pending", "crisis"):
        raise ValueError("新心声必须等待人工审核或安全关注。")

    with _connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO posts (
                content, category, intensity, ai_reply, status, consent_public
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (content, category, intensity, ai_reply, status, int(consent_public)),
        )
        return int(cursor.lastrowid)


def get_approved_posts() -> list[sqlite3.Row]:
    """Only return approved posts whose authors consented to publication."""
    with _connection() as connection:
        return connection.execute(
            """
            SELECT id, content, created_at
            FROM posts
            WHERE status = 'approved' AND consent_public = 1
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()


if __name__ == "__main__":
    init_db()
    print(f"Database ready: {DB_PATH}")
