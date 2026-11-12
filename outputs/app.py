"""Streamlit interface. Run with: streamlit run app.py"""

from datetime import datetime, timedelta, timezone
from html import escape
import hashlib
import hmac
import os
import sqlite3
from typing import Any

import streamlit as st

import db as storage
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


MACAU_TIMEZONE = timezone(timedelta(hours=8))
TEXT = {
    "zh": {
        "language": "语言 · Language",
        "language_zh": "中文",
        "language_en": "English",
        "page_title": "心声墙 | 澳门青少年",
        "brand": "澳门青少年心声墙",
        "welcome": "不必把话整理得很好。这里愿意听听你的感受，你不是一个人。",
        "sidebar_title": "🌱 心声墙",
        "sidebar_subtitle": "澳门青少年 · 匿名心声",
        "sidebar_note": "慢慢说，感受值得被听见。",
        "privacy_note": "请保护自己和他人的隐私。",
        "navigation": "导航",
        "write_page": "写心声",
        "wall_page": "心声墙",
        "admin_page": "管理员",
        "write_intro": "今天的开心、委屈，或还说不清的心情，都可以慢慢写。",
        "write_privacy": (
            "仅填写虚构示例。提交后，正文将发送至 DeepSeek 进行 AI 分析。"
            "请勿填写真实姓名、学校、电话或其他可识别身份的信息。"
        ),
        "post_saved": "提交成功，心声编号 #{id}，尚未公开。",
        "crisis_notice": (
            "这条心声需要优先安全关注，不会公开。"
            "本网站不是实时求助渠道，不能保证有人即时查看。"
        ),
        "pending_receipt": "当前状态：待人工审核。",
        "companion_heading": "🌿 AI 陪伴回应 · 给此刻的你",
        "companion_label": "AI 陪伴回应",
        "private_receipt": "你没有同意匿名公开，这条心声不会展示在心声墙上。",
        "post_label": "此刻，你想说些什么？",
        "post_placeholder": (
            "例如：最近温习有点累，想有人听我说说……\n"
            "演示时，请只写虚构的感受，不留下真实姓名或学校。"
        ),
        "consent": "同意匿名公开",
        "consent_note": "是否公开由你选择；同意公开后，也会先由人工审核。",
        "submit_post": "轻轻放下",
        "post_empty": "请先写下一点心声，再提交。",
        "post_too_long": "心声最多支持 {limit} 个字符。",
        "post_spinner": "正在接住你的心声……",
        "post_save_failed": "暂时无法保存心声，文字已保留在输入框中，请稍后重试。",
        "reaction_understand": "我懂你",
        "reaction_hug": "抱抱",
        "reaction_metoo": "我也是",
        "reaction_worried": "我有点担心你",
        "reaction_crisis": "心声 #{id} 已转入优先安全关注，暂时退出公开墙。",
        "reaction_saved": "已为心声 #{id} 留下一份关怀。",
        "reaction_failed": "关怀暂未保存，帖子可能已退出公开墙，请刷新后重试。",
        "reply_label": "留下一点安慰",
        "reply_placeholder": "一句「愿意听你说说」，也可以是一份陪伴。请只填写虚构示例。",
        "submit_reply": "提交回复",
        "reply_empty": "请先写下一点安慰，再提交。",
        "reply_too_long": "回复最多支持 {limit} 个字符。",
        "reply_spinner": "正在检查回复……",
        "reply_save_failed": "暂时无法保存回复，输入已保留，请稍后重试。",
        "reply_saved": "心声 #{id} 的回复已提交，等待人工审核，尚未公开。",
        "wall_intro": "在别人的只言片语里，也许能遇见一点共鸣。",
        "wall_privacy": (
            "每一份感受，都值得被认真对待。"
            "仅填写虚构示例，回复正文将发送至 DeepSeek 分析，请勿填写身份信息。"
        ),
        "not_realtime": "本网站不是实时求助渠道，不能保证有人即时查看。",
        "wall_empty": "这里暂时还没有公开的心声。不着急，每一份表达都会先被认真看见。",
        "post_meta": "匿名心声 #{id} · {time}（澳门时间）",
        "reply_meta": "匿名回复 #{id} · {time}（澳门时间）",
        "care_heading": "留一份关怀",
        "replies_empty": "还没有通过审核的安慰。愿意的话，留下一句温柔的话。",
        "wall_load_failed": "暂时无法读取心声或回复，请稍后重试。",
        "approve": "通过",
        "reject": "退回",
        "admin_expired": "管理员登录已失效，请重新登录。",
        "review_saved": "审核结果已保存。",
        "review_stale": "该内容已被处理，请查看最新队列。",
        "review_failed": "审核结果暂未保存，请稍后重试。",
        "admin_disabled": "尚未配置 ADMIN_PASS，管理员入口已关闭。",
        "admin_password": "管理员密码",
        "login": "登录",
        "login_failed": "密码不正确，请重试。",
        "refresh_queue": "刷新队列",
        "logout": "退出登录",
        "queue_load_failed": "暂时无法读取审核队列，请稍后重试。",
        "post_queue": "待审核心声 · {count}",
        "post_queue_empty": "暂时没有待审核心声。",
        "admin_post_meta": "心声 #{id} · {time}（澳门时间）",
        "crisis_heading": "危机 · 优先安全关注",
        "pending_heading": "待人工审核",
        "post_details": "分类：{category} · AI 参考强度：{intensity} · 同意公开：{consent}",
        "not_assessed": "未评估",
        "yes": "是",
        "no": "否",
        "reply_queue": "待审核回复 · {count}",
        "reply_queue_empty": "暂时没有待审核回复。",
        "admin_reply_meta": "回复 #{id} → 心声 #{post_id} · {time}（澳门时间）",
        "parent_crisis": "所属心声需要优先安全关注",
        "parent_post": "所属心声",
        "pending_reply": "待审核回复",
        "db_init_failed": "数据库初始化失败，请检查项目文件夹是否可写后重试。",
        "category_study": "学业",
        "category_family": "家庭",
        "category_social": "社交",
        "category_feelings": "情绪",
        "category_unknown": "未分类",
        "help_resources": (
            "如果你现在很难受，请联系澳门明爱生命热线 28525222，"
            "或向信任的大人/学校社工求助。你并不孤单。"
        ),
        "disclaimer": "本项目为黑客松原型，使用示例数据，不收集真实个人信息，不能替代专业帮助。",
        "validation_failed": "暂时无法处理这段文字，请保留内容并稍后重试。",
        "invalid_post_type": "心声内容必须是文字。",
        "invalid_consent": "公开同意选项必须是勾选或未勾选。",
        "invalid_category": "心声分类无效。",
        "invalid_intensity": "心声强度必须是 1 到 5 的整数。",
        "invalid_ai_reply": "AI 回应不能为空。",
        "invalid_new_status": "新心声必须等待人工审核或安全关注。",
        "post_not_public": "这条心声已不在公开墙上，请刷新页面。",
        "invalid_reaction": "无效的关怀类型。",
        "invalid_reply_moderation": "回复审核结果无效。",
        "invalid_review": "无效的审核操作。",
        "why_title": "为什么需要这个平台",
        "why_intro": "以下为公开研究与媒体报道数据，反映社会现状；它们不是本平台产生的数据。",
        "why_depression_value": "约 35.2%",
        "why_depression_label": "澳门大学生抑郁筛查检出率",
        "why_depression_source": "来源：Scientific Reports，2020；澳门大学生样本研究。",
        "why_depression_note": "这是特定样本与筛查结果，不代表澳门所有青少年，也不是当前总体比例。",
        "why_anxiety_value": "约 22%",
        "why_anxiety_label": "澳门青少年明显焦虑症状分组",
        "why_anxiety_source": "来源：学术研究；约 22% 属于严重至非常严重焦虑症状分组。",
        "why_anxiety_note": "这是研究中的特定分组与调查结果，不代表所有澳门青少年。",
        "why_media_value": "“隐形的疫情”",
        "why_media_label": "媒体对澳门青少年心理健康处境的描述",
        "why_media_source": "来源线索：Macau Business，2026；原文尚待核实。",
        "why_media_note": "此处保留项目简报中的媒体线索，不把未核实表述当作已证实研究结论。",
        "insights_title": "群体洞察看板",
        "insights_intro": "以下为本平台匿名聚合数据（示例），用于呈现群体趋势，不构成任何个体诊断或临床结论。",
        "insights_total": "总心声数",
        "insights_public": "已公开心声数",
        "insights_pending": "待审核心声数",
        "insights_crisis": "危机心声数（当前）",
        "insights_crisis_note": "这里统计当前 status='crisis' 的心声；数据库没有单独记录历史触发事件。",
        "insights_category_title": "按分类的心声数量",
        "insights_category_caption": "仅展示数据库中四个固定分类的数量。",
        "insights_intensity_title": "按强度的心声数量",
        "insights_intensity_caption": "仅展示数据库中 intensity 1 到 5 的数量。",
        "insights_daily_title": "按日期的发帖数量",
        "insights_daily_caption": "按澳门时间的 created_at 日期汇总，包含所有状态。",
        "insights_reactions_title": "关怀 reaction 总次数",
        "insights_reactions_caption": "统计四种关怀 reaction 的写入次数，不代表独立人数。",
        "insights_no_daily": "目前还没有可用于按日期展示的发帖记录。",
        "insights_load_failed": "暂时无法读取群体洞察数据；审核队列仍可继续使用。",
        "chart_category": "分类",
        "chart_count": "数量",
        "chart_intensity": "强度",
        "chart_date": "日期",
        "reaction_understand_total": "我懂你",
        "reaction_hug_total": "抱抱",
        "reaction_metoo_total": "我也是",
        "reaction_worried_total": "我有点担心你",
    },
    "en": {
        "language": "Language",
        "language_zh": "中文",
        "language_en": "English",
        "page_title": "Heart Wall | Macao Youth",
        "brand": "Macao Youth Heart Wall",
        "welcome": "Your words don't have to be perfect. Your feelings matter, and you're not alone.",
        "sidebar_title": "🌱 Heart Wall",
        "sidebar_subtitle": "Macao youth · Anonymous sharing",
        "sidebar_note": "Take your time. Your feelings deserve to be heard.",
        "privacy_note": "Please protect your privacy and other people's, too.",
        "navigation": "Explore",
        "write_page": "Share a feeling",
        "wall_page": "Heart wall",
        "admin_page": "Admin",
        "write_intro": "A little joy, a difficult day, or a feeling you can't quite name. Start wherever you are.",
        "write_privacy": (
            "Use fictional examples only. When you send a post, its text goes to DeepSeek for AI analysis. "
            "Please leave out real names, schools, phone numbers, or anything that could identify someone."
        ),
        "post_saved": "Your words have been saved as post #{id}. They are not public yet.",
        "crisis_notice": (
            "This post needs priority safety attention and will not be made public. "
            "This is not a live support service, and we cannot promise an immediate response."
        ),
        "pending_receipt": "Waiting for a human reviewer. Not public yet.",
        "companion_heading": "🌿 A little support from AI · For you, right now",
        "companion_label": "A supportive AI response",
        "private_receipt": "You haven't agreed to public sharing, so this post will stay off the heart wall.",
        "post_label": "What's on your mind today?",
        "post_placeholder": (
            "For example: Studying has felt tiring lately, and I'd like someone to listen...\n"
            "For this demo, use a fictional feeling and leave out real names and schools."
        ),
        "consent": "I agree to share this anonymously",
        "consent_note": "Sharing is your choice. If you agree, a human will still review your post first.",
        "submit_post": "Set it down here",
        "post_empty": "Write a little about the feeling you'd like to share first.",
        "post_too_long": "Please keep your post within {limit} characters.",
        "post_spinner": "Taking a moment with your words...",
        "post_save_failed": "We couldn't save your post just now. Your words are still in the box; please try again later.",
        "reaction_understand": "I hear you",
        "reaction_hug": "A gentle hug",
        "reaction_metoo": "Me too",
        "reaction_worried": "I'm concerned",
        "reaction_crisis": "Post #{id} has moved to the priority safety queue and is no longer on the public wall.",
        "reaction_saved": "Your care for post #{id} has been saved.",
        "reaction_failed": "We couldn't save that gesture. The post may no longer be public; please refresh and try again.",
        "reply_label": "Leave a little kindness",
        "reply_placeholder": "A simple \"I'm here to listen\" can mean a lot. Use fictional examples only.",
        "submit_reply": "Send a little kindness",
        "reply_empty": "Write a few kind words before sending your reply.",
        "reply_too_long": "Please keep your reply within {limit} characters.",
        "reply_spinner": "Taking a careful look at your reply...",
        "reply_save_failed": "We couldn't save your reply just now. Your words are still there; please try again later.",
        "reply_saved": "Your reply to post #{id} is waiting for human review. It isn't public yet.",
        "wall_intro": "Sometimes, a few words from someone else can help us feel less alone.",
        "wall_privacy": (
            "Every feeling deserves care. Use fictional examples only. "
            "Reply text goes to DeepSeek for analysis, so please leave out identifying details."
        ),
        "not_realtime": "This is not a live support service. We cannot promise an immediate response.",
        "wall_empty": "No posts are public yet. There's no rush; every post needs a human review first.",
        "post_meta": "Anonymous post #{id} · {time} (Macao time)",
        "reply_meta": "Anonymous reply #{id} · {time} (Macao time)",
        "care_heading": "A small gesture of care",
        "replies_empty": "No replies have been approved yet. A few kind words could be a gentle start.",
        "wall_load_failed": "We couldn't load the posts or replies just now. Please try again later.",
        "approve": "Approve",
        "reject": "Return",
        "admin_expired": "Your admin session has expired. Please sign in again.",
        "review_saved": "Review saved.",
        "review_stale": "This item has already been reviewed. Please check the latest queue.",
        "review_failed": "The review couldn't be saved. Please try again later.",
        "admin_disabled": "ADMIN_PASS hasn't been configured, so admin access is closed.",
        "admin_password": "Admin password",
        "login": "Sign in",
        "login_failed": "That password doesn't match. Please try again.",
        "refresh_queue": "Refresh queue",
        "logout": "Sign out",
        "queue_load_failed": "We couldn't load the review queue. Please try again later.",
        "post_queue": "Posts awaiting review · {count}",
        "post_queue_empty": "No posts are waiting for review.",
        "admin_post_meta": "Post #{id} · {time} (Macao time)",
        "crisis_heading": "Crisis · Priority safety attention",
        "pending_heading": "Awaiting human review",
        "post_details": "Category: {category} · AI intensity estimate: {intensity} · Public sharing agreed: {consent}",
        "not_assessed": "Not assessed",
        "yes": "Yes",
        "no": "No",
        "reply_queue": "Replies awaiting review · {count}",
        "reply_queue_empty": "No replies are waiting for review.",
        "admin_reply_meta": "Reply #{id} → Post #{post_id} · {time} (Macao time)",
        "parent_crisis": "The parent post needs priority safety attention",
        "parent_post": "Parent post",
        "pending_reply": "Reply awaiting review",
        "db_init_failed": "We couldn't open the database. Please check that the project folder is writable and try again.",
        "category_study": "School",
        "category_family": "Family",
        "category_social": "Friendships",
        "category_feelings": "Feelings",
        "category_unknown": "Uncategorised",
        "help_resources": (
            "If things feel very difficult right now, please contact the Caritas Macao Life Hope Hotline "
            "at 28525222, or reach out to a trusted adult or your school social worker. You are not alone."
        ),
        "disclaimer": (
            "This is a hackathon prototype using sample data. It is not intended to collect real personal "
            "information and cannot replace professional help."
        ),
        "validation_failed": "We couldn't process these words just now. Please keep a copy and try again later.",
        "invalid_post_type": "Please write your post as text.",
        "invalid_consent": "Please choose whether you agree to anonymous public sharing.",
        "invalid_category": "The post's category couldn't be processed.",
        "invalid_intensity": "The intensity estimate must be a whole number from 1 to 5.",
        "invalid_ai_reply": "The AI response couldn't be saved because it was empty.",
        "invalid_new_status": "A new post must wait for human review or priority safety attention.",
        "post_not_public": "This post is no longer on the public wall. Please refresh the page.",
        "invalid_reaction": "That gesture of care couldn't be processed.",
        "invalid_reply_moderation": "The reply's review result couldn't be processed.",
        "invalid_review": "That review action couldn't be processed.",
        "why_title": "Why MindWall Exists",
        "why_intro": "The following public research and media context reflects wider social conditions; it is not data produced by this platform.",
        "why_depression_value": "About 35.2%",
        "why_depression_label": "Depression screening result among Macao university students",
        "why_depression_source": "Source: Scientific Reports, 2020; a study of Macao university students.",
        "why_depression_note": "This describes a specific sample and screening result, not all Macao youth or a current population rate.",
        "why_anxiety_value": "About 22%",
        "why_anxiety_label": "Macao adolescents in a marked-anxiety symptom group",
        "why_anxiety_source": "Source: academic research; about 22% were in the severe-to-extremely-severe anxiety group.",
        "why_anxiety_note": "This is a specific survey grouping and result, not a figure for every adolescent in Macao.",
        "why_media_value": "“An invisible epidemic”",
        "why_media_label": "A media description of youth mental-health pressures in Macao",
        "why_media_source": "Source lead: Macau Business, 2026; original article still needs verification.",
        "why_media_note": "This keeps the project brief's media lead visible without presenting an unverified phrase as a confirmed research finding.",
        "insights_title": "Community insights",
        "insights_intro": "The following are anonymous aggregate data from this platform (demo data), shown to describe group trends. They are not individual diagnoses or clinical conclusions.",
        "insights_total": "All posts",
        "insights_public": "Public posts",
        "insights_pending": "Posts awaiting review",
        "insights_crisis": "Current crisis posts",
        "insights_crisis_note": "This counts posts whose current status is 'crisis'; the database does not separately record historical trigger events.",
        "insights_category_title": "Posts by category",
        "insights_category_caption": "Shows counts for the four fixed categories stored in the database.",
        "insights_intensity_title": "Posts by intensity",
        "insights_intensity_caption": "Shows counts for database values from intensity 1 through 5.",
        "insights_daily_title": "Posts by date",
        "insights_daily_caption": "Groups created_at by Macao calendar date across all statuses.",
        "insights_reactions_title": "Total care reactions",
        "insights_reactions_caption": "Counts writes for the four care reactions; it does not represent unique people.",
        "insights_no_daily": "There are no post records available for a date trend yet.",
        "insights_load_failed": "We couldn't load the community insights right now; the review queue is still available.",
        "chart_category": "Category",
        "chart_count": "Count",
        "chart_intensity": "Intensity",
        "chart_date": "Date",
        "reaction_understand_total": "I hear you",
        "reaction_hug_total": "A gentle hug",
        "reaction_metoo_total": "Me too",
        "reaction_worried_total": "I'm concerned",
    },
}
HELP_RESOURCES = TEXT["zh"]["help_resources"]
DEMO_DISCLAIMER = TEXT["zh"]["disclaimer"]
REACTION_TYPES = ("understand", "hug", "metoo", "worried")
REACTION_LABELS = tuple(
    (kind, TEXT["zh"][f"reaction_{kind}"]) for kind in REACTION_TYPES
)
NAVIGATION = {"写心声": "write_page", "心声墙": "wall_page", "管理员": "admin_page"}
REACTION_ICONS = {
    "understand": "💚", "hug": "🫂", "metoo": "🌷", "worried": "🤍",
}
CATEGORY_STYLES = {
    "学业": "study", "家庭": "family", "社交": "social", "情绪": "feelings",
}

