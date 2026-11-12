# 心声墙：黑客松 Demo

面向澳门青少年的匿名心声原型。只使用 Python、Streamlit、SQLite，
以及通过 `openai` Python SDK 接入的 DeepSeek；拼音兜底使用 `pypinyin`。

仅输入虚构示例，不用于收集真实个人信息。所有输入仍会写入本地数据库，
配置 DeepSeek Key 后，发帖和回复正文还会发送给 DeepSeek。
页脚声明不是自动匿名化或个人信息拦截机制。

## 文件

```text
项目目录/
|-- .venv/                 # 本机已有虚拟环境
|-- outputs/
|   |-- app.py             # 界面、发帖、心声墙、管理员
|   |-- db.py              # 三张表、审核、reaction、危机升级
|   |-- ai.py              # DeepSeek 调用、JSON 校验、拼音与异常兜底
|   |-- seed.py            # 虚构示例初始化，可重复运行
|   |-- requirements.txt
|   |-- heart_wall.db      # 自动生成，与 db.py 相邻
|   |-- DEMO_GUIDE.md      # 三分钟现场演示清单
|   |-- BILINGUAL_CHECK.md # 双语改动与安全回归的验证边界
|   `-- PROJECT_CHECK.md   # 检查结果、已修复问题与原型限制
`-- work/                  # 开发检查与自动化测试，不参与网站运行
```

`STAGE3_CHANGES.md` 和 `phase3.patch` 是第 3 阶段的历史说明与差异，
不是当前完整项目的替换步骤。当前运行以这里的说明为准。

## 本机快速启动

下面命令从项目目录运行，即包含 `outputs` 的文件夹。
当前 Mac 的项目目录为：
`/Users/starmoon/Documents/Codex/2026-11-12/python-streamlit-sqlite-openai-api-ai`。

Mac：

