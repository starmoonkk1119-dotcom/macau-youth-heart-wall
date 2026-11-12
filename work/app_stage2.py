"""Streamlit interface. Run with: streamlit run app.py"""

from datetime import datetime, timedelta, timezone
import sqlite3

import streamlit as st

from ai import analyze_post, normalize_text
from db import MAX_CONTENT_LENGTH, create_post, get_approved_posts, init_db


MACAU_TIMEZONE = timezone(timedelta(hours=8))


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
                status = "crisis" if analysis["moderation"] == "crisis" else "pending"
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


def wall_page() -> None:
    st.title("心声墙")
    st.caption("每一份感受，都值得被认真对待。")
    try:
        posts = get_approved_posts()
    except sqlite3.Error:
        st.error("暂时无法读取心声，请稍后重试。")
        return

    if not posts:
        st.info("心声墙暂时还没有可以公开的心声。")
        return

    for post in posts:
        with st.container(border=True):
            created_at = datetime.fromisoformat(
                post["created_at"].replace("Z", "+00:00")
            ).astimezone(MACAU_TIMEZONE)
            st.caption(
                f"匿名心声 #{post['id']} · "
                f"{created_at:%Y-%m-%d %H:%M}（澳门时间）"
            )
            # Render user content as literal text, never as HTML or Markdown.
            st.text(post["content"])


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
        page = st.radio("导航", ("写心声", "心声墙"), label_visibility="collapsed")
        st.divider()
        st.caption("请保护自己和他人的隐私。")

    if page == "写心声":
        write_post_page()
    else:
        wall_page()


if __name__ == "__main__":
    main()