PAGE_STYLES = """
<style>
:root {
    --hw-ink: #22383a;
    --hw-ink-soft: #395355;
    --hw-muted: #5d7474;
    --hw-primary: #4d8078;
    --hw-primary-deep: #356962;
    --hw-mint: #e8f2ee;
    --hw-mint-strong: #d6e9e1;
    --hw-sky: #eaf2f5;
    --hw-lilac: #eeeaf5;
    --hw-blush: #f6e9e5;
    --hw-sand: #faf2df;
    --hw-line: #d7e4df;
    --hw-paper: #f7f5ef;
    --hw-surface: #fffdf9;
    --hw-surface-muted: #f1f6f2;
    --hw-shadow: 0 16px 42px rgba(48, 83, 78, .09);
    color-scheme: light;
}

html, body {
    background: var(--hw-paper);
}

.stApp, [data-testid="stAppViewContainer"] {
    background: var(--hw-paper);
    color: var(--hw-ink);
}

html, body, .stApp, button, input, textarea,
[data-testid="stMarkdownContainer"], [data-testid="stText"] {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
        "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    letter-spacing: 0;
}

[data-testid="stHeader"] {
    background: rgba(247, 245, 239, .88);
}

[data-testid="stMainBlockContainer"] {
    max-width: 980px;
    padding-top: 3.75rem;
    padding-bottom: 3.25rem;
}

[data-testid="stSidebar"] {
    background: #edf4ef;
    border-right: 1px solid var(--hw-line);
    color: var(--hw-ink);
}

[data-testid="stSidebar"] > div:first-child {
    padding-top: 1.8rem;
}

[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] p {
    color: var(--hw-ink);
}

[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
    color: var(--hw-muted);
}

[data-testid="stSidebar"] h1 {
    color: var(--hw-primary-deep);
    font-size: 1.45rem;
    font-weight: 750;
    letter-spacing: -.01em;
}

[data-testid="stSidebar"] [data-testid="stRadio"] label {
    padding: .72rem .8rem;
    min-height: 46px;
    margin: .2rem 0;
    cursor: pointer;
    color: var(--hw-ink-soft);
    font-weight: 600;
    border: 1px solid transparent;
    border-radius: 14px;
    transition: background-color .18s ease, border-color .18s ease,
        transform .18s ease;
}

[data-testid="stSidebar"] [data-testid="stRadio"] label p {
    color: var(--hw-ink-soft);
    font-weight: 600;
}

[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
    background: var(--hw-surface);
    border-color: var(--hw-mint-strong);
    color: var(--hw-primary-deep);
    box-shadow: 0 6px 18px rgba(53, 105, 98, .08);
}

[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p {
    color: var(--hw-primary-deep);
}

[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
    background: rgba(255, 253, 249, .65);
    border-color: var(--hw-mint-strong);
    transform: translateX(2px);
}

[data-testid="stRadioOption"][data-selected="true"] > div > div:first-child {
    background: var(--hw-primary);
    border-color: var(--hw-primary);
}

[data-testid="stCheckbox"] label[data-selected="true"] > div:first-of-type {
    background: var(--hw-primary);
    border-color: var(--hw-primary);
}

h1, h2, h3 {
    color: var(--hw-ink);
    letter-spacing: -.01em;
}

h2 {
    font-size: clamp(1.55rem, 3vw, 2rem);
    font-weight: 760;
    line-height: 1.25;
    margin-top: .8rem;
}

h3 {
    color: var(--hw-ink-soft);
    font-size: 1.08rem;
    font-weight: 720;
    line-height: 1.35;
}

p, [data-testid="stText"] {
    line-height: 1.82;
}

[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] strong,
[data-testid="stText"] {
    color: var(--hw-ink);
}

[data-testid="stText"] {
    font-size: 1rem;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    word-break: normal;
}

[data-testid="stCaptionContainer"] p {
    color: var(--hw-muted);
    font-size: .86rem;
    line-height: 1.7;
}

[data-testid="stMetric"] {
    background: var(--hw-surface);
    border: 1px solid var(--hw-line);
    border-radius: 18px;
    box-shadow: 0 8px 24px rgba(48, 83, 78, .06);
    padding: 1rem 1.05rem;
    color: var(--hw-ink);
}

[data-testid="stMetricLabel"],
[data-testid="stMetricLabel"] p,
[data-testid="stMetricValue"],
[data-testid="stMetricValue"] > div,
[data-testid="stMetricDelta"] {
    color: var(--hw-ink);
}

[data-testid="stMetricLabel"] {
    font-size: .84rem;
    font-weight: 650;
}

[data-testid="stMetricValue"] {
    color: var(--hw-primary-deep);
    font-size: 1.55rem;
    font-weight: 760;
}

.welcome {
    display: flex;
    align-items: center;
    gap: 1.1rem;
    padding: 1.45rem 1.55rem;
    margin: 0 0 2.15rem;
    background: #edf6f1;
    border: 1px solid var(--hw-line);
    border-radius: 24px;
    box-shadow: var(--hw-shadow);
}

.welcome .welcome-mark {
    display: grid;
    flex: 0 0 56px;
    width: 56px;
    height: 56px;
    place-items: center;
    color: var(--hw-primary-deep);
    background: rgba(255, 253, 249, .8);
    border: 1px solid rgba(77, 128, 120, .18);
    border-radius: 18px;
    font-size: 1.7rem;
    box-shadow: 0 8px 18px rgba(53, 105, 98, .08);
}

.welcome-copy {
    min-width: 0;
}

.welcome-eyebrow {
    margin-bottom: .35rem;
    color: var(--hw-primary-deep);
    font-size: .76rem;
    font-weight: 750;
    letter-spacing: .08em;
    text-transform: uppercase;
}

.welcome h1 {
    font-size: clamp(1.65rem, 4vw, 2.35rem);
    line-height: 1.2;
    font-weight: 780;
    padding: 0;
    margin: 0 0 .45rem;
    overflow-wrap: anywhere;
}

.welcome p { color: var(--hw-muted); margin: 0; font-size: 1rem; }
.welcome p, .category-chip { overflow-wrap: anywhere; }

.st-key-language {
    margin-bottom: .7rem;
}

.st-key-language [role="combobox"] {
    border-radius: 13px;
    color: var(--hw-ink);
    min-height: 46px;
}

.st-key-language [data-baseweb="select"] {
    background: var(--hw-surface);
    border: 1px solid #bcd4c9;
    color: var(--hw-ink);
}

.st-key-language [data-baseweb="select"] * {
    color: var(--hw-ink);
}

.st-key-navigation { margin-top: .25rem; }

[data-testid="stTextArea"] textarea,
[data-testid="stTextInput"] input {
    background: var(--hw-surface);
    color: var(--hw-ink);
    line-height: 1.85;
    caret-color: var(--hw-primary);
}

[data-testid="stTextArea"] [data-baseweb="textarea"],
[data-testid="stTextInput"] [data-baseweb="input"],
[data-testid="stTextAreaRootElement"],
[data-testid="stTextInputRootElement"] {
    background: var(--hw-surface);
    border: 1px solid #bcd4c9;
    border-radius: 16px;
}

[data-testid="stTextArea"] [data-baseweb="textarea"]:focus-within,
[data-testid="stTextInput"] [data-baseweb="input"]:focus-within,
[data-testid="stTextAreaRootElement"]:focus-within,
[data-testid="stTextInputRootElement"]:focus-within {
    border-color: var(--hw-primary);
    box-shadow: 0 0 0 4px rgba(77, 128, 120, .14);
}

textarea::placeholder, input::placeholder {
    color: #6b8080;
    opacity: 1;
}

[data-testid="stCheckbox"] label { color: var(--hw-ink); }
[data-testid="stCheckbox"] input { accent-color: var(--hw-primary); }

[data-testid="stCheckbox"] {
    padding: .3rem 0;
}

[data-testid="stVerticalBlockBorderWrapper"] {
    background: rgba(255, 253, 249, .78);
    border-color: var(--hw-line);
    border-radius: 20px;
    box-shadow: 0 10px 28px rgba(48, 83, 78, .055);
}

.st-key-new_post {
    background: rgba(255, 253, 249, .62);
    border: 1px solid rgba(215, 228, 223, .8);
    border-radius: 22px;
    padding: 1.25rem 1.35rem .8rem;
}

button[kind] {
    border-radius: 999px;
    min-height: 44px;
    border-color: #c7dcd2;
    color: var(--hw-ink);
    background: var(--hw-surface);
    font-weight: 650;
    transition: background-color .18s ease, border-color .18s ease,
        box-shadow .18s ease, transform .18s ease;
}

button[kind]:hover {
    background: var(--hw-mint);
    border-color: var(--hw-primary);
    color: var(--hw-ink);
    box-shadow: 0 8px 18px rgba(77, 128, 120, .11);
    transform: translateY(-1px);
}

button[kind="primary"], button[kind="primaryFormSubmit"] {
    background: var(--hw-primary);
    border-color: var(--hw-primary);
    color: #fff;
    padding: .15rem 1.4rem;
    box-shadow: 0 8px 18px rgba(53, 105, 98, .16);
}

button[kind="primary"]:hover, button[kind="primaryFormSubmit"]:hover {
    background: var(--hw-primary-deep);
    border-color: var(--hw-primary-deep);
    color: #fff;
}

button:focus-visible, a:focus-visible {
    outline: 3px solid #82b7a6;
    outline-offset: 3px;
}

div[class*="st-key-heart_post_"] {
    background: var(--hw-surface);
    border: 1px solid var(--hw-line);
    border-radius: 22px;
    padding: 1.5rem 1.55rem 1.25rem;
    margin: 1.15rem 0 1.3rem;
    box-shadow: var(--hw-shadow);
    transition: border-color .18s ease, box-shadow .18s ease,
        transform .18s ease;
}

div[class*="st-key-heart_post_"]:hover {
    border-color: #b8d6ca;
    box-shadow: 0 20px 46px rgba(48, 83, 78, .12);
    transform: translateY(-2px);
}

div[class*="st-key-heart_post_"] [data-testid="stHorizontalBlock"] {
    gap: .65rem;
    flex-wrap: wrap;
}

div[class*="st-key-heart_post_"] [data-testid="stColumn"] {
    min-width: 0;
    flex: 1 1 calc(50% - .65rem);
}

div[class*="st-key-heart_post_"] button {
    width: 100%;
    min-height: 48px;
    font-size: .88rem;
    padding: .5rem .65rem;
    background: #fbfcf9;
}

div[class*="st-key-heart_post_"] button p {
    font-size: .88rem;
    line-height: 1.5;
    white-space: normal;
    overflow-wrap: anywhere;
}

.st-key-context_card_0,
.st-key-context_card_1,
.st-key-context_card_2 {
    min-height: 100%;
}

.st-key-context_card_0 [data-testid="stMetricValue"] { color: #4d8078; }
.st-key-context_card_1 [data-testid="stMetricValue"] { color: #7b789f; }
.st-key-context_card_2 [data-testid="stMetricValue"] { color: #b97961; }

.st-key-companion_reply {
    position: relative;
    background: var(--hw-sky);
    border: 1px solid #cfe1e5;
    border-radius: 18px;
    padding: 1.2rem 1.35rem 1.15rem;
    margin: .5rem 0 .95rem;
    box-shadow: 0 10px 26px rgba(80, 123, 132, .08);
}

.st-key-companion_reply [data-testid="stCaptionContainer"] p {
    color: #4f777c;
    font-weight: 600;
    letter-spacing: .01em;
}

.st-key-companion_reply [data-testid="stText"] {
    color: #31565c;
    font-weight: 500;
    line-height: 1.9;
}

.category-chip {
    display: inline-flex;
    align-items: center;
    padding: .28rem .72rem;
    border-radius: 999px;
    font-size: .78rem;
    font-weight: 600;
    line-height: 1.6;
    letter-spacing: .01em;
    background: var(--hw-mint);
    color: #3b6d63;
}

.category-chip.study { background: #e8f2f5; color: #4b7180; }
.category-chip.family { background: var(--hw-lilac); color: #6e638c; }
.category-chip.social { background: #e5f1ec; color: #3f7668; }
.category-chip.feelings { background: var(--hw-blush); color: #966758; }

[data-testid="stAlert"] {
    border-radius: 16px;
    padding: 1rem 1.15rem;
    line-height: 1.8;
    box-shadow: 0 8px 22px rgba(48, 83, 78, .05);
}

[data-testid="stAlert"]:has([data-testid="stAlertContentError"]) {
    background: #f8eee9;
    border: 1px solid #e6c9bf;
    color: #7d574c;
}

[data-testid="stAlertContentError"] { color: #7d574c; }

[data-testid="stAlert"] [data-testid="stAlertContainer"],
[data-testid="stAlert"] [data-testid^="stAlertContent"] {
    background: transparent;
    border: 0;
    padding: 0;
    color: inherit;
}

[data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]) {
    background: var(--hw-mint);
    border: 1px solid #c9e1d6;
    color: #37695d;
}

[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]) {
    background: var(--hw-sand);
    border: 1px solid #ead7aa;
    color: #765d2d;
}

[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) {
    background: var(--hw-sky);
    border: 1px solid #cfe1e5;
    color: #3e6970;
}

[data-testid="stElementContainer"]:has(.support-anchor) { display: none; }

[data-testid="stVerticalBlock"]:has(
    > [data-testid="stElementContainer"] .support-anchor
) [data-testid="stAlert"] {
    background: #fff4df;
    border: 1px solid #e7c98d;
    border-left: 5px solid #d29a55;
    border-radius: 18px;
    box-shadow: 0 12px 28px rgba(156, 108, 48, .1);
}

[data-testid="stVerticalBlock"]:has(
    > [data-testid="stElementContainer"] .support-anchor
) [data-testid="stAlert"] * {
    color: #765622;
}

hr {
    border-color: var(--hw-line);
    margin: 1.25rem 0;
}

[data-testid="stExpander"] {
    border-color: var(--hw-line);
    border-radius: 16px;
}

[data-testid="stDataFrame"] {
    border-radius: 16px;
    overflow: hidden;
}

@media (max-width: 640px) {
    [data-testid="stMainBlockContainer"] {
        padding: 2.8rem 1rem 2rem;
    }

    .welcome {
        align-items: flex-start;
        gap: .85rem;
        padding: 1.15rem;
        margin-bottom: 1.55rem;
        border-radius: 20px;
    }

    .welcome .welcome-mark {
        flex-basis: 46px;
        width: 46px;
        height: 46px;
        border-radius: 15px;
        font-size: 1.4rem;
    }

    .welcome h1 { font-size: 1.65rem; }
    .welcome p { font-size: .95rem; }

    div[class*="st-key-heart_post_"] {
        padding: 1.1rem;
        border-radius: 19px;
    }

    div[class*="st-key-heart_post_"] [data-testid="stColumn"] {
        flex-basis: 100%;
    }

    .st-key-companion_reply { padding: 1rem 1.05rem; }
    [data-testid="stText"] { font-size: .95rem; }
}

@media (max-width: 360px) {
    .welcome { padding: 1rem; }
    .welcome h1 { font-size: 1.48rem; }
}

@media (prefers-reduced-motion: reduce) {
    button[kind],
    [data-testid="stSidebar"] [data-testid="stRadio"] label,
    div[class*="st-key-heart_post_"] {
        transition: none;
    }
}
</style>
"""


