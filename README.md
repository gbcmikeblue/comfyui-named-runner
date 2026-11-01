# ComfyUI Named Runner

**把本机 ComfyUI 变成一个「按名字调用 → 传参 → 拿产物」的生成后端。**

一个零依赖（只用 Python 标准库）的命令行工具 + Python 客户端库：你不需要每次都打开 ComfyUI 网页、拖节点、点 Run，也不需要自己拼 `POST /prompt` 的 API 图。工作流仍然在 ComfyUI 的图形界面里搭（或直接用别人导出的 API 图），然后在命令行里用一个**别名**调用它。

```powershell
python scripts\comfy.py dub "弯弯的月儿小小的船。" --voice 灵小安 --out .\配音
python scripts\comfy.py run my_t2i -p prompt="雨后的江南小巷" --out .\图
```

---

## 目录

- [它解决什么问题](#它解决什么问题)
- [特性](#特性)
- [快速开始](#快速开始)
- [命令速查](#命令速查)
- [工作流别名机制](#工作流别名机制)
- [语音能力](#语音能力)
- [退出码与错误模型](#退出码与错误模型)
- [项目结构](#项目结构)
- [作为 AI Agent Skill 使用](#作为-ai-agent-skill-使用)
- [文档](#文档)
- [兼容性与实测](#兼容性与实测)
- [许可与致谢](#许可与致谢)

---

## 它解决什么问题

ComfyUI 把「画工作流」做得很舒服，把「批量、脚本化、被其他程序调用」留给了用户：

| 常见痛点 | 本项目的做法 |
|---|---|
| 每次出图都要开浏览器、点 Run、手动存文件 | 一条命令提交 + 自动下载产物到指定目录 |
| 官方 API 要求提交的图是 `{"节点id": {"class_type": ...}}` 格式，而界面保存的是 `nodes` + `links` | 内置 **UI → API 转换器**（按 `/object_info` 还原控件值、解析连线、处理旁通/静音/Reroute） |
| 工作流一改名、一另存，脚本里的节点 id 全废 | 用**别名 + 参数名**调用，节点 id 只写在 `registry.json` 里，改图只改一处 |
| 换了机器 / 端口被占用，脚本全挂 | 端口扫描（8188–8192）+ `doctor` 体检 + 分阶段退出码 |
| 想把 ComfyUI 塞进构建流水线，但输出全是人看的 | 全部命令支持 `--json`，stdout/stderr 结构化，可直接被其他程序解析 |
| 语音合成要 5 GB 环境才能试一下 | 内置「拟真人配音」与「离线 SAPI 兜底」两条链路，前者 0.5B 权重即可跑 |

**边界**：本工具**不启动、不重启、不关闭** ComfyUI。服务由你自己启动（ComfyUI Desktop 点 Launch，或命令行 `main.py`），本工具只负责发现端口、连接、提交与取回。

## 特性

- **按名字执行**：`run <别名>` / `run <文件名>` / `run <路径>`，三级查找，找不到会列出可选清单而不是瞎猜。
- **UI 与 API 两种工作流格式都吃**：界面保存的 `nodes`+`links` 自动转换；`Export (API)` 导出的图直接使用。
- **参数绑定有据可依**：显式绑定（节点 id / 节点标题 / 节点类名 + 输入名）优先，未绑定的按输入名自动匹配；同名输入有歧义时**报错并列出候选**，绝不静默挑一个。
- **产物收集完整**：`images` / `audio` / `gifs` / `videos` / `text` 五类输出键都覆盖，按 `--out` 目录落盘并保留子目录结构。
- **离线校验**：`--dry-run` + `--schema <保存的 object_info.json>` 可以在没有服务的情况下检查转换结果。
- **可嵌入**：`comfy_client.py` 是纯库，`load_config` / `Server.submit` / `ui_to_api` / `bind_params` 都能直接被 Python 项目 import。
- **可诊断**：`doctor` 一次性检查服务、端口、节点类、模型权重、torch 环境、registry 完整性。
- **零第三方依赖**：只用标准库，Python 3.9+；不需要 `pip install` 任何东西。
- **错误可编程**：7 个阶段 × 独立退出码，`--json` 时输出单行机器可读错误。
- **自带语音链路**：拟真人配音（Ming-3.0-tts 0.5B，内置音色 / 音色克隆）、离线 SAPI 兜底、CosyVoice3 多引擎备选。

## 快速开始

### 1. 准备 ComfyUI

任意一份能正常出图的 ComfyUI 安装即可：

- **ComfyUI Desktop**（推荐）：装好后点 Launch，默认监听 `http://127.0.0.1:8188`，端口冲突时会自动换到 8189+（本工具会扫描）。
- **手动安装**：`python main.py` 启动，注意用带 torch 的那个 Python 环境。

工作流可以直接在界面里搭，也可以在「工作流 → 导出 (API)」里导出成 JSON。

### 2. 拿到本项目

```powershell
git clone https://github.com/<your-name>/comfyui-named-runner.git
cd comfyui-named-runner
```

### 3. 写配置

```powershell
Copy-Item config.example.json config.json
notepad config.json
```

至少把 `comfyui_root` 改成你的 ComfyUI 代码根目录。也可以完全跳过这一步，用环境变量：

```powershell
$env:COMFY_URL        = "http://127.0.0.1:8188"
$env:COMFYUI_ROOT     = "D:\ComfyUI"
$env:COMFY_WORKFLOWS_DIR = "D:\ComfyUI\user\default\workflows"
```

优先级：**内置默认值 < `config.json` < 环境变量 < 命令行参数**。

### 4. 体检 + 试用

```powershell
python scripts\comfy.py doctor          # 服务、端口、路径、节点、torch 一次看全
python scripts\comfy.py list --all      # 已登记别名 + 工作流目录里可发现的所有工作流
python scripts\comfy.py describe <名字>  # 节点/参数/产物结构，含转换告警
python scripts\comfy.py run <名字> -p key=value --out .\out
```

一次典型的完整调用：

```powershell
python scripts\comfy.py run my_t2i `
  -p prompt="雨后的江南小巷，水彩" `
  --seed 12345 `
  --out .\out --json
```

成功时 stdout 是可直接解析的 JSON：

```json
{"ok": true, "prompt_id": "4a1c...", "elapsed_sec": 37.2,
 "files": [{"kind": "image", "path": "out\\my_t2i_00001_.png", "bytes": 1482311}],
 "text_outputs": {}, "applied": {"prompt": "...", "seed": 12345}}
```

## 命令速查

| 命令 | 作用 |
|---|---|
| `doctor` | 体检：服务、端口、节点类、模型权重、torch、registry |
| `wait` | 等待（手动启动的）ComfyUI 就绪，默认 180 s |
| `list [--all] [--filter]` | 列出已登记别名；`--all` 同时扫描工作流目录 |
| `describe <名字> [--schema f]` | 查看某工作流的节点、可绑定参数、预期产物 |
| `run <名字> [-p K=V] [--seed] [--input-image] [--input-audio] [--out] [--dry-run] [--no-wait]` | 执行工作流 |
| `tts "<文本>"` | 便捷文生语音（TTS 工作流封装） |
| `dub "<文本>"` | 拟真人配音 / 音色克隆（Ming-3.0-tts） |
| `register <别名> --source ...` | 把已有工作流登记成可复用别名 |
| `nodes [关键词]` | 查询已安装节点类及其精确类名 |
| `interrupt` | 中断当前执行 |

全局参数（子命令前后都能写）：`--json`、`--base-url`、`--config`。

完整参数表见 **[docs/cli.md](docs/cli.md)**。

## 工作流别名机制

`registry.json` 是整个工具的"路由表"：别名 → 源文件 → 参数绑定 → 默认值。

```json
"my_t2i": {
  "title": "Qwen 文生图",
  "source": "user:qwen_image_t2i_api.json",
  "params": {
    "prompt": {"node": "27", "input": "text", "type": "string"},
    "steps":  {"node_title": "采样", "input": "steps", "type": "int"}
  },
  "defaults": {"steps": 20}
}
```

`source` 三种写法：

| 写法 | 含义 |
|---|---|
| `user:<rel>` | ComfyUI 工作流目录（`<root>/user/default/workflows`）下的相对路径 |
| `api:<rel>` | 本项目 `scripts/workflows/` 下随仓库分发的 API 格式工作流 |
| `file:<abs>` | 任意绝对路径（适合把工作流放在项目仓库里） |

登记示例：

```powershell
# 自动绑定：图里同名输入唯一时
python scripts\comfy.py register my_t2i --source user:qwen_image_t2i_api.json --title "Qwen 文生图"

# 显式绑定：NAME=NODE_ID.INPUT，或 NAME=NODE@标题片段.INPUT
python scripts\comfy.py register my_t2i --source user:qwen_image_t2i_api.json `
  --param prompt=27.text --param width=30.width --param height=30.height `
  --default width=1024 --default height=1024
```

> 强烈建议用 **API 格式**（界面里「导出 (API)」）。UI 格式转换对核心节点链路很准，但自定义节点常把**显示标签**写进控件值，导致位置错位——转换器会给出 warning，这类图请导出 API 格式后再登记。

详见 **[docs/workflows.md](docs/workflows.md)**。

## 语音能力

| 别名 | 链路 | 特点 | 依赖 |
|---|---|---|---|
| `ming` | Ming-3.0-tts **0.5B**，内置音色 | 拟真人、100+ 中文音色、44.1 kHz 单声道，显存 ~2.5–2.8 GiB | `ComfyUI-Ming-3-tts` 节点 + 2.76 GiB 权重 |
| `ming_clone` | 同上，**零样本音色克隆** | 给 10–30 s 真人录音 + 逐字转写，克隆该音色 | 同上 |
| `tts` | Windows **SAPI**，离线 | 秒级、零显存、无模型；机器味，适合占位与调试 | 自建节点 `ComfyUI-LocalTTS-SAPI` |
| `cosyvoice3` | CosyVoice3（TTS Audio Suite） | 多语种 / 方言 / 多角色对话 / SRT 时间轴 | 插件 + 5.2 GiB 权重 |

```powershell
# 内置音色，开箱即用
python scripts\comfy.py dub "小兔子乖乖，把门儿开开。" --voice 灵小安 --out .\配音

# 音色克隆：参考音频 + 它的逐字转写（不是要合成的新句子）
python scripts\comfy.py dub "春天来了。" --ref-audio .\voice\teacher.wav `
  --ref-text "这是一段十五秒左右的普通话朗读示范。" --language Chinese --out .\配音

# 长文本批量：每行一句，配合 --prefix 区分课时
python scripts\comfy.py dub --text-file .\lesson02.txt --ref-audio .\voice\teacher.wav `
  --ref-text-file .\voice\teacher.txt --prefix ming_tts/lesson02 --out .\配音 --json
```

要点：**同一参考音频 + 固定 `--seed` = 稳定音色**；单段建议 ≤50 字；文本里可写副语言标签（`[Laughter]` / `[Sigh]` / `[Question-ah]`）。

模型与安装细节见 **[docs/tts.md](docs/tts.md)**。

## 退出码与错误模型

失败时 stderr 输出 `{"ok": false, "stage": ..., "error": ..., "hint": ...}`（`--json` 时为单行 JSON），退出码区分阶段，便于流水线判定重试策略：

| 退出码 | stage | 典型原因 |
|---|---|---|
| `0` | — | 成功 |
| `2` | config | 配置文件无法解析、离线模式却要提交 |
| `3` | connect | 服务未启动 / 端口不对 |
| `4` | workflow | 工作流不存在、JSON 损坏、含子图、节点类未安装 |
| `5` | param | 参数名不存在、同名输入歧义、绑定节点 id 不存在 |
| `6` | exec | 提交被拒（缺模型/必填项）、执行报错、任务从队列消失 |
| `7` | timeout | 等待超时（任务可能仍在跑，`prompt_id` 已打印） |
| `8` | io | 上传 / 下载 / 写盘失败 |

设计取舍：**不自动重试提交**（避免重复出图、重复计费），只在等待阶段容忍偶发 HTTP 抖动；任何阶段失败都保留 `prompt_id` 以便人工追查。

## 项目结构

```
comfyui-named-runner/
├── scripts/
│   ├── comfy.py                  # CLI 入口（10 个子命令）
│   ├── comfy_client.py           # 可复用的客户端库：配置/连接/转换/绑定/下载
│   ├── selftest.py               # 分层自检：离线结构 / 离线转换 / 本机 TTS / --live 联调
│   └── workflows/                # 随仓库分发的 API 格式工作流（api: 源）
│       ├── ming_dub_ip.json
│       ├── ming_dub_clone.json
│       └── tts_cosyvoice3_dub.json
├── registry.json                 # 别名路由表（别名 → 源文件 → 参数 → 默认值）
├── config.example.json           # 配置模板（复制为 config.json 使用）
├── docs/                         # 安装、CLI、配置、工作流、语音、HTTP 接口、架构、排错
├── examples/                     # Python 内嵌调用、批量配音脚本、示例 UI 工作流
├── SKILL.md                      # 作为 AI Agent Skill 安装时的入口说明
├── CHANGELOG.md
├── LICENSE
└── README.md
```

数据流：

```mermaid
flowchart LR
    A[别名 / 文件名 / 路径] --> B{resolve}
    B -->|registry 命中| C[source 定位]
    B -->|工作流目录发现| C
    C --> D{格式?}
    D -->|UI: nodes+links| E[ui_to_api<br/>需 /object_info]
    D -->|API: class_type| F[直接使用]
    E --> G[bind_params<br/>显式绑定 / 同名匹配 / 类型转换]
    F --> G
    G --> H[POST /prompt]
    H --> I[轮询 /history]
    I --> J[GET /view 下载产物]
    J --> K[--out 目录 + JSON 摘要]
```

## 作为 AI Agent Skill 使用

本项目同时是一个 **Agent Skill**：`SKILL.md` 描述能力边界与调用约定，AI 助手读入后即可在任意项目里驱动本机 ComfyUI（出图、出视频、配音），而不必每次重新摸索接口。

安装（CodeBuddy / Claude 风格的用户级 skill 目录）：

```powershell
$dst = "$env:USERPROFILE\.codebuddy\skills\comfyui-local"
git clone https://github.com/<your-name>/comfyui-named-runner.git $dst
Copy-Item $dst\config.example.json $dst\config.json   # 再改成自己的路径
python $dst\scripts\comfy.py doctor
```

之后在任何项目目录里都可以直接：

```powershell
python "$env:USERPROFILE\.codebuddy\skills\comfyui-local\scripts\comfy.py" run <别名> --json
```

## 文档

| 文档 | 内容 |
|---|---|
| [docs/install.md](docs/install.md) | 安装到任意目录 / 作为 skill 安装 / 前置条件 / 首次验证 |
| [docs/cli.md](docs/cli.md) | 全部子命令与参数、返回值结构、退出码 |
| [docs/configuration.md](docs/configuration.md) | 配置优先级、全部配置键、环境变量、离线模式 |
| [docs/workflows.md](docs/workflows.md) | 查找顺序、UI→API 转换规则、别名与参数绑定、实测兼容性 |
| [docs/tts.md](docs/tts.md) | 三条语音链路、模型下载、音色一致性、批量配音 |
| [docs/http-api.md](docs/http-api.md) | 用到的 ComfyUI HTTP 接口速查与失败对照 |
| [docs/architecture.md](docs/architecture.md) | 模块划分、关键函数、如何扩展（新格式 / 新产物类型） |
| [docs/troubleshooting.md](docs/troubleshooting.md) | 常见故障 → 定位 → 处理 |
| [SKILL.md](SKILL.md) | Agent Skill 定义（触发条件、调用约定、自愈原则） |

## 兼容性与实测

- **Python**：3.9+，仅标准库（已在 3.10 / 3.13 上使用）。
- **ComfyUI**：面向 0.38+ 的经典 `/prompt` + `/history` 接口，避免依赖新版 `/api/jobs`；在 **0.43.0 / 2211 个节点类** 的服务端上实测。
- **平台**：Windows 为主要开发平台（SAPI 链路仅 Windows）；HTTP 与转换逻辑本身平台无关。
- **已知限制**：

  - 不支持含**子图**（`definitions.subgraphs`）的 UI 工作流 → 请在界面里展开子图或导出 API 格式。
  - 未安装节点类的工作流会被明确拒绝，而不是提交后报错。
  - 自定义节点若把显示标签写入控件值，UI→API 会产生错位，`describe` 会给 warning → 改用 API 格式。

- **自检**：

  ```powershell
  python scripts\selftest.py          # L1 结构 + L2 转换 + L3 本机 TTS（不需要服务在跑）
  python scripts\selftest.py --live    # 额外：真实连接、比对 schema、跑一次 TTS
  ```

## 路线图

- [ ] `uv`/`pipx` 安装入口与 `comfy-runner` 控制台脚本
- [ ] 批量任务清单（YAML/JSONL）与并发队列
- [ ] `describe` 输出 JSON Schema，直接生成 CLI 参数
- [ ] 更多产物类型（3D 模型、字幕 SRT）落盘策略
- [ ] Linux / macOS 上的等价离线 TTS 引擎

## 许可与致谢

本项目以 **MIT** 许可证发布，见 [LICENSE](LICENSE)。

它站在这些项目的肩膀上：

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI)（GPL-3.0）—— 被调用方，本项目不包含其代码。
- [Ming-3.0-tts](https://github.com/inclusionAI/Ming-3.0-tts)（MIT）与 [ComfyUI-Ming-3-tts](https://github.com/Saganaki22/ComfyUI-Ming-3-tts)（MIT）—— 拟真人配音链路。
- [TTS-Audio-Suite](https://github.com/diodiogod/TTS-Audio-Suite)（MIT）—— CosyVoice3 备选引擎。
- Windows SAPI5 —— 离线兜底语音。

> 工作流里用到的模型各有自己的许可证（例如 Fun-CosyVoice3 为 Apache-2.0），商用前请自行核对。
