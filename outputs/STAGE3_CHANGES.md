# 第 3 阶段：完整新增代码与插入位置

本项目已经直接更新，无需再次粘贴代码。下面是可逐项核对的代码。
只修改 `app.py`、`db.py`；`ai.py` 和 `requirements.txt` 不变。数据库仍是原有三张表，保留已有数据。

## 1. app.py 导入区

将原导入区替换为以下内容，保留文件开头的模块说明：


```python
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import sqlite3
import streamlit as st
from ai import analyze_post, normalize_text
from db import (
    MAX_CONTENT_LENGTH,
    add_reaction,
    create_post,
    create_reply,
    get_approved_posts,
    get_approved_replies,
    get_reaction_counts,
    get_review_posts,
    get_review_replies,
    init_db,
    review_item,
)
```

## 2. app.py 常量与求助框

放在导入区之后、`write_post_page()` 之前，替换原有 `MACAU_TIMEZONE` 定义。


```python
MACAU_TIMEZONE = timezone(timedelta(hours=8))


HELP_RESOURCES = (
    "如果你现在很难受，请联系澳门明爱生命热线 28525222，"
    "或向信任的大人/学校社工求助。你并不孤单。"
)


REACTION_LABELS = (
    ("understand", "我懂你"),
    ("hug", "抱抱"),
    ("metoo", "我也是"),
    ("worried", "我有点担心你"),
)


def show_help_resources() -> None:
    st.error(HELP_RESOURCES)


def format_time(value: str) -> str:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        MACAU_TIMEZONE
    ).strftime("%Y-%m-%d %H:%M")
```

## 3. app.py 发帖成功页

用下面的函数替换原 `write_post_page()`。AI 判为危机或强度达到 4，都使用 `crisis` 状态，成功页显示原样求助资源。


```python
def write_post_page() -> None:
    st.title("写心声")
    st.caption(
        "提交后，正文将发送至 DeepSeek 进行 AI 分析。"
        "请勿填写真实姓名、学校、电话或其他可识别身份的信息。"
    )

    receipt = st.session_state.pop("_post_receipt", None)
    if receipt is not None:
        # Reset form widgets before rendering them, and only after a saved post.
        st.session_state["draft_content"] = ""
        st.session_state["consent_public"] = False
        st.success(f"提交成功，心声编号 #{receipt['id']}，尚未公开。")
        if receipt["status"] == "crisis":
            st.warning(
                "这条心声需要优先安全关注，不会公开。"
                "本网站不是实时求助渠道，不能保证有人即时查看。"
            )
            show_help_resources()
        else:
            st.caption("当前状态：待人工审核。")
        with st.container(border=True):
            st.caption("AI 陪伴回应")
            st.text(receipt["ai_reply"])
        if not receipt["consent_public"]:
            st.caption("你没有同意匿名公开，这条心声不会展示在心声墙上。")

    with st.form("new_post", clear_on_submit=False):
        content = st.text_area(
            "此刻，你想说些什么？",
            height=200,
            max_chars=MAX_CONTENT_LENGTH,
            key="draft_content",
        )
        consent_public = st.checkbox("同意匿名公开", key="consent_public")
        submitted = st.form_submit_button("提交心声", type="primary")

    if submitted:
        try:
            if not normalize_text(content):
                raise ValueError("请先写下一点心声，再提交。")
            if len(content.strip()) > MAX_CONTENT_LENGTH:
                raise ValueError(f"心声最多支持 {MAX_CONTENT_LENGTH} 个字符。")
            with st.spinner("正在接住你的心声……"):
                analysis = analyze_post(content)
                status = (
                    "crisis"
                    if analysis["moderation"] == "crisis" or analysis["intensity"] >= 4
                    else "pending"
                )
                post_id = create_post(
                    content, consent_public,
                    category=analysis["category"],
                    intensity=analysis["intensity"],
                    ai_reply=analysis["ai_reply"],
                    status=status,
                )
        except ValueError as error:
            st.error(str(error))
        except sqlite3.Error:
            st.error("暂时无法保存心声，文字已保留在输入框中，请稍后重试。")
        else:
            st.session_state["_post_receipt"] = {
                "id": post_id,
                "consent_public": consent_public,
                "status": status,
                "ai_reply": analysis["ai_reply"],
            }
            st.rerun()
```