def apply_page_style() -> None:
    st.markdown(PAGE_STYLES, unsafe_allow_html=True)


def current_language() -> str:
    return "en" if st.session_state.get("language") == "en" else "zh"


def t(key: str, **values: object) -> str:
    return TEXT[current_language()][key].format(**values)


def category_label(category: str | None) -> str:
    style = CATEGORY_STYLES.get(category or "", "unknown")
    return t(f"category_{style}")


def validation_message(error: ValueError) -> str:
    message = str(error)
    # Translate known storage errors without changing the database module.
    for key in (
        "post_empty", "post_too_long", "reply_empty", "reply_too_long",
        "invalid_post_type", "invalid_consent", "invalid_category",
        "invalid_intensity", "invalid_ai_reply", "invalid_new_status",
        "post_not_public", "invalid_reaction", "invalid_reply_moderation",
        "invalid_review",
    ):
        if message in (
            TEXT["zh"][key].format(limit=MAX_CONTENT_LENGTH),
            TEXT["en"][key].format(limit=MAX_CONTENT_LENGTH),
        ):
            return t(key, limit=MAX_CONTENT_LENGTH)
    return message if current_language() == "zh" else t("validation_failed")


def show_welcome() -> None:
    st.markdown(
        '<section class="welcome">'
        '<div class="welcome-mark" aria-hidden="true">🌱</div>'
        '<div class="welcome-copy">'
        f'<div class="welcome-eyebrow">{escape(t("sidebar_subtitle"))}</div>'
        f'<h1>{escape(t("brand"))}</h1>'
        f'<p>{escape(t("welcome"))}</p>'
        '</div>'
        '</section>',
        unsafe_allow_html=True,
    )


