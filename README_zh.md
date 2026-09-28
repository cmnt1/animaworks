<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: README_ja.md -->
<!-- i18n: source-sha256=ebdfb709d98a0ad5490cf073d9c3e29774738eb4a952fb786529414e2ca765c1 generated=2026-09-28 engine=luna model=gpt-6-luna-2026-09-22 translator=2 -->

# AnimaWorks — Organization-as-Code

### 交付软件的 AI organization。

AnimaWorks 是一个将持久运行的 AI 智能体组成“运转中的 organization”的框架。给它一个目标，智能体们就会拆解工作，在并行 worktree 中实现、互相测试和评审、创建 Pull Request、修复 CI failure、解决冲突，并跟进到部署结果。只有确实需要人类参与时，才会向人类寻求确认。

```text
タスク → エージェントチーム → 並列worktree → 実装 → テスト → レビュー
     → Pull Request → CI修復 → デプロイ → 観測 → 修復
```

AnimaWorks 不会把这条流水线硬编码进去。框架负责将 GitHub 事件转化为 task、按 PR 串行执行，以及编排多模型评审。其余工作都由智能体像人类工程师一样完成——使用 git、测试、CI，以及各角色的工作规范。因此，同一个 organization 也能处理邮件、整理会议记录、发布 Slack 消息。因为它是一个 organization，而不是构建脚本。

## 在生产环境中的成果

过去 6 个月里，由 8 个 Anima 组成的 AnimaWorks organization 一直负责生产 SaaS 产品的日常开发运营：

| 指标（2026年3月〜8月） | 值 |
|---|---|
| 智能体创建的 Pull Request | **302 件**（267 件已合并） |
| 智能体负责运营的 Pull Request — 评审、CI 修复、冲突解决 | **752 件**（721 件已合并） |
| organization 自主发起的 task 占比 | **99.7%**（共 31,215 个 task，其中 92 个由人类发起） |
| 由 GitHub 事件自动转化为 task 的数量（仅 8 月） | **2,508 件** |

这些数字是根据一手执行记录（每个智能体的 activity log、task 队列、工作备忘录）汇总得出的，而不是根据提交的 author 信息统计的。因为在共享凭据下，人类和智能体的 push 会混在一起。无法确认有证据支持的 PR 均已排除。由于目标仓库不公开，因此仅公布汇总值。

AnimaWorks 本身也使用同样的方法开发。定义在这个仓库中的智能体会评审这个仓库的 PR、修复 CI 并发布版本。人类主要负责指明方向和处理例外。

<p align="center">
  <img src="docs/images/workspace-dashboard.gif" alt="AnimaWorks Workspace — リアルタイム組織ツリーとアクティビティフィード" width="720">
  <br><em>Workspace 仪表板：实时查看每个 Anima 的角色、status 和近期操作。</em>
</p>

<p align="center">
  <img src="docs/images/pixel-workspace.gif" alt="AnimaWorks ドット絵オフィス — 稼働中の組織のライブビュー" width="720">
  <br><em>像素风办公室并非模拟场景，而是运行中 organization 的实时视图——每个 status 标签都对应着正在运行的实际 task。</em>
</p>

**[English README](README.md)** | **[简体中文 README](README_zh.md)** | **[한국어 README](README_ko.md)**

---

## :rocket: 立即试用

**如果已安装 Claude Code CLI，或已登录 Codex，则无需 API 密钥**。

首先，通过一行命令克隆并安装：

```bash
curl -sSL https://raw.githubusercontent.com/xuiltul/animaworks/main/scripts/setup.sh | bash
cd animaworks
```

接下来，启动演示 team：

```bash
uv run animaworks demo
```

**打开 http://localhost:18501** 即可开始。一个由 3 人组成的 team（经理＋工程师＋助理）将开始运行，并附带 3 天的活动历史记录。首次安装需要下载 Python 3.12+ 和机器学习相关依赖包，因此需要几分钟；之后启动演示只需几秒。[查看演示详情 →](demo/README.ja.md)

> 预设：`en-business`（默认）/ `en-anime` / `ja-business` / `ja-anime` — 例如：`uv run animaworks demo --preset ja-anime`。切换现有演示的预设需要 `--reset`。演示需要克隆后的仓库（不会包含在 pip 软件包中）。

要创建自己的 organization，请运行 `uv run animaworks start` — 下方的设置向导将引导你创建第一个智能体。

---

## 快速开始

macOS / Linux / WSL：

```bash
curl -sSL https://raw.githubusercontent.com/xuiltul/animaworks/main/scripts/setup.sh | bash
cd animaworks
uv sync --all-extras        # codex/claude実行系のextraを追加
animaworks start            # サーバー起動 — 初回はセットアップウィザードが開きます
```

