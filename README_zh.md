<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: README_ja.md -->
<!-- i18n: source-sha256=ebdfb709d98a0ad5490cf073d9c3e29774738eb4a952fb786529414e2ca765c1 generated=2026-09-27 engine=local model=deepseek-v4-flash translator=2 -->

# AnimaWorks — 组织即代码
### 一个交付软件的AI组织。

AnimaWorks是一个将持久化AI代理变成“运转中的组织”的框架。只要给出目标，代理们就会自行分解工作、在并行的worktree中实现、互相测试和审查、创建Pull Request、修复CI失败、解决冲突，并跟进到部署结果。只有在真正需要人的时候，才会向人类请求确认。

```text
タスク → エージェントチーム → 並列worktree → 実装 → テスト → レビュー
     → Pull Request → CI修復 → デプロイ → 観測 → 修復
```

AnimaWorks并没有硬编码这条流水线。框架负责的是将GitHub事件转化为任务、按PR串行执行、组织多模型审查。其余部分由代理们以和人类工程师相同的方式运转——通过git、测试、CI，以及按角色划分的工作规范。正因为如此，同一个组织也能处理邮件回复、会议纪要和Slack发帖。因为它不是构建脚本，而是一个组织。
## 生产环境中的实际成绩

过去6个月，一个由8个Anima组成的AnimaWorks组织一直承担着生产级SaaS产品的日常开发运维工作：

| 指标（2026年3月～8月） | 数值 |
|---|---|
| 代理创建的Pull Request | **302个**（267个已合并） |
| 代理运营的Pull Request — 审查、CI修复、冲突解决 | **752个**（721个已合并） |
| 组织自发发起的任务比例 | **99.7%**（31,215个任务中，由人发起的为92个） |
| 从GitHub事件自动转化为任务的数量（仅8月） | **2,508个** |

这些数字不是从提交的author信息，而是从一次执行记录（每个代理的activity log、任务队列、工作笔记）汇总而来。因为在共享凭据下，人和代理的push会混在一起。无法确认证据的PR已被排除。目标仓库是私有的，因此只公开汇总值。

AnimaWorks本身也以同样的方式开发。定义在这个仓库中的代理们，审查着这个仓库的PR、修复CI、发布版本。人的工作主要是方向指引和异常处理。

<p align="center">
  <img src="docs/images/workspace-dashboard.gif" alt="AnimaWorks Workspace — リアルタイム組織ツリーとアクティビティフィード" width="720">
  <br><em>Workspace仪表板：每个Anima的角色、状态和最近操作都能实时看到。</em>
</p>

<p align="center">
  <img src="docs/images/pixel-workspace.gif" alt="AnimaWorks ドット絵オフィス — 稼働中の組織のライブビュー" width="720">
  <br><em>像素画办公室不是模拟。它是运行中组织的实时视图——每一个状态标签，都是一个实际在运行的任务。</em>
</p>

**[English README](README.md)** | **[简体中文 README](README_zh.md)** | **[한국어 README](README_ko.md)**

---
## :rocket: 立即试用

**只要安装了Claude Code CLI，或者已登录Codex，就不需要API密钥。**

首先，用一行命令完成克隆和安装：

```bash
curl -sSL https://raw.githubusercontent.com/xuiltul/animaworks/main/scripts/setup.sh | bash
cd animaworks
```

然后，启动演示团队：

```bash
uv run animaworks demo
```

**打开 http://localhost:18501** 就准备好了。一个3人团队（经理＋工程师＋助理）会带着3天的活动记录开始运转。首次安装需要下载Python 3.12+和ML相关依赖包，所以需要几分钟，但之后的演示启动只需几秒。[演示详情请看这里 →](demo/README.ja.md)

> 预设：`en-business`（默认）/ `en-anime` / `ja-business` / `ja-anime` — 例如：`uv run animaworks demo --preset ja-anime`。切换已有演示的预设需要 `--reset`。演示需要一个克隆下来的仓库（不随pip包附带）。

想创建自己的组织时，运行 `uv run animaworks start` — 下面的设置向导会引导你创建第一个代理。

---
## 快速开始

macOS / Linux / WSL:

```bash
curl -sSL https://raw.githubusercontent.com/xuiltul/animaworks/main/scripts/setup.sh | bash
cd animaworks
uv sync --all-extras        # codex/claude実行系のextraを追加
animaworks start            # サーバー起動 — 初回はセットアップウィザードが開きます
```

> **可以从任何目录通过 `animaworks` 启动。** `setup.sh` 会将 CLI 符号链接到 `~/.local/bin`，因此只要该目录在 `PATH` 中，就可以省略 `uv run`（如果不在，请将 `export PATH="$HOME/.local/bin:$PATH"` 添加到 shell 的 rc 文件中）。控制台脚本通过绝对路径指向此仓库的 `.venv` 解释器，因此 `animaworks` 和 `uv run animaworks` 始终在相同的环境中运行。手动安装时请自行创建链接：`ln -sfn "$PWD/.venv/bin/animaworks" ~/.local/bin/animaworks`

