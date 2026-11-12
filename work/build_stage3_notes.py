"""Generate exact code excerpts and a phase-2-to-phase-3 patch."""

import ast
import difflib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
app_source = (OUTPUTS / "app.py").read_text(encoding="utf-8")
db_source = (OUTPUTS / "db.py").read_text(encoding="utf-8")
app_tree = ast.parse(app_source)
db_tree = ast.parse(db_source)


def excerpts(source, tree, names):
    lines = source.splitlines()
    sections = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
        else:
            continue
        if name in names:
            sections.append("\n".join(lines[node.lineno - 1:node.end_lineno]))
    return "\n\n\n".join(sections)


def block(code, language="python"):
    return f"\n```{language}\n{code}\n```\n"


imports = "\n".join(
    ast.get_source_segment(app_source, node)
    for node in app_tree.body
    if isinstance(node, (ast.Import, ast.ImportFrom))
)
notes = [
    "# 第 3 阶段：完整新增代码与插入位置\n",
    "本项目已经直接更新，无需再次粘贴代码。下面是可逐项核对的代码。\n"
    "只修改 `app.py`、`db.py`；`ai.py` 和 `requirements.txt` 不变。"
    "数据库仍是原有三张表，保留已有数据。\n",
    "## 1. app.py 导入区\n",
    "将原导入区替换为以下内容，保留文件开头的模块说明：\n",
    block(imports),
    "## 2. app.py 常量与求助框\n",
    "放在导入区之后、`write_post_page()` 之前，替换原有 `MACAU_TIMEZONE` 定义。\n",
    block(excerpts(app_source, app_tree, {
        "MACAU_TIMEZONE", "HELP_RESOURCES", "REACTION_LABELS",
        "show_help_resources", "format_time",
    })),
    "## 3. app.py 发帖成功页\n",
    "用下面的函数替换原 `write_post_page()`。AI 判为危机或强度达到 4，"
    "都使用 `crisis` 状态，成功页显示原样求助资源。\n",
    block(excerpts(app_source, app_tree, {"write_post_page"})),
    "## 4. app.py 心声墙\n",
    "删除旧 `wall_page()`，在原位置放入下面三个函数。每次 interaction 会检查"
    "帖子是否仍已通过且同意公开。所有回复先调用现有 `analyze_post()`，"
    "保存后仍为 `pending`，不会自动公开。\n",
    block(excerpts(app_source, app_tree, {
        "reaction_buttons", "reply_form", "wall_page",
    })),
    "## 5. app.py 管理员页面\n",
    "放在新的 `wall_page()` 之后、`main()` 之前。未配置 `ADMIN_PASS`、"
    "未登录或密码错误时，都不读取或显示审核队列。\n",
    block(excerpts(app_source, app_tree, {
        "admin_authenticated", "check_admin_password", "logout_admin",
        "review_buttons", "admin_page",
    })),
    "## 6. app.py 导航\n",
    "用下面函数替换原 `main()`；文件底部的入口调用不变。\n",
    block(excerpts(app_source, app_tree, {"main"})),
    "## 7. db.py 配套更新与危机预警函数\n",
    "数据库操作继续集中在 `db.py`。在 `MAX_CONTENT_LENGTH` 后增加以下常量：\n",
    block(excerpts(db_source, db_tree, {"REACTION_TYPES", "CRISIS_CONDITION"})),
    "替换原 `init_db()`、`create_post()`、`get_approved_posts()`，并在"
    " `if __name__ == '__main__':` 入口之前增加其余函数。"
    "保留原有导入、`DB_PATH`、`MAX_CONTENT_LENGTH`、`_connection()`。\n",
    block(excerpts(db_source, db_tree, {
        "init_db", "create_post", "escalate_crisis_if_needed",
        "get_approved_posts", "get_reaction_counts", "_require_public_post",
        "add_reaction", "create_reply", "get_approved_replies",
        "get_review_posts", "get_review_replies", "review_item",
    })),
    "## 8. 环境变量与启动\n",
    "在 `outputs` 文件夹、已激活虚拟环境的终端设置密码后再启动。"
    "如果服务已经运行，先 Ctrl+C 停止，再设置变量并重新启动。"
    "不要使用示例文字作为真实管理员密码。\n",
    "Mac：\n",
    block(
        'export ADMIN_PASS="替换为足够长的管理员密码"\n'
        'export DEEPSEEK_API_KEY="你的DeepSeek密钥"\n'
        "streamlit run app.py",
        "bash",
    ),
    "Windows PowerShell：\n",
    block(
        '$env:ADMIN_PASS="替换为足够长的管理员密码"\n'
        '$env:DEEPSEEK_API_KEY="你的DeepSeek密钥"\n'
        "streamlit run app.py",
        "powershell",
    ),
    "## 9. 验证与状态边界\n",
    "1. 普通心声提交后为 pending；管理员通过后，只有同意公开的帖子出现在墙上。\n"
    "2. 高强度或 AI 危机帖直接进入 crisis 队列，标红并显示求助框。\n"
    "3. 对公开帖累计点击三次“我有点担心你”，帖子转为 crisis 并退出公开墙；"
    "触发者页面显示该帖编号与求助资源。\n"
    "4. 提交回复后，它只出现在人工队列；通过后公开，退回后不显示。\n"
    "5. AI 判为 crisis 的回复本身仍为 pending，同时让所属帖子转为 crisis。\n"
    "6. 人工通过已有风险的帖子后，不会因读取页面而反复升级；"
    "风险条件仍在时，公开帖保留求助框，后续关怀写入会重新检查阈值。\n"
    "7. 历史风险只做一次迁移；已退回的帖子不会自动复活。\n"
    "8. reaction 是累计点击次数，不是独立人数；此阶段没有跨会话防刷。"
    "简单共享密码只适合原型演示，不是面向未成年人的完整线上安全方案。\n"
    "9. 求助资源文字与号码按用户提供原样保留，未核实其真实性、可用时间或适用范围；"
    "本网站也不提供实时值守或实际通知服务。\n",
]
(OUTPUTS / "STAGE3_CHANGES.md").write_text("\n".join(notes), encoding="utf-8")

patches = []
for name in ("app", "db"):
    before = (ROOT / "work" / f"{name}_stage2.py").read_text(encoding="utf-8")
    after = (OUTPUTS / f"{name}.py").read_text(encoding="utf-8")
    patches.extend(difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{name}.py",
        tofile=f"b/{name}.py",
    ))
(OUTPUTS / "phase3.patch").write_text("".join(patches), encoding="utf-8")
print("Generated STAGE3_CHANGES.md and phase3.patch")