> **可在任何目录通过 `animaworks` startup。** `setup.sh` 会将 CLI 符号 link 到 `~/.local/bin`，因此只要该目录在 `PATH` 中，就可以省略 `uv run`（如果不在，请将 `export PATH="$HOME/.local/bin:$PATH"` 添加到 shell 的 rc 文件中）。控制台脚本使用绝对路径指向此仓库的 `.venv` 解释器，因此 `animaworks` 和 `uv run animaworks` 始终在同一环境中运行。手动安装时，请自行创建 link：`ln -sfn "$PWD/.venv/bin/animaworks" ~/.local/bin/animaworks`

Windows（PowerShell）：

```powershell
git clone https://github.com/xuiltul/animaworks.git
cd animaworks
uv sync --all-extras
uv run animaworks start
```

如果要在不使用 API 密钥的情况下使用 OpenAI Codex，请在首次 startup 前运行 `codex login`。

**打开 http://localhost:18500/** 后，设置向导会通过 5 个步骤引导你：

1. **语言** — 选择 UI 显示语言
2. **用户信息** — 创建所有者账户
3. **提供商 authentication** — 输入 API 密钥（OpenAI 也可使用 Codex Login），并选择头像画风
4. **第一个 Anima** — 为第一个智能体命名
5. **确认** — 检查内容并完成

无需手动编写 `.env`。向导会自动将其保存到 `config.json`。