```bash
source .venv/bin/activate
python -m pip install -r outputs/requirements.txt
export ADMIN_PASS="替换为你自己的长密码"
export DEEPSEEK_API_KEY="你的DeepSeek密钥"
python outputs/seed.py
python -m streamlit run outputs/app.py --server.address 127.0.0.1
```

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe -m pip install -r outputs/requirements.txt
$env:ADMIN_PASS="替换为你自己的长密码"
$env:DEEPSEEK_API_KEY="你的DeepSeek密钥"
.\.venv\Scripts\python.exe outputs/seed.py
.\.venv\Scripts\python.exe -m streamlit run outputs/app.py --server.address 127.0.0.1
```

若尚未创建虚拟环境，先执行 `python3 -m venv .venv`（Mac）
或 `python -m venv .venv`（Windows）。

访问终端显示的本地地址；默认端口被占用时，以实际显示的地址为准。
本地演示只绑定 `127.0.0.1`，不将管理员入口暴露到局域网。
停止网站，在启动服务的终端按 Ctrl+C。
环境变量须在启动网站的同一个终端设置；修改后需要重启服务。

## 中英切换与界面

侧边栏最上方的「语言 · Language」可选择「中文」或「English」，
默认中文，选择保存在当前浏览器会话中；重新建立会话时恢复中文。
导航、输入提示、按钮、审核后台、状态提示、页脚和求助框均随语言切换。
柔和背景、分类标签、关怀按钮与 AI 回应卡片由 `app.py` 内的样式统一控制。

所有界面静态文案集中在 `app.py` 的 `TEXT["zh"]`、`TEXT["en"]` 中。
没有引入国际化库或新的前端框架。要求 Streamlit 至少 1.67，
与本次验证环境一致，支持关怀按钮换行，以及语言切换时 keyed 控件的稳定身份。

发帖与回复调用 `analyze_post(text, language="zh")`，界面传入当前语言。
一次 DeepSeek 请求同时做分类、强度、回应和审核；只有 `ai_reply` 的输出语言改变，
分类仍为「学业/家庭/社交/情绪」，状态与审核枚举不翻译。
英文回应的句数校验适配英文句号，仍要求 2–4 句及明确的非诊断说明。
中文/英文均使用原有的规范化、拼音兜底、严格 JSON 校验及异常转人工复核机制。

帖子与回复正文不会翻译，仍按原有数据库规则保存和显示。
已保存的 AI 回应也不会因切换语言而重新生成；新提交才使用当时选定的语言，
切换语言本身不会额外调用 API。示例帖及其预设回应维持原文。
热线号码 `28525222` 原样保留，中英两版均未新增号码或承诺实时响应。

更新代码后，建议在原服务终端按 Ctrl+C 完整重启，确保 `ai.py` 的新接口已加载：

```bash
source .venv/bin/activate
python -m pip install -r outputs/requirements.txt
python -m streamlit run outputs/app.py --server.address 127.0.0.1 --server.port 8506
```

以上命令仍从包含 `outputs` 的项目根目录执行；无需重新运行 seed 或重建数据库。
如果 8506 已占用，改为其他空闲端口。在同一个终端保留原有的环境变量配置。

## 示例数据

运行 `python outputs/seed.py`，创建 7 条虚构帖子、2 条虚构回复。
全部明确标注 DEMO 和非真实个人数据，回应明确标为预设内容，不调用 API。

| 示例标记 | 分类 | 强度 | 初始状态 | 同意公开 | 演示用途 |
| --- | --- | --- | --- | --- | --- |
| 01 | 学业 | 1 | approved | 是 | 公开帖子及已通过回复 |
| 02 | 家庭 | 2 | approved | 是 | 不同分类 |
| 03 | 情绪 | 3 | approved | 是 | 不同强度 |
| 04 | 社交 | 2 | pending | 是 | 人工审核及待审核回复 |
| 05 | 家庭 | 2 | pending | 否 | 即使通过也不公开 |
| 06 | 情绪 | 5 | crisis | 是 | 红色危机队列与求助资源 |
| 07 | 社交 | 2 | approved | 是 | 三次 worried 触发升级 |

“示例 07”是内容里的标签，不保证数据库 `id` 为 7。
默认重复运行只补充缺失的示例，不覆盖现有审核结果或清空关怀次数。
普通网站发帖、AI 判为 safe 的发帖和普通回复均不会自动通过审核；
只有种子脚本为了准备演示，预置了部分 `approved` 数据。

重新彩排前，若要把这些示例恢复初始状态：

```bash
python outputs/seed.py --reset-demo
```

这会删除并重建本脚本的七条精确匹配示例，以及它们下面的回复和 reaction；
不清空其他帖子，但会清除这些示例下彩排时留下的互动。
脚本不会删除额外从网页提交的虚构测试帖。
请勿在存有真实个人内容的环境中进行演示或执行重置。

## 状态与隐私边界

- 心声墙只展示 `approved` 且 `consent_public=1` 的帖子。
- safe、need_review 仍需人工审核；crisis 或强度至少 4 会进入危机队列。
- worried 达到三次，帖子升级为 crisis 并退出公开墙，显示求助资源。
- 回复先经 AI 初步判断，之后一律 pending；只有人工通过才能公开。
- 危机回复本身仍 pending，同时使所属帖子进入 crisis。
- 人工重新通过危机帖子后，不会因刷新反复升级；后续关怀写入会重新检查。
- 管理员密码读取 `ADMIN_PASS`；未配置时默认关闭，没有内置密码。
- 缺少 DeepSeek Key、网络异常、模型格式错误时，使用通用回应并转人工复核。
- 共享密码没有完整账号体系、跨会话防刷或全局登录限流；只适合本地原型。
- 数据库是明文存储，不要上传公开仓库。不要公开真实 Key 或管理员密码。
- 求助资源按项目发起人提供的文字原样保留，号码及可用性尚未核实。
- 本项目没有实时值守、报警通知或专业危机干预服务。

## 开发检查

在项目目录使用已安装依赖的虚拟环境：

```bash
python -m unittest discover -s work -p "test_*.py" -v
```

测试使用临时数据库和模拟 HTTP，不需要真实 Key，不消耗 API 额度，
也不会向演示数据库写入测试数据。真实服务的网络、额度和模型可用性，
需要演示前使用虚构文本单独试跑。

双语更新后，原有 86 项测试未修改，新增 24 项双语回归测试，共 110 项通过。
检查覆盖英文危机处理、异常兜底、花字/谐音、人工审核、私密内容不公开、
第三次 worried 升级和切换语言不额外请求 API。
这些是模拟服务返回的自动化检查，不是对真实 DeepSeek 危机语义识别能力的保证。
