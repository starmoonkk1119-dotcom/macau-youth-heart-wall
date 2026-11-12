"""SQLite storage for the anonymous heart wall."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator


DB_PATH = Path(__file__).resolve().parent / "heart_wall.db"
MAX_CONTENT_LENGTH = 3000
REACTION_TYPES = ("understand", "hug", "metoo", "worried")
CRISIS_CONDITION = """
    (intensity >= 4 OR (
        SELECT COUNT(*) FROM reactions
        WHERE reactions.post_id = posts.id AND type = 'worried'
    ) >= 3)
"""


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
            CREATE INDEX IF NOT EXISTS idx_reactions_post_type
                ON reactions(post_id, type);
            """
        )
        # Upgrade existing phase 2 risks once, not after every manual approval.
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute("PRAGMA user_version").fetchone()[0] < 1:
            connection.execute(
                f"""
                UPDATE posts SET status = 'crisis'
                WHERE status IN ('pending', 'approved') AND {CRISIS_CONDITION}
                """
            )
            connection.execute("PRAGMA user_version = 1")


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
        post_id = int(cursor.lastrowid)
        escalate_crisis_if_needed(post_id, connection=connection)
        return post_id


def escalate_crisis_if_needed(
    post_id: int, *, connection: sqlite3.Connection | None = None
) -> bool:
    """Escalate pending/public posts; return whether the post is now crisis."""
    if connection is None:
        with _connection() as connection:
            return escalate_crisis_if_needed(post_id, connection=connection)
    connection.execute(
        f"""
        UPDATE posts SET status = 'crisis'
        WHERE id = ? AND status IN ('pending', 'approved')
          AND {CRISIS_CONDITION}
        """,
        (post_id,),
    )
    row = connection.execute(
        "SELECT status FROM posts WHERE id = ?", (post_id,)
    ).fetchone()
    return row is not None and row["status"] == "crisis"


def get_approved_posts() -> list[sqlite3.Row]:
    """Only return approved posts whose authors consented to publication."""
    with _connection() as connection:
        return connection.execute(
            """
            SELECT id, content, category, intensity, created_at
            FROM posts
            WHERE status = 'approved' AND consent_public = 1
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()


def get_reaction_counts(post_id: int) -> dict[str, int]:
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT type, COUNT(*) AS count FROM reactions
            WHERE post_id = ? GROUP BY type
            """,
            (post_id,),
        ).fetchall()
    counts = dict.fromkeys(REACTION_TYPES, 0)
    counts.update({row["type"]: row["count"] for row in rows})
    return counts


def _require_public_post(connection: sqlite3.Connection, post_id: int) -> None:
    row = connection.execute(
        """
        SELECT id FROM posts
        WHERE id = ? AND status = 'approved' AND consent_public = 1
        """,
        (post_id,),
    ).fetchone()
    if row is None:
        raise ValueError("这条心声已不在公开墙上，请刷新页面。")


def add_reaction(post_id: int, reaction_type: str) -> bool:
    """Insert and check escalation in one transaction; return crisis status."""
    if reaction_type not in REACTION_TYPES:
        raise ValueError("无效的关怀类型。")
    with _connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        _require_public_post(connection, post_id)
        connection.execute(
            "INSERT INTO reactions(post_id, type) VALUES (?, ?)",
            (post_id, reaction_type),
        )
        return escalate_crisis_if_needed(post_id, connection=connection)


def create_reply(
    post_id: int, content: str, *, moderation: str = "need_review"
) -> int:
    """All replies wait for review, including replies flagged by the AI."""
    if not isinstance(content, str) or not content.strip():
        raise ValueError("请先写下一点安慰，再提交。")
    content = content.strip()
    if len(content) > MAX_CONTENT_LENGTH:
        raise ValueError(f"回复最多支持 {MAX_CONTENT_LENGTH} 个字符。")
    if moderation not in ("safe", "need_review", "crisis"):
        raise ValueError("回复审核结果无效。")
    with _connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        _require_public_post(connection, post_id)
        cursor = connection.execute(
            """
            INSERT INTO replies(post_id, content, status)
            VALUES (?, ?, 'pending')
            """,
            (post_id, content),
        )
        if moderation == "crisis":
            connection.execute(
                "UPDATE posts SET status = 'crisis' WHERE id = ?", (post_id,)
            )
        return int(cursor.lastrowid)


def get_approved_replies(post_id: int) -> list[sqlite3.Row]:
    with _connection() as connection:
        return connection.execute(
            """
            SELECT r.id, r.content, r.created_at
            FROM replies AS r JOIN posts AS p ON p.id = r.post_id
            WHERE r.post_id = ? AND r.status = 'approved'
              AND p.status = 'approved' AND p.consent_public = 1
            ORDER BY r.created_at, r.id
            """,
            (post_id,),
        ).fetchall()