## 4. app.py 心声墙

删除旧 `wall_page()`，在原位置放入下面三个函数。每次 interaction 会检查帖子是否仍已通过且同意公开。所有回复先调用现有 `analyze_post()`，保存后仍为 `pending`，不会自动公开。


```python
def reaction_buttons(post_id: int, counts: dict[str, int]) -> None:
    for offset in (0, 2):
        columns = st.columns(2)
        for column, (reaction_type, label) in zip(
            columns, REACTION_LABELS[offset:offset + 2]
        ):
            if column.button(
                f"{label} · {counts[reaction_type]}",
                key=f"reaction_{post_id}_{reaction_type}",
                use_container_width=True,
            ):
                try:
                    crisis = add_reaction(post_id, reaction_type)
                    st.session_state["_wall_notice"] = {
                        "message": (
                            f"心声 #{post_id} 已转入优先安全关注，暂时退出公开墙。"
                            if crisis else f"已为心声 #{post_id} 留下一份关怀。"
                        ),
                        "help": crisis,
                    }
                except (ValueError, sqlite3.Error):
                    st.session_state["_wall_notice"] = {
                        "message": "关怀暂未保存，帖子可能已退出公开墙，请刷新后重试。",
                        "error": True,
                    }
                st.rerun()


def reply_form(post_id: int) -> None:
    draft_key = f"reply_draft_{post_id}"
    with st.form(f"reply_form_{post_id}", clear_on_submit=False, border=False):
        content = st.text_area(
            "留下一点安慰",
            key=draft_key,
            max_chars=MAX_CONTENT_LENGTH,
            height=100,
        )
        submitted = st.form_submit_button("提交回复")
    if submitted:
        try:
            if not normalize_text(content):
                raise ValueError("请先写下一点安慰，再提交。")
            if len(content.strip()) > MAX_CONTENT_LENGTH:
                raise ValueError(f"回复最多支持 {MAX_CONTENT_LENGTH} 个字符。")
            with st.spinner("正在检查回复……"):
                analysis = analyze_post(content)
                create_reply(post_id, content, moderation=analysis["moderation"])
        except ValueError as error:
            st.error(str(error))
        except sqlite3.Error:
            st.error("暂时无法保存回复，输入已保留，请稍后重试。")
        else:
            st.session_state["_clear_reply_draft"] = draft_key
            st.session_state["_wall_notice"] = {
                "message": f"心声 #{post_id} 的回复已提交，等待人工审核，尚未公开。",
                "help": analysis["moderation"] == "crisis",
            }
            st.rerun()


def wall_page() -> None:
    st.title("心声墙")
    st.caption(
        "每一份感受，都值得被认真对待。"
        "回复正文将发送至 DeepSeek 分析，请勿填写身份信息。"
    )
    clear_key = st.session_state.pop("_clear_reply_draft", None)
    if clear_key:
        st.session_state[clear_key] = ""
    notice = st.session_state.pop("_wall_notice", None)
    if notice:
        if notice.get("error"):
            st.error(notice["message"])
        else:
            st.success(notice["message"])
        if notice.get("help"):
            show_help_resources()
            st.caption("本网站不是实时求助渠道，不能保证有人即时查看。")
    try:
        posts = get_approved_posts()
        if not posts:
            st.info("心声墙暂时还没有可以公开的心声。")
        for post in posts:
            counts = get_reaction_counts(post["id"])
            replies = get_approved_replies(post["id"])
            with st.container(border=True):
                st.caption(
                    f"匿名心声 #{post['id']} · "
                    f"{format_time(post['created_at'])}（澳门时间）"
                )
                st.text(post["content"])
                if (post["intensity"] or 0) >= 4 or counts["worried"] >= 3:
                    show_help_resources()
                reaction_buttons(post["id"], counts)
                st.divider()
                for reply in replies:
                    st.caption(
                        f"匿名回复 #{reply['id']} · "
                        f"{format_time(reply['created_at'])}（澳门时间）"
                    )
                    st.text(reply["content"])
                if not replies:
                    st.caption("还没有已通过的回复。")
                reply_form(post["id"])
    except sqlite3.Error:
        st.error("暂时无法读取心声或回复，请稍后重试。")
```