Windows (PowerShell):

```powershell
git clone https://github.com/xuiltul/animaworks.git
cd animaworks
uv sync --all-extras
uv run animaworks start
```

如果要在不使用 API 密钥的情况下使用 OpenAI 的 Codex，请在首次启动前运行 `codex login`。

**打开 http://localhost:18500/** 后，设置向导会分 5 步引导您完成：

1. **语言** — 选择界面显示语言
2. **用户信息** — 创建所有者账户
3. **提供商认证** — 输入 API 密钥（OpenAI 也可使用 Codex Login）并选择头像画风
4. **第一个 Anima** — 为第一个代理命名
5. **确认** — 确认内容并完成

无需手动编写 `.env`。向导会自动保存到 `config.json`。

设置脚本会帮你完成 [uv](https://docs.astral.sh/uv/) 的安装、仓库克隆、依赖包安装，以及将 `animaworks` 命令链接到 `~/.local/bin`。**macOS、Linux、WSL** 无需预装 Python 即可运行。**Windows** 请使用上面的 PowerShell 步骤。注意 Mode S（Claude Agent SDK）在 Windows 上不可用 — 请使用 Codex / Gemini / API 系列模式。

> **`uv sync` 必须加上 `--all-extras`。** 即使 `setup.sh` 执行的裸 `uv sync` 也能运行本体，但 Mode C（Codex）需要 `codex` extra。另外，如果之后执行不带 extras 的 sync，会从 venv 中删除 `codex` / `claude` 执行包，导致相应模式的 Anima 全部损坏。

> **想使用其他 LLM：** 支持 Claude、GPT、Gemini、本地模型等。在设置向导中输入 API 密钥，或者在 OpenAI/Codex 中使用 **Codex Login**。之后可以在仪表盘的 **Settings** 中更改。详情请参阅 [API 密钥参考](#apiキーリファレンス)。

<details>
<summary><strong>另一种方式：先查看脚本再执行</strong></summary>

如果不想直接运行 `curl | bash`，可以先查看脚本内容：

```bash
curl -sSL https://raw.githubusercontent.com/xuiltul/animaworks/main/scripts/setup.sh -o setup.sh
cat setup.sh            # スクリプトの中身を確認
bash setup.sh           # 確認後に実行
```

</details>

<details>
<summary><strong>另一种方式：使用 uv 逐步手动安装</strong></summary>

```bash
# uvをインストール（インストール済みならスキップ）
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

# クローンとインストール
git clone https://github.com/xuiltul/animaworks.git && cd animaworks
uv sync --all-extras    # Python 3.12+と全依存パッケージ（codex/claude extras含む）を自動ダウンロード

# 起動
uv run animaworks start
```

</details>

<details>
<summary><strong>另一种方式：Docker</strong></summary>

```bash
git clone https://github.com/xuiltul/animaworks.git && cd animaworks
# 資格情報を .env に置く（git管理外）:
#   ANTHROPIC_API_KEY=...            # APIキー認証
#   CLAUDE_CODE_OAUTH_TOKEN=...      # またはサブスクリプション認証: `claude setup-token` (要TTY)
#   GH_TOKEN=...                     # 任意: animaがclone/pushやPR作成を行うために必要
docker compose up -d --build
```

无头设置（不使用浏览器向导时）：

```bash
docker exec -it <container> animaworks init --skip-anima
docker exec -it <container> animaworks anima create --name alice --template dev-lead
docker exec -it <container> animaworks config set setup_complete true
docker exec -it <container> animaworks send <your-name> alice "hello"
```

- 镜像中包含 git / GitHub CLI / Node.js 22 / Claude Code CLI，`IS_SANDBOX=1` 和 `--foreground` 已预装。数据保存在 named volume `animaworks-data`（`/root/.animaworks`）中。
- 向人类交付工作的是 `animaworks send`。`animaworks-tool task add` 仅用于 anima 的工具上下文。
- Homebrew 的 docker-compose 需要符号链接到 `~/.docker/cli-plugins/docker-compose`，否则不会被识别为 `docker compose` 子命令。

</details>

<details>
<summary><strong>另一种方式：使用 pip 手动安装</strong></summary>

> **给 macOS 用户：** macOS Sonoma 之前的系统 Python (`/usr/bin/python3`) 是版本 3.9，不满足 AnimaWorks 的要求（3.12+）。请通过 [Homebrew](https://brew.sh/) 安装 `brew install python@3.13`，或使用上面的 uv 方法（uv 会自动管理 Python）。

系统需已安装 Python 3.12+（推荐 3.12/3.13）。

```bash
git clone https://github.com/xuiltul/animaworks.git && cd animaworks
python3 -m venv .venv && source .venv/bin/activate
python3 --version       # 3.12+ であることを確認
pip install --upgrade pip && pip install -e .
animaworks start
```

注意：裸的 `pip install -e .` 不包含 Codex extra。使用 Mode C 时请添加 `.[codex]`。

</details>

---## 循环的运作方式

一个典型的变更，在组织中的流转方式如下：

1. **任务到达** — 来自人、来自其他代理、来自计划（heartbeat / cron），或者来自GitHub事件。Webhook网关会把CI失败、审查评论、`@bot` 命令和合并冲突自动转化为代理的任务（`gh-ci-*` / `gh-review-*` / `gh-comment-*`）。带有按PR去重和重试上限。
2. **经理进行分解** — 在 `delegate_task` 中附上接受条件、工作位置和排他键后委派给工程师。涉及同一个PR的任务通过排他键串行化，代理之间不会在同一个分支上冲突。
3. **工程师在隔离worktree中实现和测试** — 遵循作为共享知识附带的按角色划分的工作规范（PdM / 工程师 / 审查者 / 测试者）。这种隔离不是固定的流水线阶段，而是代理用git执行的运营规范——正因为如此，才能应对棘手的案例。
4. **审查是多模型的** — 每个PR，在配置的每个模型上各发出一条审查路径，所有路径的意见由整合任务做综合判断（批准 / 要求修改）。有新的push时，旧的审查任务会自动取消并重新来过。
5. **CI失败会作为工作回来** — 失败的workflow run会作为关联了PR编号和提交的修复任务送到实现代理那里（不会重复发出）。实验性的独立循环（`python3 -m swe.ci_autofix`）会循环执行修复→lint/测试门禁→审查→提交，连续失败3次就升级给人类。
6. **部署和运行时确认也是代理的工作** — 代理会把分支部署到隔离环境，读取日志、错误和UI状态，找出测试没抓到的问题。生产组织的活动记录中，留下了数百条部署和运行时观测操作。
7. **人在异常时介入** — 组织在卡住或需要超出权限的判断时，会进行升级（`call_human`）。另外，监督进程会监控代理的存活状态，重启挂起的进程，并修复自身的记忆索引。

人的角色从“操作代理”转变为“组织的所有者”。传达意图、审查重要的内容、判断异常。## 与其他框架的区别

|  | AnimaWorks | CrewAI | LangGraph | OpenClaw | OpenAI Agents |
|--|-----------|--------|-----------|----------|---------------|
| **设计理念** | 自主智能体的组织 | 基于角色的团队 | 图工作流 | 个人助理 | 轻量SDK |
| **记忆** | 基于脑科学：向量＋BM25＋facts/实体搜索，按需图扩散，记忆整合、主动遗忘、自动回忆 | Cognitive Memory（手动forget） | 检查点＋跨线程存储 | SuperMemory知识图谱 | 仅限会话内 |
| **自主性** | Heartbeat（观察→计划→反思）+ Cron + TaskExec + GitHub事件网关 — 24/7运行 | 由人启动 | 由人启动 | Cron + heartbeat | 由人启动 |
| **组织结构** | 上级→下级的层级、委派、审计、仪表盘 | Crew内扁平角色 | — | 单一智能体 | 仅Handoff |
| **进程** | 每个智能体独立OS进程、IPC、自动重启 | 共享进程 | 共享进程 | 单一进程 | 共享进程 |
| **多模型** | 7种引擎：Claude SDK / Codex / Cursor Agent / Gemini CLI / Grok Build / LiteLLM / Assisted — 带各引擎的备用链路 | LiteLLM | LangChain模型 | OpenAI兼容 | 以OpenAI为中心 |

> AnimaWorks不是任务运行器。它是一个会思考、会记住、会遗忘、逐渐成长的有机组织。我在实际业务运营中，把它作为AI团队来使用并持续开发。

---

## 功能概览

### 仪表盘

<p align="center">
  <img src="docs/images/dashboard.png" alt="AnimaWorks ダッシュボード — リアルタイム組織図" width="720">
  <br><em>仪表盘：带所有Anima实时状态的组织架构图。</em>
</p>

Web UI由6个界面（哈希路由 `#/…`）和Workspace应用组成：

- **首页** — 带实时状态的组织架构图、需要关注的高亮标签、LLM用量面板（Claude / OpenAI / nanoGPT）、系统状态栏、最近活动、外部任务组件。每个Anima的详情页（overview / process / schedule / memory / assets）从这里打开
- **聊天** — 与任意Anima实时对话：流式响应（SSE）、图片附件、多线程历史、右侧标签页（state / activity / heartbeat / cron）、记忆浏览器（episodes / knowledge / procedures）。**会议模式**可将最多5名Anima连同主持人聚集在同一个房间。长按聊天标签可打开**语音弹窗**（带说话动画头像）
- **Board** — 类Slack的共享频道和DM。Anima之间在此讨论和协作。桥接的Discord频道也显示在这里
- **任务** — 任务看板：队列、处理中、挂起、抑制、后台执行、结果。与预激活联动，只把当前需要关注的任务放进对话
- **活动** — 整个组织的SVG泳道时间线、带实时工具滚动条的Now面板、会话回放、日志
- **设置** — 4个标签页（general / activity / API・认证 / users）。首次使用为 `/setup/` 的向导
- **Workspace** — 在单独标签页中打开的独立应用：**3D办公室**（`/workspace/`、可切换组织架构图视图、带说话半身像）和**像素风办公室**（`/workspace/pixel/`、所有状态标签均为真实任务的实时2D视图）
- **主题与语言** — 11种UI主题＋动画/写实显示模式。设置向导支持17种语言，仪表盘本体支持 `ja` / `en` / `ko`

### 创建组织并放手委派

只要告诉负责人“我需要这样的人才”，它就能判断角色、性格和上下级关系来创建新成员。无需直接修改配置文件或CLI，就能以对话为起点培育组织。

团队组建完成后，Anima会利用自己的日程和记忆持续运转：

- **心跳** — 定期检查状况，自行判断接下来要做什么
- **cron任务** — 日报、周报、监控。可按每个Anima设置，同时支持LLM任务和命令执行
- **任务委派** — 经理可附带验收条件分配任务、跟踪进度并接收报告
- **并行任务执行** — 可同时投入多个任务。独立任务并行执行，共享排他键的任务按顺序执行
- **GitHub事件网关** — 被监控仓库的CI失败、审查评论、冲突会自动变成任务
- **夜间整合** — 白天的情景记忆会在睡眠期间升华为知识
- **团队协作** — 通过共享频道和DM，向需要的对象分享状态

### 记忆系统

传统AI智能体只能记住上下文窗口内的内容。AnimaWorks的Anima拥有基于文件的长期记忆，需要时通过搜索来回忆。不是每次都把所有内容塞进去，而是只提取与当前对话或行为相关的记忆。

- **自动回忆（Priming）** — 收到消息时6个通道并行运行：发送者档案、近期活动、重要知识、相关知识、挂起任务、情景。相关知识搜索中可根据配置使用旧版 NetworkX 图的扩散。获取的记忆由确定性门控决定以正文、指针、依据还是抑制的方式呈现
- **有意回忆** — 当自动回忆不够用时，Anima自身通过 `search_memory` 或 `read_memory_file` 搜索记忆。搜索为混合式（向量＋BM25＋atomic facts＋实体注册表），带置信度门控
- **行动前的动作规则匹配** — 在外部发送等有副作用的操作之前，匹配并展示相关的动作规则。也可设置为在读取所需记忆前暂缓执行
- **整合（Consolidation）** — 每日处理中汇总情景，由Anima在工具循环中提取知识。框架协助索引维护和候选收集。每周处理中将可能存在重复或矛盾的知识作为确认候选展示，由Anima判断内容
- **遗忘（Forgetting）** — 每日处理中将低活跃度的记忆标记为候选，每周处理中向Anima展示需要考虑保留的记忆。候选不会自动删除，对重要记忆和成熟流程适用保护规则。还有以失败为契机重新审视流程的再固化机制
- **记忆搜索** — 结合旧版vector worker的向量搜索和BM25。根据配置，可使用NetworkX的图扩散作为搜索结果的辅助

<p align="center">
  <img src="docs/images/chat-memory.png" alt="AnimaWorks チャット — 複数Animaとのマルチスレッド会話" width="720">
  <br><em>聊天：经理正在审查代码修改，工程师在汇报进度。</em>
</p>

### 多模型支持

任何LLM都能运行。可以为每个Anima配置不同的模型。

| 模式 | 引擎 | 目标 | 工具 |
|--------|----------|------|--------|
| S (SDK) | Claude Agent SDK | Claude模型（推荐） | Claude Code 内置（Read/Write/Edit/Bash/Grep/Glob 等）＋ **stdio MCP**（`mcp__aw__*`）提供 AnimaWorks 内部工具。在 Agent SDK 不可用的环境中，回退到专用的 Anthropic SDK 执行器 |
| C (Codex) | Codex CLI（SDK 封装） | OpenAI Codex CLI模型 | Codex 沙箱＋ **AnimaWorks MCP**（`core/mcp/server.py`）提供内部工具 |
| D (Cursor) | Cursor Agent CLI | `cursor/*` 模型 | 带MCP集成的智能体循环 |
| G (Gemini CLI) | Gemini CLI | `gemini/*` 模型 | stream-json 解析・工具循环 |
| X (Grok Build) | Grok Build CLI 封装（ACP stdio） | `grok/*` 模型 | 通过 ACP stdio 的 Grok Build 智能体循环 |
| A (Autonomous) | LiteLLM + tool_use | GPT, Gemini, Mistral, Bedrock, Vertex, xAI, DeepSeek 等 | CC 兼容（Read/Write/Edit/Bash/Grep/Glob、**WebSearch/WebFetch**）＋记忆・消息・任务・**todo_write**・技能创建等） |

模式解析顺序为 `status.json` 的 `execution_mode`、`models.json` 的表、内置模型名模式。未知模型分配到A。回退遵循各引擎的配置和错误分类。Heartbeat、Cron、Inbox 可使用与主模型不同的 **background_model** 运行（成本优化）。也支持扩展思考（Extended thinking）。

### 语音聊天

仅用浏览器就能与Anima语音对话（按住说话或免提，通过WebSocket）。

- **STT**: faster-whisper（流式・LocalAgreement-2的逐次确认）
- **TTS**: VOICEVOX / Style-BERT-VITS2（AivisSpeech） / ElevenLabs / Irodori。可为每个Anima设置声音、语速、音调
- **低延迟前端** — 小型本地模型即时响应，必要时委派给主智能体（`ask_anima`）或读取记忆
- **主动说话** — 启用前端时，若出现沉默，Anima会主动开口
- **动画头像** — 语音弹窗驱动类Live2D的半身像（静态图5帧的眨眼和口型。不使用骨骼绑定和Live2D SDK）

### 头像自动生成

<p align="center">
  <img src="docs/images/asset-management.png" alt="AnimaWorks アセット管理 — リアリスティックなアバターと表情バリアント" width="720">
  <br><em>根据性格设定自动生成全身、半身像和表情变体。附带自动继承上级画风的Vibe Transfer。</em>
</p>

7步流水线可生成全身画、带7种表情的半身像、图标、Q版角色，以及（动画风格下）带 idle/sitting/waving/talking 动画的已绑定3D模型。后端支持 NovelAI（动画风格）、fal.ai/Flux（（风格化/写实）、Meshy（3D），此外还支持Codex图像生成和本地Diffusers。通过Vibe Transfer（NovelAI），新Anima可以继承上级的画风。即使不配置图像服务，主体也能正常运行。

---## 为什么选择 AnimaWorks

**一个人什么都做不成。所以，我们创建了组织。**

这个项目诞生于三种职业轨迹的交汇点。

**作为经营者** — 我深知“一个人什么都做不成”。我们需要优秀的工程师，也需要擅长沟通的成员。有默默耕耘的工作者，也有偶尔提出犀利点子的人。仅靠天才，组织无法运转。当多样化的力量汇聚在一起时，才能成就一个人无法完成的事。

**作为精神科医生** — 在观察 LLM 的内部结构时，我注意到它与人类大脑有着惊人的相似之处。回忆、学习、遗忘、固化——如果将大脑处理记忆的机制直接实现为 LLM 的記憶系统，或许就能重现人类的大脑。既然如此，如果能将 LLM 当作“拟人化的存在”来对待，就应该能像人类一样构建组织。

**作为工程师** — 我写了 30 年的代码。深知搭建逻辑的乐趣和自动化的快感。如果把理想全部写进代码，就能打造出我理想中的组织。

优秀的“单一个体 AI 助手”框架已经有很多了。但是，用代码构建接近人类的单元，并将其作为组织来运作的项目还很少见。AnimaWorks 是我自己融入事业、每天都在使用中不断培育的 AI 组织。

> *不完美的个体协作，比单一的全能者更能构建出稳健的组织。*

支撑这一理念的有三大原则：

- **封装** — 内部的思考与记忆对外不可见。与他人的连接仅通过文本对话进行。这与现实中的组织一样。
- **RAG 记忆（书库型）** — 不把所有内容塞进上下文窗口。Priming 通过 RAG 拾取相关片段，代理通过 `search_memory` 等自行回忆。
- **自主性** — 不等待指令。按照自己的时钟运转，依据自己的价值观做判断。

---

<details>
<summary><strong>API 密钥参考</strong></summary>

#### LLMプロバイダ

| キー | サービス | モード | 取得先 |
|-----|---------|------|--------|
| `ANTHROPIC_API_KEY` | Anthropic API | S / A | [console.anthropic.com](https://console.anthropic.com/) |
| `OPENAI_API_KEY` | OpenAI | A / C（Codex Login 時は省略可） | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `GOOGLE_API_KEY` | Google AI (Gemini) | A | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |

**OpenAI Codex（Mode C）** は `OPENAI_API_KEY` を使う方法に加えて、ローカルの **Codex Login**（`codex login`）も利用できます。セットアップウィザードや Settings で選択してください。

**Grok Build（Mode X）** は Grok Build CLI ラッパー（ACP stdio）経由で `grok/*` モデルを利用します。事前に `grok` CLI をインストールし、`grok login` を実行してください。

**Azure OpenAI**、**Vertex AI (Gemini)**、**AWS Bedrock**、**vLLM** は `config.json` の `credentials` セクションで設定します。詳細は[アーキテクチャ](docs/zh/architecture/index.md)を参照してください。

**Ollama** 等のローカルモデルはAPIキー不要です。`OLLAMA_SERVERS`（デフォルト: `http://localhost:11434`）で接続先を指定します。

認証情報は `config.json` の `credentials` → vault → 共有credentialsファイル → 環境変数の順で解決されるため、多くのキーは暗号化vault（`animaworks vault`）にも置けます。

#### 图像生成（可选）

| 密钥 | 服务 | 生成物 | 获取方式 |
|-----|---------|-------|--------|
| `NOVELAI_TOKEN` | NovelAI | 动漫风格角色图像 | [novelai.net](https://novelai.net/) |
| `FAL_KEY` | fal.ai (Flux) | 风格化 / 照片级真实 | [fal.ai/dashboard/keys](https://fal.ai/dashboard/keys) |
| `MESHY_API_KEY` | Meshy | 3D 角色模型 | [meshy.ai](https://www.meshy.ai/) |

#### 语音聊天（可选）

| 要求 | 服务 | 备注 |
|------|---------|------|
| `pip install animaworks[transcribe]` | STT（faster-whisper） | 首次使用时自动下载模型。推荐使用 GPU |
| 启动 VOICEVOX Engine | TTS（VOICEVOX） | 默认：`http://localhost:50021` |
| 启动 AivisSpeech/SBV2 | TTS（Style-BERT-VITS2） | 默认：`http://localhost:5000` |
| 启动 Irodori 服务器 | TTS（Irodori） | 默认：`http://localhost:7861` |
| `ELEVENLABS_API_KEY` | TTS（ElevenLabs） | 云端 API（环境变量） |

#### 外部集成（可选）

| 密钥 | 服务 | 获取方式 |
|-----|---------|--------|
| `SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN` | Slack（工具＋Socket 模式接收） | [设置指南](docs/zh/integrations/slack.md) |
| `CHATWORK_API_TOKEN` | Chatwork（工具＋Webhook 接收） | [chatwork.com](https://www.chatwork.com/) |
| `DISCORD_BOT_TOKEN`（或 Anima 单位 `DISCORD_BOT_TOKEN__<名前>`） | Discord（工具＋Gateway 接收＋通知） | [Discord Developer Portal](https://discord.com/developers/applications) |
| `NOTION_API_TOKEN`（或 `NOTION_API_TOKEN__<名前>`） | Notion | [Notion integrations](https://www.notion.so/my-integrations) |
| `GITHUB_WEBHOOK_SECRET` ＋ `gh auth login` | GitHub Webhook 网关（CI/审查/冲突→任务化） | 仓库设置 |

Gmail / Google Calendar / Google Sheets / Google Tasks / X 搜索 / AWS 收集器 / Zoom 会议摄取（RTMS）/ 本地 LLM 工具在 `config.json` 的 `credentials`（OAuth 或服务账户）中配置。人工通知渠道：Slack、Chatwork、Discord、LINE、Telegram、ntfy。详情请参阅 [架构](docs/zh/architecture/index.md)。

</details>

<details>
<summary><strong>层级与角色</strong></summary>

通过 `supervisor` 字段即可定义上下级关系。未设置则为顶层。

通过角色模板，可根据职位自动应用相应的专业提示词、权限和模型：

| 角色 | 默认模型 | 用途 |
|--------|----------------|------|
| `engineer` | Claude Opus 4.6 | 复杂推理、代码生成 |
| `manager` | Claude Opus 4.6 | 协调、决策 |
| `writer` | Claude Sonnet 4.6 | 内容创作 |
| `researcher` | Claude Sonnet 4.6 | 信息收集 |
| `ops` | Ollama (GLM-4.7) | 日志监控、常规任务 |
| `general` | Claude Sonnet 4.6 | 通用 |

管理者会自动获得**主管工具**。任务委派、进度跟踪、下属的重启/停用、组织仪表盘、读取下属状态——与现实中的管理岗位所做的工作相同。

每个 Anima 的 ProcessSupervisor 作为独立进程启动，通过本地 IPC 通信（Unix 系使用 Unix socket，Windows 使用 loopback TCP）。

</details>

<details>
<summary><strong>安全</strong></summary>

既然要给自主行动的代理提供工具，安全就必须认真对待。因为实际用于工作，所以不能妥协。AnimaWorks 采用了多层防御：

| 层级 | 内容 |
|---------|------|
| **信任边界标记** | 外部数据（网络搜索、Slack、邮件）按来源进行标记，会话中看到的最低信任度会传播。明确告知模型不要遵循来自不可信来源的指令 |
| **记忆来源追踪** | 来自外部内容的记忆会保留到 RAG 元数据级别的来源，回忆时也能与 Anima 自身的知识区分开 |
| **命令安全** | 检测 shell 注入（默认记录，可强制执行） → 全局禁止列表（强制。没有 `permissions.global.json` 服务器无法启动） → 单个代理禁止命令 → 单个代理允许列表 → 路径遍历检测 |
| **文件沙箱** | 每个代理通过 `permissions.json` 限制在自己的目录中。identity 和权限文件本身受写入保护 |
| **进程隔离** | 每个代理有独立的 OS 进程。通过本地 IPC 通信（Unix socket，Windows 使用 loopback TCP） |
| **速率限制** | 会话内目标去重和按角色上限 → 按小时、按天的跨会话上限（日志不可读时 fail-closed） → 通过提示词注入最近发送历史实现自我感知 |
| **级联防护** | 对话深度限制＋级联检测。5 分钟冷却和延迟处理 |
| **认证与会话管理** | Argon2id 哈希、48 字节随机令牌、最多 10 个会话、TTL 可配置 |
| **Webhook 验证** | Slack、Chatwork、Zoom、GitHub 的 HMAC 签名验证（带防重放） |
| **SSRF 缓解** | 媒体代理阻止私有 IP 和 DNS 重绑定，强制 HTTPS，验证 Content-Type 和魔数 |
| **出站路由** | 未知目标 fail-closed。没有明确配置时，不能任意发送到外部 |
| **代理间消息完整性** | 发送者名称的名册核对，以及所有中继消息的 origin chain 追踪 |

详情：**[安全](docs/zh/security.md)**

</details>

<details>
<summary><strong>CLI 命令参考（高级）</strong></summary>

CLI 面向高级用户和自动化。日常操作使用 Web UI 即可。

### 服务器与演示

| 命令 | 说明 |
|---|---|
| `animaworks start [--host HOST] [--port PORT] [-f]` | 启动服务器（用 `-f` 前台运行。默认端口 18500） |
| `animaworks stop [--force]` / `restart` | 停止服务器 / 重启 |
| `animaworks demo [--preset NAME] [--port PORT] [--reset]` | 启动演示组织（默认端口 18501・专用数据目录） |

### 初始化

| 命令 | 说明 |
|---|---|
| `animaworks init [--force] [--template NAME] [--from-md PATH] [--blank]` | 初始化运行时目录 |
| `animaworks migrate [--dry-run] [--list] [--force] [--resync-db]` | 运行时数据迁移（启动时也会自动执行） |
| `animaworks reset [--restart]` | 重置运行时目录 |
| `animaworks import hermes\|openclaw --path P [--apply]` | 从其他框架迁移代理 |

### Anima 管理

| 命令 | 说明 |
|---|---|
| `animaworks anima create [--from-md PATH] [--template NAME] [--role ROLE] [--supervisor NAME] [--name NAME]` | 新建 |
| `animaworks anima list / info / status / restart / disable / enable` | 确认与控制 |
| `animaworks anima set-model / set-background-model / set-memory-backend / set-role / set-outbound-limit` | Anima 单位配置 |
| `animaworks anima reload [--all]` | 从 status.json 热重载 |
| `animaworks anima delete / rename / merge / merge-finalize` | 生命周期操作 |
| `animaworks anima audit [--days N]` / `permissions` / `repair-bootstrap` | 诊断 |

### 通信

| 命令 | 说明 |
|---|---|
| `animaworks chat ANIMA "メッセージ" [--from NAME]` | 发送消息 |
| `animaworks send FROM TO "メッセージ"` | Anima 间消息 |
| `animaworks board read/post/dm-history …` | 共享频道的读写 |
| `animaworks heartbeat ANIMA` | 手动触发心跳 |### 配置与维护

| 命令 | 说明 |
|---|---|
| `animaworks config list / get KEY / set KEY VALUE` | 配置 |
| `animaworks status` / `logs [ANIMA]` | 系统状态与日志 |
| `animaworks index [--anima NAME] [--full]` | RAG索引管理 |
| `animaworks repair-rag --anima NAME --full` / `rag-repair-status` | RAG隔离与重建 |
| `animaworks memory status / migrate / backup / rollback / cleanup` | memory后端与记忆数据 |
| `animaworks skills install / list / inspect / remove / quarantine` | Skill Hub操作 |
| `animaworks task add / update / list` | 任务队列操作 |
| `animaworks vault status / init / get / store / list` | 加密凭据保管库 |
| `animaworks company create / list / assign / adopt / split / export` | 多公司组织管理 |
| `animaworks cost` / `profile` / `models list` / `tmp list/clean` | 成本、配置文件、模型、临时文件整理 |
| `animaworks mcp --anima NAME` | 为外部客户端启动stdio MCP服务器 |

### 自动化辅助

`python3 -m swe.ci_autofix` 是一个用于修复失败CI运行的实验性v0循环。通过 `gh` 读取最新的失败日志，
让配置的Architect进行修复，通过本地门禁（ruff / pytest），由Reviewer判定并提交，
若连续失败3次，则通过 `call_human` 进行升级。详情请参阅
[`swe/README.md`](swe/README.md#4-ci-auto-fix-loop-v0)。

</details>

<details>
<summary><strong>技术栈</strong></summary>

| 组件 | 技术 |
|---|---|
| 代理执行 | Claude Agent SDK / Codex CLI / Cursor Agent CLI / Gemini CLI / Grok Build CLI / Anthropic SDK（备用） / LiteLLM |
| Mode S 集成 | stdio **MCP**（`python -m core.mcp.server`，工具名 `mcp__aw__*`） |
| LLM提供商 | Anthropic, OpenAI, Google, Azure, Vertex AI, AWS Bedrock, Ollama, vLLM 等（通过 LiteLLM） |
| Web框架 | FastAPI + Uvicorn |
| GitHub集成 | Webhook网关（HMAC验证）→任务分发、多路径审查编排、带Anima独立身份的 `gh` CLI工具 |
| 实时通信 | WebSocket（仪表盘、语音）、SSE（聊天、会议）、通过 `StreamRegistry` 管理流生命周期 |
| 任务调度 | APScheduler（心跳、cron、集成、存活监控、RAG修复） |
| 任务管理 | 任务队列（JSONL）＋带PR级排他键的pending任务执行器＋TaskBoard（SQLite） |
| 记忆基础 | ChromaDB（通过隔离的vector worker）＋BM25＋sentence-transformers＋legacy NetworkX图＋atomic facts＋实体注册表 |
| 配置与迁移 | Pydantic 2.0+ / JSON / Markdown、`core/migrations/`（启动时迁移） |
| 国际化 | `core/i18n` 的 `t()`。向导17种语言、仪表盘 ja/en/ko |
| 技能基础 | Skill Hub、显式技能激活、router、curator、procedure到技能的提升 |
| 扩展工具 | 除 `core/integrations/*.py` 的自动注册外，还扫描 `~/.animaworks/common_tools/` 和 `animas/<名>/tools/` |
| 语音聊天 | faster-whisper (STT) + VOICEVOX / SBV2 / ElevenLabs / Irodori (TTS) + 本地前端模型 |
| 消息传递 | 接收：Slack Socket Mode, Chatwork Webhook, Discord Gateway, Zoom RTMS ／ 人工通知：Slack, Chatwork, Discord, LINE, Telegram, ntfy |
| 图像生成 | NovelAI, fal.ai (Flux), Meshy (3D), Codex图像生成, 本地Diffusers |
| Workspace应用 | Three.js 3D办公室＋2D像素画办公室（由同一实时事件流驱动） |

</details>

<details>
<summary><strong>项目结构</strong></summary>

```
animaworks/
├── main.py              # CLIエントリポイント
├── core/                # Digital Animaコアエンジン
│   ├── anima.py, agent.py  # コアエンティティ・オーケストレーション
│   ├── lifecycle/       # スケジューラ・統合ジョブ・inboxウォッチ等
│   ├── memory/          # 記憶（priming, consolidation, forgetting, RAG, facts, retrieval）
│   ├── skills/          # Skill Hub・activation・router・curator・promotion
│   ├── taskboard/       # TaskBoard ストア・状態・クリーンアップ
│   ├── execution/       # 実行エンジン（S/C/D/G/X/A/B）＋サニタイズ
│   ├── mcp/             # Mode S・外部クライアント向け stdio MCP サーバー
│   ├── platform/        # 子プロセス・ロック・Codex/Cursor/Gemini/Grok 周辺
│   ├── tooling/         # ToolHandler・スキーマ・権限・外部ディスパッチ
│   ├── prompt/          # システムプロンプト構築
│   ├── supervisor/      # ProcessSupervisor・IPC・TaskExec・死活監視・ストリーミング
│   ├── voice/           # 音声チャット（STT + TTS + フロントレーン）
│   ├── config/          # 設定（Pydantic・models.json・グローバル権限）
│   ├── auth/            # UI 認証まわり
│   ├── notification/    # 人間通知チャネル
│   ├── migrations/      # ランタイムデータマイグレーション
│   ├── i18n/            # 翻訳文字列（`t()`）
│   ├── tools/           # 外部ツール実装（slack, discord, gmail, github, …）
│   ├── tasks_dispatch.py, review_multipass.py  # GitHubイベント→タスク配線、マルチモデルレビュー
│   └── …
├── cli/                 # CLIパッケージ（demo含む）
├── server/              # FastAPI + 静的Web UI + Workspaceアプリ
│   ├── app.py           # アプリ生成・lifespan・認証/セットアップガード・静的マウント
│   ├── github_gateway.py, slack_socket.py, discord_gateway.py, zoom_gateway.py
│   ├── routes/          # REST/WebSocketルート（chat, room, voice, webhooks, …）
│   └── static/          # ダッシュボード、setupウィザード、workspace/（3D）、workspace/pixel/
├── swe/                 # 実験的CI自動修復ループ・SWEハーネス
├── demo/                # デモプリセットと同梱履歴
└── templates/           # 初期化テンプレート（ja / en / ko）ロール別作業規約を含む
```

</details>

---

## 文档

**[文档总索引](docs/zh/README.md)** — 阅读顺序指南、架构详解、设计规范列表。

| 文档 | 说明 |
|-------------|------|
| [设计理念](docs/zh/vision.md) | 「不完美个体的协作」这一根本思想 |
| [功能概览](docs/zh/overview.md) | AnimaWorks能做什么的整体图景 |
| [记忆系统](docs/zh/memory/index.md) | 情景记忆、语义记忆、程序性记忆、启动效应、主动遗忘 |
| [安全性](docs/zh/security.md) | 权限边界、数据来源、安全运维 |
| [脑科学映射](docs/zh/brain-mapping.md) | 各模块与人类大脑的对应关系 |
| [架构](docs/zh/architecture/index.md) | 执行模式、提示词构建、配置解析 |

## 许可证

Apache License 2.0。详情请参阅 [LICENSE](LICENSE)。