安装脚本会帮你安装 [uv](https://docs.astral.sh/uv/)、克隆仓库、安装依赖包，并将 `animaworks` 命令 link 到 `~/.local/bin`。在 **macOS、Linux、WSL** 上，无需预先安装 Python 即可运行。**Windows** 用户请使用上面的 PowerShell 步骤。请注意，Mode S（Claude Agent SDK）无法在 Windows 上使用 — 请使用 Codex / Gemini / API 系列模式。

> **`uv sync` 必须附带 `--all-extras`。** 即使通过 `setup.sh` 运行原生 `uv sync` 也能运行主体程序，但 Mode C（Codex）需要 `codex` extra。此外，之后如果执行不带 extras 的 sync，venv 中的 `codex` / `claude` 可执行包会被删除，导致相应模式下的 Anima 全部无法运行。

> **想使用其他 LLM？** 支持 Claude、GPT、Gemini、本地模型等。你可以在设置向导中输入 API 密钥，也可以在 OpenAI/Codex 中使用 **Codex Login**。之后还可以在仪表板的 **Settings** 中更改。详情请参阅 [API 密钥 reference](#apiキーリファレンス)。

<details>
<summary><strong>其他方式：先检查脚本，再运行</strong></summary>

如果不想直接运行 `curl | bash`，可以先检查脚本内容：

```bash
curl -sSL https://raw.githubusercontent.com/xuiltul/animaworks/main/scripts/setup.sh -o setup.sh
cat setup.sh            # スクリプトの中身を確認
bash setup.sh           # 確認後に実行
```

</details>

<details>
<summary><strong>其他方式：使用 uv 手动逐步安装</strong></summary>

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
<summary><strong>其他方式：Docker</strong></summary>

```bash
git clone https://github.com/xuiltul/animaworks.git && cd animaworks
# 資格情報を .env に置く（git管理外）:
#   ANTHROPIC_API_KEY=...            # APIキー認証
#   CLAUDE_CODE_OAUTH_TOKEN=...      # またはサブスクリプション認証: `claude setup-token` (要TTY)
#   GH_TOKEN=...                     # 任意: animaがclone/pushやPR作成を行うために必要
docker compose up -d --build
```

无头设置（不使用 browser 向导时）：

```bash
docker exec -it <container> animaworks init --skip-anima
docker exec -it <container> animaworks anima create --name alice --template dev-lead
docker exec -it <container> animaworks config set setup_complete true
docker exec -it <container> animaworks send <your-name> alice "hello"
```

- 镜像中包含 git / GitHub CLI / Node.js 22 / Claude Code CLI，并已预装 `IS_SANDBOX=1` 和 `--foreground`。数据保存在命名卷 `animaworks-data`（`/root/.animaworks`）中。
- 人类通过 `animaworks send` 分派工作。`animaworks-tool task add` 仅用于 anima 的工具上下文。
- Homebrew 的 docker-compose 必须 link 到 `~/.docker/cli-plugins/docker-compose`，否则无法识别为 `docker compose` 子命令。

</details>

<details>
<summary><strong>其他方式：使用 pip 手动安装</strong></summary>

> **macOS 用户请注意：** macOS Sonoma 及更早版本的系统 Python（`/usr/bin/python3`）为 3.9 版，不满足 AnimaWorks 的要求（3.12+）。请通过 [Homebrew](https://brew.sh/) 安装 `brew install python@3.13`，或使用上面的 uv 方法（uv 会自动管理 Python）。

请确保系统已安装 Python 3.12+（推荐使用 3.12/3.13）。

```bash
git clone https://github.com/xuiltul/animaworks.git && cd animaworks
python3 -m venv .venv && source .venv/bin/activate
python3 --version       # 3.12+ であることを確認
pip install --upgrade pip && pip install -e .
animaworks start
```

注意：原生 `pip install -e .` 不包含 Codex extra。使用 Mode C 时，请添加 `.[codex]`。

</details>

---

## 循环如何运作

典型的变更会在 organization 中按以下流程推进：

1. **收到 task** — 来自人类、其他智能体、计划任务（heartbeat / cron）或 GitHub 事件。Webhook 网关会自动将 CI failure、评审评论、`@bot` 命令和合并冲突转化为智能体 task（`gh-ci-*` / `gh-review-*` / `gh-comment-*`）。支持按 PR 去重，并设有 retry 上限。
2. **经理拆分工作** — 通过 `delegate_task` 将工作委派给工程师，并附上验收条件、工作位置和排他键。涉及同一 PR 的 task 会通过排他键串行处理，智能体之间不会在同一分支发生冲突。
3. **工程师在隔离的 worktree 中实现并测试** — 遵循作为共享 knowledge 一部分提供的角色专属工作规范（产品经理 / 工程师 / 评审员 / 测试员）。这种隔离并非固定的流水线阶段，而是智能体通过 git 执行的运营规范——因此能够应对棘手的情况。
4. **多模型评审** — 每个 PR 都会针对配置的各个模型分别发起一条评审流程，再由综合 task 汇总所有流程的意见并做出判断（批准 / 要求修改）。有新的 push 时，旧的评审 task 会自动取消并重新执行。
5. **CI failure 会作为工作重新派回** — 失败的 workflow run 会作为修复 task 发送给实现智能体，并与 PR 编号和提交关联（不会重复派发）。实验性的独立循环（`python3 -m swe.ci_autofix`）会反复执行修复→lint/测试门禁→评审→提交，连续失败 3 次后升级给人类处理。
6. **部署和 runtime 确认也是智能体的工作** — 智能体会将分支部署到隔离环境，读取日志、错误和 UI 状态，找出测试未能发现的问题。生产环境 organization 的活动记录中，保留了数百条部署和 runtime 观察操作。
7. **人类介入处理例外** — organization 会在遇到阻塞，或需要作出超出权限范围的判断时升级处理（`call_human`）。另有一个监督进程负责监控智能体的存活状态、重启挂起的进程，并修复自身的记忆索引。

人类的角色从“操作智能体”转变为“organization 所有者”：传达意图、评审重要事项，并判断例外情况。

---

## 与其他框架的区别

|  | AnimaWorks | CrewAI | LangGraph | OpenClaw | OpenAI Agents |
|--|-----------|--------|-----------|----------|---------------|
| **设计理念** | 自主代理组成的组织 | 基于角色的团队 | 图工作流 | 个人助手 | 轻量级 SDK |
| **记忆** | 基于脑科学：vector＋BM25＋facts/实体 search，按需进行图扩散、consolidation、主动遗忘和自动回忆 | Cognitive Memory（手动 forget） | 检查点＋cross-thread 存储 | SuperMemory knowledge 图 | 仅限 session 内 |
| **自主性** | Heartbeat（观察→计划→回顾）+ Cron + TaskExec + GitHub 事件网关 — 24/7运行 | 由人类启动 | 由人类启动 | Cron + heartbeat | 由人类启动 |
| **组织结构** | Supervisor→subordinate 的 hierarchy、委派、审计和仪表板 | Crew 内部的扁平角色 | — | 单一代理 | 仅支持 Handoff |
| **进程** | 每个代理均为独立 OS 进程，支持 IPC 和自动重启 | 共享进程 | 共享进程 | 单一进程 | 共享进程 |
| **多模型** | 7 种引擎：Claude SDK / Codex / Cursor Agent / Gemini CLI / Grok Build / LiteLLM / Assisted — 提供按引擎区分的回退链 | LiteLLM | LangChain 模型 | OpenAI 兼容 | 以 OpenAI 为中心 |

> AnimaWorks 不是任务运行器，而是一个会思考、记忆、遗忘并逐渐成长的组织。我在实际经营业务的过程中，将它作为 AI team 使用，同时也在持续开发。

---

## 能做什么

### 仪表板

<p align="center">
  <img src="docs/images/dashboard.png" alt="AnimaWorks ダッシュボード — リアルタイム組織図" width="720">
  <br><em>仪表板：显示所有 Anima 实时状态的组织架构图。</em>
</p>

Web UI 由 6 个页面（哈希路由器 `#/…`）和 Workspace 应用组成：

- **主页** — 显示实时状态的组织架构图、提示需要处理事项的醒目标签、LLM 使用量面板（Claude / OpenAI / nanoGPT）、系统状态栏、近期活动和外部任务组件。可从此处打开各 Anima 的详情页（overview / process / schedule / memory / assets）
- **聊天** — 与任意 Anima 实时对话：流式响应（SSE）、图片附件、多线程历史记录、右侧标签页（state / activity / heartbeat / cron）、记忆浏览器（episodes / knowledge / procedures）。**会议模式**可将最多 5 名 Anima 与主持人召集到同一房间。长按聊天标签页可打开**语音弹窗**（带有说话动画头像）
- **Board** — 类似 Slack 的共享 channel 和 DM。Anima 之间可讨论和协作。桥接的 Discord channel 也会显示在此处
- **任务** — 任务看板：队列、处理中、搁置、抑制、后台执行和结果。还会与 priming 联动，只把当前值得关注的任务带入对话
- **活动** — 全组织 SVG 泳道时间线、带实时 tool 滚动提示的 Now 看板、session 回放、log
- **设置** — 4 个标签页（general / activity / API・authentication / users）。首次启动时会显示 `/setup/` 向导
- **Workspace** — 在独立标签页中打开的独立应用：**3D 办公室**（`/workspace/`，可切换组织架构视图，带有说话的半身像）和**像素办公室**（`/workspace/pixel/`，所有状态标签都对应实际任务的实时 2D 视图）
- **主题和语言** — 11 种 UI 主题＋动画/写实显示模式。设置向导支持 17 种语言，仪表板主体支持 `ja` / `en` / `ko`

### 创建组织，委派工作

只要告诉领导“我想要这样的人”，它就能判断角色、性格和上下级关系，并创建新成员。无需直接操作 configuration file 或 CLI，也能以对话为起点逐步发展组织。

团队组建完成后，Anima 会利用自己的日程和记忆持续工作：

- **heartbeat** — 定期确认状况，并自行判断接下来要做什么
- **cron 作业** — 日报、周报、监控。可针对每个 Anima 单独设置，同时支持 LLM 任务和命令执行
- **任务委派** — 经理会附上验收条件分配任务、跟踪进度并接收汇报
- **并行任务执行** — 同时提交多个任务。独立任务并行执行，共享排他键的任务则依次执行
- **GitHub 事件网关** — 受监控仓库中的 CI failure、评审评论和冲突会自动转化为任务
- **夜间整合** — 白天的 episode 记忆会在睡眠期间升华为 knowledge
- **团队协作** — 通过共享 channel 和 DM 向需要的对象共享情况

### 记忆系统

传统 AI 代理只能记住能放进上下文窗口的内容。AnimaWorks 的 Anima 拥有基于文件的 long-term memory，需要时会通过 search 回忆。它不会每次都把所有内容塞进上下文，而是只取出与当前对话或行动相关的记忆。

- **自动回忆（Priming）** — 收到 message 时，6 个 channel 会并行运行：发送者档案、近期活动、重要 knowledge、相关 knowledge、待处理任务、episode。相关 knowledge 的 search 也可根据 configuration 使用 legacy NetworkX 图扩散。确定性门控会决定以正文、指针、依据还是抑制的方式呈现检索到的记忆
- **有意回忆** — 自动回忆不足时，Anima 会通过 `search_memory` 或 `read_memory_file` search 记忆。search 采用混合方式（vector＋BM25＋atomic facts＋实体注册表），并设有置信度门控
- **行动前的操作规则匹配** — 在外部发送等具有副作用的操作之前，会匹配并呈现相关操作规则。也可以配置为在读取必要记忆之前暂缓执行
- **整合（Consolidation）** — 日常处理中会汇总 episode，Anima 通过工具循环提取 knowledge。框架会协助维护索引和收集候选项。每周处理中，会将可能重复或矛盾的 knowledge 列为待确认项，由 Anima 判断内容
- **遗忘（Forgetting）** — 日常处理中会将低活跃度记忆标记为候选项，每周处理中会向 Anima 提供建议归档的记忆。候选项不会自动删除，重要记忆和成熟流程会受到保护规则约束。也支持在发生 failure 后重新审视流程的再巩固
- **记忆 search** — 结合通过 legacy vector worker 执行的 vector search 与 BM25。也可根据 configuration 使用 NetworkX 图扩散辅助 search 结果

<p align="center">
  <img src="docs/images/chat-memory.png" alt="AnimaWorks チャット — 複数Animaとのマルチスレッド会話" width="720">
  <br><em>聊天：经理在审核代码修改，工程师正在汇报进度。</em>
</p>

### 多模型支持

可以运行在任何 LLM 上。每个 Anima 都可以使用不同的模型。

| 模式 | 引擎 | 对象 | 工具 |
|--------|----------|------|--------|
| S (SDK) | Claude Agent SDK | Claude 模型（推荐） | Claude Code 内置（Read/Write/Edit/Bash/Grep/Glob 等）＋ **stdio MCP**（`mcp__aw__*`）提供 AnimaWorks 内部工具。在无法使用 Agent SDK 的环境中，回退到专用的 Anthropic SDK 执行器 |
| C (Codex) | Codex CLI（SDK 封装器） | OpenAI Codex CLI 模型 | Codex 沙箱＋通过 **AnimaWorks MCP**（`core/mcp/server.py`）使用内部工具 |
| D (Cursor) | Cursor Agent CLI | `cursor/*` 模型 | 集成 MCP 的代理循环 |
| G (Gemini CLI) | Gemini CLI | `gemini/*` 模型 | stream-json 解析和工具循环 |
| X (Grok Build) | Grok Build CLI 封装器（ACP stdio） | `grok/*` 模型 | 通过 ACP stdio 运行 Grok Build 代理循环 |
| A (Autonomous) | LiteLLM + tool_use | GPT、Gemini、Mistral、Bedrock、Vertex、xAI、DeepSeek 等 | CC 兼容（Read/Write/Edit/Bash/Grep/Glob、**WebSearch/WebFetch**）＋记忆、message、任务、**todo_write**、技能创建等 |

模式解析依次使用 `status.json` 的 `execution_mode`、`models.json` 的表，以及内置的模型名称模式。未知模型会分配到 A。回退遵循各引擎的 configuration 和错误分类。Heartbeat、Cron、Inbox 可以使用与主模型不同的 **background_model** 运行（优化成本）。同时支持扩展思考（Extended thinking）。

### 语音聊天

只需使用浏览器即可与 Anima 语音对话（按住说话或免提，通过 WebSocket 连接）。

- **STT**：faster-whisper（流式处理・LocalAgreement-2 逐步确认）
- **TTS**：VOICEVOX / Style-BERT-VITS2（AivisSpeech） / ElevenLabs / Irodori。可为每个 Anima 设置声音、语速和音高
- **低延迟前置通道** — 小型本地模型会立即响应，并根据需要委派给主体代理（`ask_anima`）或读取记忆
- **主动发言** — 启用前置通道时，如果持续沉默，Anima 会主动开口
- **动画头像** — 语音弹窗会驱动伪 Live2D 半身像（以 5 帧静态图实现眨眼和口型同步。不使用骨骼绑定或 Live2D SDK）

### 自动生成头像

<p align="center">
  <img src="docs/images/asset-management.png" alt="AnimaWorks アセット管理 — リアリスティックなアバターと表情バリアント" width="720">
  <br><em>根据性格设置自动生成全身像、半身像和表情变体。还带有 Vibe Transfer，可自动继承 supervisor 的画风。</em>
</p>

7 步流水线会生成全身图、带 7 种表情的半身像、图标、Q 版角色，以及（动画风格下）idle/sitting/waving/talking带动画的绑定 3D 模型。后端除 NovelAI（动画风格）、fal.ai/Flux（（风格化/写实）和 Meshy（3D）外，还支持 Codex 图像生成和本地 Diffusers。通过 Vibe Transfer（NovelAI），新的 Anima 可以继承 supervisor 的画风。即使不配置图像服务，主体也能运行。

---

## 为什么选择 AnimaWorks

**一个人什么也做不了。所以，我们创建了一个组织。**

这个项目诞生于三种职业经历的交汇点。

**作为经营者**——我知道“一个人什么也做不了”。我们需要优秀的工程师，也需要擅长沟通的员工。有默默工作的员工，也有人偶尔能提出犀利的点子。只有天才，组织无法运转。汇聚多种力量，就能完成一个人无法做到的事。

**作为精神科医生**——观察 LLM 的内部结构时，我发现它与人脑有着惊人的相似之处。回忆、学习、遗忘、巩固——如果把大脑处理记忆的机制原样实现为 LLM 的记忆系统，也许就能重现人脑。既然如此，只要把 LLM 当作“拟似人类”来对待，就应该也能像人类一样组建组织。

**作为工程师**——我写了 30 年代码。我了解构建逻辑的乐趣，也了解自动化带来的快感。只要把所有理想都写进代码，就能创建出我理想中的组织。

优秀的“单人 AI 秘书”框架已经有很多了。但我一直觉得，用代码构建接近人类的单元，并让这些单元作为组织运作的项目仍然不多。AnimaWorks 是一个 AI 组织，我亲自将它融入业务，并在日常使用中不断完善。

> *不完美个体的协作，能构建出比单一全能者更坚韧的组织。*

三项原则为此提供支撑：

- **封装**——内部的思考和记忆不会对外公开。与他人仅通过文本对话相连。这与现实中的组织相同。
- **RAG记忆（档案库型）**——不会把所有内容都塞进窗口。Priming 会通过 RAG 提取相关片段，智能体会通过 `search_memory` 等内容主动回忆。
- **自主性**——不等待指示。按照自己的时钟行动，并依据自己的价值观做判断。

---

<details>
<summary><strong>API 密钥参考</strong></summary>

#### LLM 提供商

| 键 | 服务 | 模式 | 获取方式 |
|-----|---------|------|--------|
| `ANTHROPIC_API_KEY` | Anthropic API | S / A | [console.anthropic.com](https://console.anthropic.com/) |
| `OPENAI_API_KEY` | OpenAI | A / C（使用 Codex Login 时可省略） | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `GOOGLE_API_KEY` | Google AI (Gemini) | A | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |

**OpenAI Codex（Mode C）** 除了使用 `OPENAI_API_KEY` 外，也可以使用本地的 **Codex Login**（`codex login`）。请在设置向导或 Settings 中进行选择。

**Grok Build（Mode X）** 通过 Grok Build CLI 封装程序（ACP stdio）使用 `grok/*` 模型。请预先安装 `grok` CLI，然后运行 `grok login`。

**Azure OpenAI**、**Vertex AI (Gemini)**、**AWS Bedrock** 和 **vLLM** 可在 `config.json` 的 `credentials` 部分进行 configuration。详情请参阅[架构](docs/zh/architecture/index.md)。

**Ollama** 等本地模型无需 API 密钥。请通过 `OLLAMA_SERVERS`（默认值：`http://localhost:11434`）指定连接目标。

authentication 信息按 `config.json` 的 `credentials` → vault → 共享 credentials 文件 → environment variable 的顺序解析，因此许多密钥也可以存放在加密 vault（`animaworks vault`）中。

#### 图像生成（可选）

| 密钥 | 服务 | 生成内容 | 获取地址 |
|-----|---------|-------|--------|
| `NOVELAI_TOKEN` | NovelAI | 动漫风格角色图像 | [novelai.net](https://novelai.net/) |
| `FAL_KEY` | fal.ai (Flux) | 风格化 / 照片级写实图像 | [fal.ai/dashboard/keys](https://fal.ai/dashboard/keys) |
| `MESHY_API_KEY` | Meshy | 3D 角色模型 | [meshy.ai](https://www.meshy.ai/) |

#### 语音聊天（可选）

| 要求 | 服务 | 备注 |
|------|---------|------|
| `pip install animaworks[transcribe]` | STT（faster-whisper） | 首次使用时自动下载模型。建议使用 GPU |
| 启动 VOICEVOX Engine | TTS（VOICEVOX） | 默认值：`http://localhost:50021` |
| 启动 AivisSpeech/SBV2 | TTS（Style-BERT-VITS2） | 默认值：`http://localhost:5000` |
| 启动 Irodori 服务器 | TTS（Irodori） | 默认值：`http://localhost:7861` |
| `ELEVENLABS_API_KEY` | TTS（ElevenLabs） | 云端 API（环境变量） |

#### 外部集成（可选）

| 密钥 | 服务 | 获取地址 |
|-----|---------|--------|
| `SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN` | Slack（工具＋Socket Mode 接收） | [设置指南](docs/zh/integrations/slack.md) |
| `CHATWORK_API_TOKEN` | Chatwork（工具＋Webhook 接收） | [chatwork.com](https://www.chatwork.com/) |
| `DISCORD_BOT_TOKEN`（或按 Anima 单独配置 `DISCORD_BOT_TOKEN__<名前>`） | Discord（工具＋Gateway 接收＋通知） | [Discord Developer Portal](https://discord.com/developers/applications) |
| `NOTION_API_TOKEN`（或 `NOTION_API_TOKEN__<名前>`） | Notion | [Notion integrations](https://www.notion.so/my-integrations) |
| `GITHUB_WEBHOOK_SECRET` ＋ `gh auth login` | GitHub Webhook 网关（CI/审查/冲突→创建任务） | 仓库配置 |

Gmail / Google Calendar / Google Sheets / Google Tasks / X 搜索 / AWS 收集器 / Zoom 会议导入（RTMS）/ 本地 LLM 工具，可在 `config.json` 的 `credentials`（OAuth 或服务账号）中配置。面向人类的通知渠道：Slack、Chatwork、Discord、LINE、Telegram、ntfy。详情请参阅[架构](docs/zh/architecture/index.md)。

</details>

<details>
<summary><strong>层级与角色</strong></summary>

只需一个 `supervisor` 字段即可定义上下级关系。未设置时默认为顶层。

角色模板会根据职位自动应用专用提示词、权限和模型：

| 角色 | 默认模型 | 用途 |
|--------|----------------|------|
| `engineer` | Claude Opus 4.6 | 复杂推理、代码生成 |
| `manager` | Claude Opus 4.6 | 协调、决策 |
| `writer` | Claude Sonnet 4.6 | 内容创作 |
| `researcher` | Claude Sonnet 4.6 | 信息收集 |
| `ops` | Ollama (GLM-4.7) | 日志监控、常规工作 |
| `general` | Claude Sonnet 4.6 | 通用 |

经理会自动获得**主管工具**。委派任务、跟踪进度、重新启动/停用下属、查看组织仪表板、读取下属状态——做的都是现实中的管理者会做的事。

每个 Anima 都由 ProcessSupervisor 作为独立进程启动，并通过本地 IPC 通信（Unix 系统使用 Unix socket，Windows 使用 loopback TCP）。

</details>

<details>
<summary><strong>安全</strong></summary>

既然要把工具交给自主运行的智能体，就必须认真对待安全问题。因为它会实际用于工作，绝不能妥协。AnimaWorks 采用多层防御：

| 层级 | 内容 |
|---------|------|
| **信任边界标记** | 外部数据（网页搜索、Slack、邮件）会根据来源添加标签，并传播会话中观察到的最低信任级别。明确告知模型不要遵从来自不可信来源的指示 |
| **记忆来源追踪** | 来自外部内容的记忆会将来源信息保留至 RAG 元数据，并在回忆时与 Anima 自身的知识区分开来 |
| **命令安全** | Shell 注入检测（默认仅记录，可启用强制模式） → 全局禁止列表（强制执行。没有 `permissions.global.json` 时服务器无法启动） → 单个智能体的禁止命令 → 单个智能体的允许列表 → 路径遍历检测 |
| **文件沙箱** | 每个智能体都通过 `permissions.json` 被限制在自己的目录中。identity 和权限文件本身受到写入保护 |
| **进程隔离** | 每个智能体使用独立的 OS 进程。通过本地 IPC 通信（Unix socket；Windows 使用 loopback TCP） |
| **速率限制** | 会话内对重复目标去重并按角色设定上限 → 按小时和天计算的跨会话上限（日志不可读时采用 fail-closed） → 通过提示词注入近期发送记录，使智能体具备自我认知 |
| **级联防护** | 会话深度限制＋级联检测。设置 5 分钟冷却时间并延迟处理 |
| **认证与会话管理** | Argon2id 哈希、48 字节随机令牌、最多 10 个会话，TTL 可配置 |
| **Webhook 验证** | Slack、Chatwork、Zoom、GitHub 的 HMAC 签名验证（带重放防护） |
| **SSRF 缓解** | 媒体代理会拦截私有 IP 和 DNS 重绑定，强制使用 HTTPS，并验证 Content-Type 和魔数 |
| **出站路由** | 未知目标采用 fail-closed。未明确配置时不允许向任意外部地址发送内容 |
| **智能体间消息完整性** | 将发送者名称与名册核对，并追踪所有转发消息的 origin chain |

详情：**[安全](docs/zh/security.md)**

</details>

<details>
<summary><strong>CLI 命令参考（高级用户）</strong></summary>

CLI 面向高级用户和自动化场景。日常操作使用 Web UI 即可。

### 服务器与演示

| 命令 | 说明 |
|---|---|
| `animaworks start [--host HOST] [--port PORT] [-f]` | 启动服务器（使用 `-f` 在前台运行。默认端口 18500） |
| `animaworks stop [--force]` / `restart` | 停止 / 重启服务器 |
| `animaworks demo [--preset NAME] [--port PORT] [--reset]` | 启动演示组织（默认端口 18501，使用专用数据目录） |

### 初始化

| 命令 | 说明 |
|---|---|
| `animaworks init [--force] [--template NAME] [--from-md PATH] [--blank]` | 初始化运行时目录 |
| `animaworks migrate [--dry-run] [--list] [--force] [--resync-db]` | 迁移运行时数据（启动时也会自动执行） |
| `animaworks reset [--restart]` | 重置运行时目录 |
| `animaworks import hermes\|openclaw --path P [--apply]` | 从其他框架迁移智能体 |

### Anima 管理

| 命令 | 说明 |
|---|---|
| `animaworks anima create [--from-md PATH] [--template NAME] [--role ROLE] [--supervisor NAME] [--name NAME]` | 新建 |
| `animaworks anima list / info / status / restart / disable / enable` | 确认与控制 |
| `animaworks anima set-model / set-background-model / set-memory-backend / set-role / set-outbound-limit` | 按 Anima 配置 |
| `animaworks anima reload [--all]` | 从 status.json 热重载 |
| `animaworks anima delete / rename / merge / merge-finalize` | 生命周期操作 |
| `animaworks anima audit [--days N]` / `permissions` / `repair-bootstrap` | 诊断 |

### 沟通

| 命令 | 说明 |
|---|---|
| `animaworks chat ANIMA "メッセージ" [--from NAME]` | 发送消息 |
| `animaworks send FROM TO "メッセージ"` | Anima 间消息 |
| `animaworks board read/post/dm-history …` | 读写共享渠道 |
| `animaworks heartbeat ANIMA` | 手动触发心跳 |

### Configuration・Maintenance

| Command | Description |
|---|---|
| `animaworks config list / get KEY / set KEY VALUE` | Configuration |
| `animaworks status` / `logs [ANIMA]` | System status・logs |
| `animaworks index [--anima NAME] [--full]` | RAG index management |
| `animaworks repair-rag --anima NAME --full` / `rag-repair-status` | RAG quarantine・rebuild |
| `animaworks memory status / migrate / backup / rollback / cleanup` | memory backend and memory data |
| `animaworks skills install / list / inspect / remove / quarantine` | Skill Hub operations |
| `animaworks task add / update / list` | Task queue operations |
| `animaworks vault status / init / get / store / list` | Encrypted credential vault |
| `animaworks company create / list / assign / adopt / split / export` | Multi-company organization management |
| `animaworks cost` / `profile` / `models list` / `tmp list/clean` | Cost・profiles・models・temporary file cleanup |
| `animaworks mcp --anima NAME` | Start an stdio MCP server for external clients |

### Automation Helpers

`python3 -m swe.ci_autofix` is an experimental v0 loop for repairing failed CI runs. It reads the latest failure log with `gh`,
has the configured Architect make corrections, runs the local gates (ruff / pytest), has the Reviewer assess the changes, and commits them.
After three failures, it escalates via `call_human`. For details, see
[`swe/README.md`](swe/README.md#4-ci-auto-fix-loop-v0).

</details>

<details>
<summary><strong>Technology Stack</strong></summary>

| Component | Technology |
|---|---|
| Agent execution | Claude Agent SDK / Codex CLI / Cursor Agent CLI / Gemini CLI / Grok Build CLI / Anthropic SDK (fallback) / LiteLLM |
| Mode S integration | stdio **MCP** (`python -m core.mcp.server`, tool name `mcp__aw__*`) |
| LLM providers | Anthropic, OpenAI, Google, Azure, Vertex AI, AWS Bedrock, Ollama, vLLM, and others (via LiteLLM) |
| Web framework | FastAPI + Uvicorn |
| GitHub integration | Webhook gateway (HMAC validation) → task dispatch, multi-path review orchestration, `gh` CLI tool with per-Anima identity |
| Real-time | WebSocket (dashboard・voice), SSE (chat・meetings), stream lifecycle management via `StreamRegistry` |
| Task scheduling | APScheduler (heartbeat・cron・consolidation・health monitoring・RAG repair) |
| Task management | Task queue (JSONL) + pending task runner with PR-level exclusive keys + TaskBoard (SQLite) |
| Memory foundation | ChromaDB (via isolated vector worker) + BM25 + sentence-transformers + legacy NetworkX graph + atomic facts + entity registry |
| Configuration・migration | Pydantic 2.0+ / JSON / Markdown, `core/migrations/` (startup migration) |
| Internationalization | `core/i18n`'s `t()`. 17 wizard languages・dashboard ja/en/ko |
| Skill foundation | Skill Hub, explicit skill activation, router, curator, procedure-to-skill promotion |
| Extension tools | In addition to automatic registration of `core/integrations/*.py`, scans `~/.animaworks/common_tools/` and `animas/<名>/tools/` |
| Voice chat | faster-whisper (STT) + VOICEVOX / SBV2 / ElevenLabs / Irodori (TTS) + local front-lane model |
| Messaging | Receive: Slack Socket Mode, Chatwork Webhook, Discord Gateway, Zoom RTMS / Human notifications: Slack, Chatwork, Discord, LINE, Telegram, ntfy |
| Image generation | NovelAI, fal.ai (Flux), Meshy (3D), Codex image generation, local Diffusers |
| Workspace app | Three.js 3D office + 2D pixel-art office (powered by the same live event stream) |

</details>

<details>
<summary><strong>Project Structure</strong></summary>

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

## Documentation

**[Documentation Index](docs/zh/README.md)** — Guidance on reading order, detailed architecture, and a list of design specifications.

| Documentation | Description |
|-------------|------|
| [Design Philosophy](docs/zh/vision.md) | The foundational idea of “collaboration among imperfect individuals” |
| [Feature Overview](docs/zh/overview.md) | An overview of what AnimaWorks can do |
| [Memory System](docs/zh/memory/index.md) | Episodic memory・semantic memory・procedural memory・priming・active forgetting |
| [Security](docs/zh/security.md) | Permission boundaries, data provenance, security operations |
| [Neuroscience Mapping](docs/zh/brain-mapping.md) | How each module corresponds to the human brain |
| [Architecture](docs/zh/architecture/index.md) | Execution modes, prompt construction, configuration resolution |

## 许可证

Apache License 2.0。详情请参阅 [LICENSE](LICENSE)。