## 5. app.py 管理员页面

放在新的 `wall_page()` 之后、`main()` 之前。未配置 `ADMIN_PASS`、未登录或密码错误时，都不读取或显示审核队列。


```python
def admin_authenticated() -> bool:
    expected = os.environ.get("ADMIN_PASS", "")
    token = st.session_state.get("_admin_token")
    return (
        bool(expected.strip())
        and isinstance(token, bytes)
        and hmac.compare_digest(
            token, hashlib.sha256(expected.encode("utf-8")).digest()
        )
    )


def check_admin_password() -> None:
    entered = st.session_state.pop("admin_password", "")
    expected = os.environ.get("ADMIN_PASS", "")
    if expected.strip() and hmac.compare_digest(
        entered.encode("utf-8"), expected.encode("utf-8")
    ):
        st.session_state["_admin_token"] = hashlib.sha256(
            expected.encode("utf-8")
        ).digest()
        st.session_state.pop("_admin_login_error", None)
    else:
        st.session_state.pop("_admin_token", None)
        st.session_state["_admin_login_error"] = True


def logout_admin() -> None:
    for key in ("_admin_token", "_admin_login_error", "_admin_notice"):
        st.session_state.pop(key, None)


def review_buttons(kind: str, item_id: int) -> None:
    columns = st.columns(2)
    approved = columns[0].button(
        "通过", key=f"approve_{kind}_{item_id}", type="primary"
    )
    rejected = columns[1].button("退回", key=f"reject_{kind}_{item_id}")
    if approved or rejected:
        if not admin_authenticated():
            st.error("管理员登录已失效，请重新登录。")
            return
        try:
            changed = review_item(
                kind, item_id, "approved" if approved else "rejected"
            )
            st.session_state["_admin_notice"] = {
                "message": "审核结果已保存。" if changed else "该内容已被处理，请查看最新队列。"
            }
        except (ValueError, sqlite3.Error):
            st.session_state["_admin_notice"] = {
                "message": "审核结果暂未保存，请稍后重试。",
                "error": True,
            }
        st.rerun()


def admin_page() -> None:
    st.title("管理员")
    if not os.environ.get("ADMIN_PASS", "").strip():
        logout_admin()
        st.warning("尚未配置 ADMIN_PASS，管理员入口已关闭。")
        return
    if not admin_authenticated():
        st.session_state.pop("_admin_token", None)
        with st.form("admin_login"):
            st.text_input("管理员密码", type="password", key="admin_password")
            st.form_submit_button("登录", on_click=check_admin_password)
        if st.session_state.get("_admin_login_error"):
            st.error("密码不正确，请重试。")
        return

    columns = st.columns(2)
    if columns[0].button("刷新队列", key="refresh_admin"):
        st.rerun()
    columns[1].button("退出登录", key="logout_admin", on_click=logout_admin)
    notice = st.session_state.pop("_admin_notice", None)
    if notice:
        if notice.get("error"):
            st.error(notice["message"])
        else:
            st.success(notice["message"])
    try:
        posts = get_review_posts()
        replies = get_review_replies()
    except sqlite3.Error:
        st.error("暂时无法读取审核队列，请稍后重试。")
        return

    st.subheader(f"待审核心声 · {len(posts)}")
    if not posts:
        st.info("暂时没有待审核心声。")
    for post in posts:
        with st.container(border=True):
            st.caption(
                f"心声 #{post['id']} · {format_time(post['created_at'])}（澳门时间）"
            )
            if post["status"] == "crisis":
                st.error("危机 · 优先安全关注")
                show_help_resources()
            else:
                st.caption("待人工审核")
            st.text(post["content"])
            st.caption(
                f"分类：{post['category'] or '未分类'} · "
                f"AI 参考强度：{post['intensity'] or '未评估'} · "
                f"同意公开：{'是' if post['consent_public'] else '否'}"
            )
            if post["ai_reply"]:
                st.caption("AI 陪伴回应")
                st.text(post["ai_reply"])
            review_buttons("post", post["id"])

    st.subheader(f"待审核回复 · {len(replies)}")
    if not replies:
        st.info("暂时没有待审核回复。")
    for reply in replies:
        with st.container(border=True):
            st.caption(
                f"回复 #{reply['id']} → 心声 #{reply['post_id']} · "
                f"{format_time(reply['created_at'])}（澳门时间）"
            )
            if reply["post_status"] == "crisis":
                st.error("所属心声需要优先安全关注")
            st.caption("所属心声")
            st.text(reply["post_content"])
            st.caption("待审核回复")
            st.text(reply["content"])
            review_buttons("reply", reply["id"])
```