def show_public_context() -> None:
    """Show external context separately from the platform's own data."""
    st.markdown(f"### {escape(t('why_title'))}")
    st.caption(t("why_intro"))
    cards = (
        (
            "why_depression_value",
            "why_depression_label",
            "why_depression_source",
            "why_depression_note",
        ),
        (
            "why_anxiety_value",
            "why_anxiety_label",
            "why_anxiety_source",
            "why_anxiety_note",
        ),
        (
            "why_media_value",
            "why_media_label",
            "why_media_source",
            "why_media_note",
        ),
    )
    columns = st.columns(3)
    for index, (column, keys) in enumerate(zip(columns, cards)):
        with column:
            with st.container(border=True, key=f"context_card_{index}"):
                st.metric(t(keys[1]), t(keys[0]))
                st.caption(t(keys[2]))
                st.caption(t(keys[3]))


def _read_insights() -> dict[str, Any]:
    """Read anonymous aggregates without selecting content or changing data."""
    db_uri = f"{storage.DB_PATH.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(db_uri, uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        totals = connection.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'approved' AND consent_public = 1
                         THEN 1 ELSE 0 END) AS public,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN status = 'crisis' THEN 1 ELSE 0 END) AS crisis
            FROM posts
            """
        ).fetchone()
        category_rows = connection.execute(
            """
            SELECT category, COUNT(*) AS count
            FROM posts
            WHERE category IN ('学业', '家庭', '社交', '情绪')
            GROUP BY category
            """
        ).fetchall()
        intensity_rows = connection.execute(
            """
            SELECT intensity, COUNT(*) AS count
            FROM posts
            WHERE intensity IN (1, 2, 3, 4, 5)
            GROUP BY intensity
            """
        ).fetchall()
        daily_rows = connection.execute(
            """
            SELECT date(created_at, '+8 hours') AS day, COUNT(*) AS count
            FROM posts
            WHERE date(created_at, '+8 hours') IS NOT NULL
            GROUP BY day
            ORDER BY day
            """
        ).fetchall()
        reaction_rows = connection.execute(
            """
            SELECT type, COUNT(*) AS count
            FROM reactions
            WHERE type IN ('understand', 'hug', 'metoo', 'worried')
            GROUP BY type
            """
        ).fetchall()
        return {
            "totals": {
                "total": int(totals["total"] or 0),
                "public": int(totals["public"] or 0),
                "pending": int(totals["pending"] or 0),
                "crisis": int(totals["crisis"] or 0),
            },
            "categories": {
                category: int(
                    next(
                        (row["count"] for row in category_rows
                         if row["category"] == category),
                        0,
                    )
                )
                for category in ("学业", "家庭", "社交", "情绪")
            },
            "intensities": {
                intensity: int(
                    next(
                        (row["count"] for row in intensity_rows
                         if row["intensity"] == intensity),
                        0,
                    )
                )
                for intensity in range(1, 6)
            },
            "daily": [
                {"day": row["day"], "count": int(row["count"])}
                for row in daily_rows
                if row["day"]
            ],
            "reactions": {
                reaction_type: int(
                    next(
                        (row["count"] for row in reaction_rows
                         if row["type"] == reaction_type),
                        0,
                    )
                )
                for reaction_type in REACTION_TYPES
            },
        }
    finally:
        connection.rollback()
        connection.close()


def show_insights_dashboard() -> None:
    if not admin_authenticated():
        return
    st.divider()
    st.markdown(f"### {escape(t('insights_title'))}")
    st.caption(t("insights_intro"))
    try:
        insights = _read_insights()
    except sqlite3.Error:
        st.error(t("insights_load_failed"))
        return

    totals = insights["totals"]
    with st.container(horizontal=True):
        st.metric(t("insights_total"), totals["total"], border=True)
        st.metric(t("insights_public"), totals["public"], border=True)
        st.metric(t("insights_pending"), totals["pending"], border=True)
        st.metric(t("insights_crisis"), totals["crisis"], border=True)
    st.caption(t("insights_crisis_note"))

    categories = insights["categories"]
    st.markdown(f"#### {escape(t('insights_category_title'))}")
    st.caption(t("insights_category_caption"))
    st.bar_chart(
        {
            t("chart_category"): [category_label(category)
                                  for category in categories],
            t("chart_count"): list(categories.values()),
        },
        x=t("chart_category"),
        y=t("chart_count"),
        sort=False,
        alt=t("insights_category_title"),
    )

    intensities = insights["intensities"]
    st.markdown(f"#### {escape(t('insights_intensity_title'))}")
    st.caption(t("insights_intensity_caption"))
    st.bar_chart(
        {
            t("chart_intensity"): list(intensities),
            t("chart_count"): list(intensities.values()),
        },
        x=t("chart_intensity"),
        y=t("chart_count"),
        sort=False,
        alt=t("insights_intensity_title"),
    )

    st.markdown(f"#### {escape(t('insights_daily_title'))}")
    st.caption(t("insights_daily_caption"))
    daily = insights["daily"]
    if daily:
        st.line_chart(
            daily,
            x="day",
            y="count",
            x_label=t("chart_date"),
            y_label=t("chart_count"),
            alt=t("insights_daily_title"),
        )
    else:
        st.caption(t("insights_no_daily"))

    st.markdown(f"#### {escape(t('insights_reactions_title'))}")
    st.caption(t("insights_reactions_caption"))
    reaction_titles = {
        "understand": "reaction_understand_total",
        "hug": "reaction_hug_total",
        "metoo": "reaction_metoo_total",
        "worried": "reaction_worried_total",
    }
    with st.container(horizontal=True):
        for reaction_type in REACTION_TYPES:
            st.metric(
                t(reaction_titles[reaction_type]),
                insights["reactions"][reaction_type],
                border=True,
            )


def show_category(category: str | None) -> None:
    # Only fixed labels enter HTML; posts and replies still use literal st.text.
    label = category_label(category)
    style = CATEGORY_STYLES.get(category or "", "")
    st.markdown(
        f'<span class="category-chip {style}">{escape(label)}</span>',
        unsafe_allow_html=True,
    )


def show_help_resources() -> None:
    with st.container():
        st.markdown('<span class="support-anchor" aria-hidden="true"></span>',
                    unsafe_allow_html=True)
        st.error(t("help_resources"))


def format_time(value: str) -> str:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        MACAU_TIMEZONE
    ).strftime("%Y-%m-%d %H:%M")


def write_post_page() -> None:
    st.subheader(t("write_page"))
    st.markdown(t("write_intro"))
    st.caption(t("write_privacy"))

    receipt = st.session_state.pop("_post_receipt", None)
    if receipt is not None:
        # Reset form widgets before rendering them, and only after a saved post.
        st.session_state["draft_content"] = ""
        st.session_state["consent_public"] = False
        st.success(t("post_saved", id=receipt["id"]))
        if receipt["status"] == "crisis":
            st.warning(t("crisis_notice"))
            show_help_resources()
        else:
            st.caption(t("pending_receipt"))
        with st.container(border=False, key="companion_reply"):
            st.caption(t("companion_heading"))
            st.text(receipt["ai_reply"])
        if not receipt["consent_public"]:
            st.caption(t("private_receipt"))

    with st.form("new_post", clear_on_submit=False, border=False):
        content = st.text_area(
            t("post_label"),
            height=200,
            max_chars=MAX_CONTENT_LENGTH,
            key="draft_content",
            placeholder=t("post_placeholder"),
        )
        consent_public = st.checkbox(t("consent"), key="consent_public")
        st.caption(t("consent_note"))
        submitted = st.form_submit_button(
            t("submit_post"), type="primary", icon="🌱", key="submit_post"
        )

    if submitted:
        try:
            if not normalize_text(content):
                raise ValueError(t("post_empty"))
            if len(content.strip()) > MAX_CONTENT_LENGTH:
                raise ValueError(t("post_too_long", limit=MAX_CONTENT_LENGTH))
            with st.spinner(t("post_spinner")):
                analysis = analyze_post(content, language=current_language())
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
            st.error(validation_message(error))
        except sqlite3.Error:
            st.error(t("post_save_failed"))
        else:
            st.session_state["_post_receipt"] = {
                "id": post_id,
                "consent_public": consent_public,
                "status": status,
                "ai_reply": analysis["ai_reply"],
            }
            st.rerun()


def reaction_buttons(post_id: int, counts: dict[str, int]) -> None:
    for offset in (0, 2):
        columns = st.columns(2)
        for column, reaction_type in zip(
            columns, REACTION_TYPES[offset:offset + 2]
        ):
            if column.button(
                f"{t(f'reaction_{reaction_type}')} · {counts[reaction_type]}",
                key=f"reaction_{post_id}_{reaction_type}",
                icon=REACTION_ICONS[reaction_type],
                width="stretch",
                wrap=True,
            ):
                try:
                    crisis = add_reaction(post_id, reaction_type)
                    st.session_state["_wall_notice"] = {
                        "message": (
                            t("reaction_crisis", id=post_id)
                            if crisis else t("reaction_saved", id=post_id)
                        ),
                        "help": crisis,
                    }
                except (ValueError, sqlite3.Error):
                    st.session_state["_wall_notice"] = {
                        "message": t("reaction_failed"),
                        "error": True,
                    }
                st.rerun()


def reply_form(post_id: int) -> None:
    draft_key = f"reply_draft_{post_id}"
    with st.form(f"reply_form_{post_id}", clear_on_submit=False, border=False):
        content = st.text_area(
            t("reply_label"),
            key=draft_key,
            max_chars=MAX_CONTENT_LENGTH,
            height=100,
            placeholder=t("reply_placeholder"),
        )
        submitted = st.form_submit_button(
            t("submit_reply"), icon="💌",
            # Keep the existing widget identity in both languages.
            key=f"FormSubmitter:reply_form_{post_id}-提交回复",
        )
    if submitted:
        try:
            if not normalize_text(content):
                raise ValueError(t("reply_empty"))
            if len(content.strip()) > MAX_CONTENT_LENGTH:
                raise ValueError(t("reply_too_long", limit=MAX_CONTENT_LENGTH))
            with st.spinner(t("reply_spinner")):
                analysis = analyze_post(content, language=current_language())
                create_reply(post_id, content, moderation=analysis["moderation"])
        except ValueError as error:
            st.error(validation_message(error))
        except sqlite3.Error:
            st.error(t("reply_save_failed"))
        else:
            st.session_state["_clear_reply_draft"] = draft_key
            st.session_state["_wall_notice"] = {
                "message": t("reply_saved", id=post_id),
                "help": analysis["moderation"] == "crisis",
            }
            st.rerun()


def wall_page() -> None:
    st.subheader(t("wall_page"))
    st.markdown(t("wall_intro"))
    st.caption(t("wall_privacy"))
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
            st.caption(t("not_realtime"))
    try:
        posts = get_approved_posts()
        if not posts:
            st.info(t("wall_empty"))
        for post in posts:
            counts = get_reaction_counts(post["id"])
            replies = get_approved_replies(post["id"])
            with st.container(border=True, key=f"heart_post_{post['id']}"):
                show_category(post["category"])
                st.caption(
                    t("post_meta", id=post["id"], time=format_time(post["created_at"]))
                )
                st.text(post["content"])
                if (post["intensity"] or 0) >= 4 or counts["worried"] >= 3:
                    show_help_resources()
                st.caption(t("care_heading"))
                reaction_buttons(post["id"], counts)
                st.divider()
                for reply in replies:
                    st.caption(
                        t("reply_meta", id=reply["id"], time=format_time(reply["created_at"]))
                    )
                    st.text(reply["content"])
                if not replies:
                    st.caption(t("replies_empty"))
                reply_form(post["id"])
    except sqlite3.Error:
        st.error(t("wall_load_failed"))


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
        t("approve"), key=f"approve_{kind}_{item_id}", type="primary"
    )
    rejected = columns[1].button(t("reject"), key=f"reject_{kind}_{item_id}")
    if approved or rejected:
        if not admin_authenticated():
            st.error(t("admin_expired"))
            return
        try:
            changed = review_item(
                kind, item_id, "approved" if approved else "rejected"
            )
            st.session_state["_admin_notice"] = {
                "message": t("review_saved") if changed else t("review_stale")
            }
        except (ValueError, sqlite3.Error):
            st.session_state["_admin_notice"] = {
                "message": t("review_failed"),
                "error": True,
            }
        st.rerun()


def admin_page() -> None:
    st.title(t("admin_page"))
    if not os.environ.get("ADMIN_PASS", "").strip():
        logout_admin()
        st.warning(t("admin_disabled"))
        return
    if not admin_authenticated():
        st.session_state.pop("_admin_token", None)
        with st.form("admin_login"):
            st.text_input(t("admin_password"), type="password", key="admin_password")
            st.form_submit_button(
                t("login"), on_click=check_admin_password, key="admin_login_submit"
            )
        if st.session_state.get("_admin_login_error"):
            st.error(t("login_failed"))
        return

    columns = st.columns(2)
    if columns[0].button(t("refresh_queue"), key="refresh_admin"):
        st.rerun()
    columns[1].button(t("logout"), key="logout_admin", on_click=logout_admin)
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
        st.error(t("queue_load_failed"))
        return

    st.subheader(t("post_queue", count=len(posts)))
    if not posts:
        st.info(t("post_queue_empty"))
    for post in posts:
        with st.container(border=True, key=f"admin_post_{post['id']}"):
            st.caption(
                t("admin_post_meta", id=post["id"], time=format_time(post["created_at"]))
            )
            if post["status"] == "crisis":
                st.error(t("crisis_heading"))
                show_help_resources()
            else:
                st.caption(t("pending_heading"))
            st.text(post["content"])
            st.caption(
                t(
                    "post_details", category=category_label(post["category"]),
                    intensity=post["intensity"] or t("not_assessed"),
                    consent=t("yes") if post["consent_public"] else t("no"),
                )
            )
            if post["ai_reply"]:
                st.caption(t("companion_label"))
                st.text(post["ai_reply"])
            review_buttons("post", post["id"])

    st.subheader(t("reply_queue", count=len(replies)))
    if not replies:
        st.info(t("reply_queue_empty"))
    for reply in replies:
        with st.container(border=True, key=f"admin_reply_{reply['id']}"):
            st.caption(
                t(
                    "admin_reply_meta", id=reply["id"], post_id=reply["post_id"],
                    time=format_time(reply["created_at"]),
                )
            )
            if reply["post_status"] == "crisis":
                st.error(t("parent_crisis"))
            st.caption(t("parent_post"))
            st.text(reply["post_content"])
            st.caption(t("pending_reply"))
            st.text(reply["content"])
            review_buttons("reply", reply["id"])
    show_insights_dashboard()


def main() -> None:
    st.session_state.setdefault("language", "zh")
    if st.session_state["language"] not in ("zh", "en"):
        st.session_state["language"] = "zh"
    st.set_page_config(
        page_title=t("page_title"), page_icon="🌱", layout="centered"
    )
    apply_page_style()
    try:
        init_db()
    except sqlite3.Error:
        st.error(t("db_init_failed"))
        st.stop()

    with st.sidebar:
        st.selectbox(
            t("language"), ("zh", "en"), key="language",
            format_func=lambda value: TEXT["zh"][f"language_{value}"],
        )
        st.title(t("sidebar_title"))
        st.caption(t("sidebar_subtitle"))
        navigation_labels = {value: t(key) for value, key in NAVIGATION.items()}
        page = st.radio(
            t("navigation"), tuple(NAVIGATION), key="navigation",
            format_func=navigation_labels.__getitem__,
            label_visibility="visible",
        )
        st.divider()
        st.markdown(t("sidebar_note"))
        st.caption(t("privacy_note"))

    if page != "管理员":
        show_welcome()
        show_public_context()
    if page == "写心声":
        write_post_page()
    elif page == "心声墙":
        wall_page()
    else:
        admin_page()
    st.divider()
    st.caption(t("disclaimer"))


if __name__ == "__main__":
    main()