def get_review_posts() -> list[sqlite3.Row]:
    with _connection() as connection:
        return connection.execute(
            """
            SELECT * FROM posts WHERE status IN ('pending', 'crisis')
            ORDER BY CASE WHEN status = 'crisis' THEN 0 ELSE 1 END,
                     created_at, id
            """
        ).fetchall()


def get_review_replies() -> list[sqlite3.Row]:
    with _connection() as connection:
        return connection.execute(
            """
            SELECT r.*, p.content AS post_content, p.status AS post_status
            FROM replies AS r JOIN posts AS p ON p.id = r.post_id
            WHERE r.status = 'pending'
            ORDER BY CASE WHEN p.status = 'crisis' THEN 0 ELSE 1 END,
                     r.created_at, r.id
            """
        ).fetchall()


def review_item(kind: str, item_id: int, new_status: str) -> bool:
    """Only change items still in the queue, protecting against stale views."""
    table = {"post": "posts", "reply": "replies"}.get(kind)
    if table is None or new_status not in ("approved", "rejected"):
        raise ValueError("无效的审核操作。")
    with _connection() as connection:
        cursor = connection.execute(
            f"""
            UPDATE {table} SET status = ?
            WHERE id = ? AND status IN ('pending', 'crisis')
            """,
            (new_status, item_id),
        )
        return cursor.rowcount == 1


def seed_demo_posts(demo_posts: list[dict], *, reset: bool = False) -> dict[str, int]:
    """Seed only explicitly marked fixtures, atomically and without duplicates."""
    if not demo_posts:
        raise ValueError("示例数据不能为空。")
    contents = []
    for post in demo_posts:
        content = post["content"]
        if not content.startswith("[DEMO 示例 ") or len(content) > MAX_CONTENT_LENGTH:
            raise ValueError("种子帖子必须明确标记为 DEMO 示例。")
        if post["category"] not in ("学业", "家庭", "社交", "情绪"):
            raise ValueError("示例分类无效。")
        if type(post["intensity"]) is not int or not 1 <= post["intensity"] <= 5:
            raise ValueError("示例强度无效。")
        if post["status"] not in ("pending", "approved", "crisis"):
            raise ValueError("示例状态无效。")
        if type(post["consent_public"]) is not bool:
            raise ValueError("示例公开选项无效。")
        if not post["ai_reply"].startswith("[DEMO 预设回应]"):
            raise ValueError("示例回应必须注明为预设内容。")
        for reply in post.get("replies", []):
            if (
                not reply["content"].startswith("[DEMO 示例回复 ")
                or len(reply["content"]) > MAX_CONTENT_LENGTH
                or reply["status"] not in ("pending", "approved", "rejected")
            ):
                raise ValueError("示例回复格式无效。")
        contents.append(content)
    if len(contents) != len(set(contents)):
        raise ValueError("示例帖子内容不能重复。")
    summary = {
        "posts_created": 0, "posts_skipped": 0, "posts_removed": 0,
        "replies_created": 0, "replies_skipped": 0,
    }
    with _connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        if reset:
            placeholders = ",".join("?" for _ in contents)
            cursor = connection.execute(
                f"DELETE FROM posts WHERE content IN ({placeholders})", contents
            )
            summary["posts_removed"] = cursor.rowcount
        for post in demo_posts:
            existing = connection.execute(
                "SELECT id FROM posts WHERE content = ? ORDER BY id LIMIT 1",
                (post["content"],),
            ).fetchone()
            if existing is None:
                cursor = connection.execute(
                    """
                    INSERT INTO posts (
                        content, category, intensity, ai_reply, status, consent_public
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        post["content"], post["category"], post["intensity"],
                        post["ai_reply"], post["status"], int(post["consent_public"]),
                    ),
                )
                post_id = int(cursor.lastrowid)
                escalate_crisis_if_needed(post_id, connection=connection)
                summary["posts_created"] += 1
            else:
                post_id = existing["id"]
                summary["posts_skipped"] += 1
            for reply in post.get("replies", []):
                existing_reply = connection.execute(
                    "SELECT id FROM replies WHERE post_id = ? AND content = ?",
                    (post_id, reply["content"]),
                ).fetchone()
                if existing_reply is not None:
                    summary["replies_skipped"] += 1
                    continue
                connection.execute(
                    "INSERT INTO replies(post_id, content, status) VALUES (?, ?, ?)",
                    (post_id, reply["content"], reply["status"]),
                )
                summary["replies_created"] += 1
    return summary


if __name__ == "__main__":
    init_db()
    print(f"Database ready: {DB_PATH}")