## 6. app.py 导航

用下面函数替换原 `main()`；文件底部的入口调用不变。


```python
def main() -> None:
    st.set_page_config(page_title="心声墙 | 澳门青少年", layout="centered")
    try:
        init_db()
    except sqlite3.Error:
        st.error("数据库初始化失败，请检查项目文件夹是否可写后重试。")
        st.stop()

    with st.sidebar:
        st.title("心声墙")
        st.caption("澳门青少年 · 匿名心声")
        page = st.radio(
            "导航", ("写心声", "心声墙", "管理员"), label_visibility="collapsed"
        )
        st.divider()
        st.caption("请保护自己和他人的隐私。")

    if page == "写心声":
        write_post_page()
    elif page == "心声墙":
        wall_page()
    else:
        admin_page()
```

## 7. db.py 配套更新与危机预警函数

数据库操作继续集中在 `db.py`。在 `MAX_CONTENT_LENGTH` 后增加以下常量：


```python
REACTION_TYPES = ("understand", "hug", "metoo", "worried")


CRISIS_CONDITION = """
    (intensity >= 4 OR (
        SELECT COUNT(*) FROM reactions
        WHERE reactions.post_id = posts.id AND type = 'worried'
    ) >= 3)
"""
```

替换原 `init_db()`、`create_post()`、`get_approved_posts()`，并在 `if __name__ == '__main__':` 入口之前增加其余函数。保留原有导入、`DB_PATH`、`MAX_CONTENT_LENGTH`、`_connection()`。


```python
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
            SELECT id, content, intensity, created_at
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
```

## 8. 环境变量与启动

在 `outputs` 文件夹、已激活虚拟环境的终端设置密码后再启动。如果服务已经运行，先 Ctrl+C 停止，再设置变量并重新启动。不要使用示例文字作为真实管理员密码。

Mac：


```bash
export ADMIN_PASS="替换为足够长的管理员密码"
export DEEPSEEK_API_KEY="你的DeepSeek密钥"
streamlit run app.py
```

Windows PowerShell：


```powershell
$env:ADMIN_PASS="替换为足够长的管理员密码"
$env:DEEPSEEK_API_KEY="你的DeepSeek密钥"
streamlit run app.py
```

## 9. 验证与状态边界

1. 普通心声提交后为 pending；管理员通过后，只有同意公开的帖子出现在墙上。
2. 高强度或 AI 危机帖直接进入 crisis 队列，标红并显示求助框。
3. 对公开帖累计点击三次“我有点担心你”，帖子转为 crisis 并退出公开墙；触发者页面显示该帖编号与求助资源。
4. 提交回复后，它只出现在人工队列；通过后公开，退回后不显示。
5. AI 判为 crisis 的回复本身仍为 pending，同时让所属帖子转为 crisis。
6. 人工通过已有风险的帖子后，不会因读取页面而反复升级；风险条件仍在时，公开帖保留求助框，后续关怀写入会重新检查阈值。
7. 历史风险只做一次迁移；已退回的帖子不会自动复活。
8. reaction 是累计点击次数，不是独立人数；此阶段没有跨会话防刷。简单共享密码只适合原型演示，不是面向未成年人的完整线上安全方案。
9. 求助资源文字与号码按用户提供原样保留，未核实其真实性、可用时间或适用范围；本网站也不提供实时值守或实际通知服务。
