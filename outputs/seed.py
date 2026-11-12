"""Seed fictional demo fixtures only. No AI requests or API keys are needed."""

import argparse
import sqlite3

import db


DEMO_POSTS = [
    {
        "content": (
            "[DEMO 示例 01 | 虚构、非真实个人数据]\n"
            "今天终于整理好一周的温习计划，还是有点担心进度，"
            "但想试着慢慢来。"
        ),
        "category": "学业",
        "intensity": 1,
        "status": "approved",
        "consent_public": True,
        "ai_reply": (
            "[DEMO 预设回应] 这不是诊断，听起来你正努力找到自己的节奏。"
            "能把计划整理出来已经不容易，也可以给自己留一点休息空间。"
        ),
        "replies": [
            {
                "content": (
                    "[DEMO 示例回复 01 | 虚构、非真实个人数据]\n"
                    "愿意陪你一起慢慢来，不用一次做好所有事情。"
                ),
                "status": "approved",
            },
        ],
    },
    {
        "content": (
            "[DEMO 示例 02 | 虚构、非真实个人数据]\n"
            "家人很关心我的学习，可是我们聊天时常常只谈成绩。"
            "我想学着说出自己的感受。"
        ),
        "category": "家庭",
        "intensity": 2,
        "status": "approved",
        "consent_public": True,
        "ai_reply": (
            "[DEMO 预设回应] 这不是诊断，想让家人听见感受是可以理解的。"
            "愿意的话，可以选一个比较平静的时刻，或找信任的大人陪你表达。"
        ),
    },
    {
        "content": (
            "[DEMO 示例 03 | 虚构、非真实个人数据]\n"
            "最近有时会低落，喜欢的事情也提不起劲。"
            "我想先找一个愿意听我说话的人。"
        ),
        "category": "情绪",
        "intensity": 3,
        "status": "approved",
        "consent_public": True,
        "ai_reply": (
            "[DEMO 预设回应] 这不是诊断，这段日子听起来有些不容易。"
            "你不必独自承担，可以找信任的大人或学校社工说说最近的感受。"
        ),
    },
    {
        "content": (
            "[DEMO 示例 04 | 虚构、非真实个人数据]\n"
            "小组讨论时总怕说错话，想练习主动说一句自己的想法。"
        ),
        "category": "社交",
        "intensity": 2,
        "status": "pending",
        "consent_public": True,
        "ai_reply": (
            "[DEMO 预设回应] 这不是诊断，在意别人怎么看自己并不容易。"
            "可以从一句简单的话开始，也可以和信任的人一起练习。"
        ),
        "replies": [
            {
                "content": (
                    "[DEMO 示例回复 02 | 虚构、非真实个人数据]\n"
                    "你的想法值得被听见，愿意陪你练习说出第一句话。"
                ),
                "status": "pending",
            },
        ],
    },
    {
        "content": (
            "[DEMO 示例 05 | 虚构、非真实个人数据]\n"
            "和家人意见不同的时候，我希望先把感受写下来，暂时不想公开。"
        ),
        "category": "家庭",
        "intensity": 2,
        "status": "pending",
        "consent_public": False,
        "ai_reply": (
            "[DEMO 预设回应] 这不是诊断，想给自己留一些空间是可以理解的。"
            "愿意的时候，可以找信任的大人陪你梳理想说的话。"
        ),
    },
    {
        "content": (
            "[DEMO 示例 06 | 虚构、非真实个人数据]\n"
            "最近压力大到很难继续独自应付，希望现在就有人陪着我，"
            "并帮助我联系信任的大人或学校社工。"
        ),
        "category": "情绪",
        "intensity": 5,
        "status": "crisis",
        "consent_public": True,
        "ai_reply": (
            "[DEMO 预设回应] 这不是诊断，你此刻的感受值得认真对待。"
            "请尽快找信任的大人陪在身边，或向学校社工求助。"
            "如果有即时危险，请联系当地紧急服务。"
        ),
    },
    {
        "content": (
            "[DEMO 示例 07 | 虚构、非真实个人数据]\n"
            "今天在新朋友面前有些紧张，但还是想试着加入话题。"
            "能收到一点鼓励就好了。"
        ),
        "category": "社交",
        "intensity": 2,
        "status": "approved",
        "consent_public": True,
        "ai_reply": (
            "[DEMO 预设回应] 这不是诊断，想靠近别人又有些紧张并不容易。"
            "可以给自己一点时间，从你觉得舒服的小小互动开始。"
        ),
    },
]


def seed_demo(*, reset_demo: bool = False) -> dict[str, int]:
    db.init_db()
    return db.seed_demo_posts(DEMO_POSTS, reset=reset_demo)


def main() -> None:
    parser = argparse.ArgumentParser(description="插入 7 条虚构心声及 2 条虚构回复。")
    parser.add_argument(
        "--reset-demo",
        action="store_true",
        help="仅重建本脚本的示例帖子及其回复/reaction；不会清空其他帖子。",
    )
    arguments = parser.parse_args()
    try:
        result = seed_demo(reset_demo=arguments.reset_demo)
    except (sqlite3.Error, ValueError) as error:
        parser.exit(1, f"示例数据初始化失败：{error}\n")
    print(f"数据库：{db.DB_PATH}")
    print(
        f"帖子：新增 {result['posts_created']}，"
        f"保留已有 {result['posts_skipped']}，"
        f"重建前移除示例 {result['posts_removed']}。"
    )
    print(
        f"回复：新增 {result['replies_created']}，"
        f"保留已有 {result['replies_skipped']}。"
    )
    print("全部为虚构 DEMO 数据；预设回应不代表真实模型调用结果。")
    print("初始示例：01/02/03/07 公开，04/05 待审核，06 危机；05 未同意公开。")
    print("重复运行默认不覆盖审核状态；需要恢复初始状态时使用 --reset-demo。")


if __name__ == "__main__":
    main()
