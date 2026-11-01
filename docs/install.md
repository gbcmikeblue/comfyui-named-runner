# 安装与首次验证

本项目有两种等价的使用形态，安装方式只差"放在哪个目录"：

| 形态 | 目录约定 | 适用场景 |
|---|---|---|
| **独立工具** | 任意目录（如 `D:\tools\comfyui-named-runner`） | 在终端 / CI / 自己的 Python 项目里调用 |
| **Agent Skill** | `<用户目录>/.codebuddy/skills/comfyui-local`（或你的 agent 约定的 skill 目录） | 让 AI 助手在任意项目里自动驱动本机 ComfyUI |

代码里不写死任何路径：配置文件放在**仓库根目录**的 `config.json`，脚本在 `scripts/`，两者通过 `__file__` 相对定位。所以两种形态可以共存，也可以直接拷贝目录。

## 1. 前置条件

| 项 | 要求 |
|---|---|
| Python | 3.9+，**不需要任何第三方包** |
| ComfyUI | 能正常出图的任意安装；推荐 ComfyUI Desktop（自动管理 `.venv` 与端口） |
| 服务状态 | **必须已经启动**——本工具不启动、不重启、不关闭服务 |
| 网络 | 只需要能访问 `127.0.0.1:<port>`，不出网 |

> 本篇命令以 Windows PowerShell 为例。macOS / Linux 的差异（`python3`、`chmod +x`、`venv/` 与 `.venv/`、SAPI 不可用、换行符与 BOM）见 README 的 [平台支持](../README.md#平台支持windows--macos--linux)。

> 手动启动 ComfyUI 时务必用**带 torch 的那个 Python**。ComfyUI Desktop 的实际运行环境通常是 `<root>\.venv\Scripts\python.exe`，而 `<install>\standalone-env` 只是引导环境（没有 torch），用它启动会失败。同时只跑一个实例：Desktop 的 Launch 与命令行启动并存会互相抢显存。

## 2. 安装

### 2.1 独立工具

```powershell
git clone https://github.com/<your-name>/comfyui-named-runner.git D:\tools\comfyui-named-runner
cd D:\tools\comfyui-named-runner
Copy-Item config.example.json config.json
notepad config.json      # 至少改 comfyui_root / workflows_dir
```

### 2.2 Agent Skill

```powershell
$dst = "$env:USERPROFILE\.codebuddy\skills\comfyui-local"
git clone https://github.com/<your-name>/comfyui-named-runner.git $dst
Copy-Item "$dst\config.example.json" "$dst\config.json"
python "$dst\scripts\comfy.py" doctor
```

`SKILL.md` 会被 agent 自动读取，里面写清了触发条件、调用约定与"不启动服务"的边界。

### 2.3 可选：复制示例 UI 工作流

`examples/comfyui-workflows/tts_zh_sapi.json` 是一个两节点的离线 TTS 工作流（UI 格式），`registry.json` 里的 `tts` 别名通过 `user:tts_zh_sapi.json` 引用它：

```powershell
Copy-Item .\examples\comfyui-workflows\tts_zh_sapi.json "<ComfyUI>\user\default\workflows\"
```

它依赖配套自定义节点 `ComfyUI-LocalTTS-SAPI`（`LocalTTS_SAPI` / `LocalTTS_VoiceList`，调用 Windows SAPI5）。没有这个节点也不影响其它功能——把 `registry.json` 里的 `tts` 条目删掉或改指到你自己的 TTS 工作流即可。

## 3. 首次验证

按顺序做这四步，每步都能独立定位问题：

```powershell
# ① 离线结构自检：不需要 ComfyUI 在跑
python scripts\selftest.py

# ② 体检：服务 / 端口 / 路径 / 节点类 / 模型 / torch
python scripts\comfy.py doctor

# ③ 看看有哪些工作流可调用
python scripts\comfy.py list --all

# ④ 跑一次真实任务（换成你已有的别名）
python scripts\comfy.py run <别名> --out .\out --json
```

`doctor` 的关键检查项（`--json` 时为 `checks` 字段）：

| 检查项 | 期望 | 不通过时看 |
|---|---|---|
| `server` | `true` | ComfyUI 是否启动、端口是否被换（`--base-url` / `port_scan`） |
| `port` | 实际监听端口 | Desktop 的 `portConflict=auto` 会换端口 |
| `paths` | 工作流/输出目录存在 | `config.json` 的 `comfyui_root` 是否指对 |
| `node:<Class>` | 关键节点类存在 | 自定义节点是否装好、**装完是否重启过** ComfyUI |
| `model:<name>` | 关键权重存在 | `extra_model_paths` 是否生效、文件层级是否多套了一层 |
| `torch` | 运行环境能 `import torch` | 是否用错了 Python（见上文） |
| `registry` | 别名可解析 | 工作流是否被改名/另存，`list` 会标 `[文件缺失]` |

判定"能用了"的标准：`doctor --json` 里 `server`、关键 `node:*` / `model:*`（图像链路看 `node:TextEncodeQwenImage21` 与 `qwen_model:*`）为 `true`；`run`/`t2i`/`i2i`/`dub` 的 `--json` 输出 `ok=true`，`files[].bytes > 0`，产物可被播放器/查看器正常打开。

## 4. 真实联调（可选）

```powershell
python scripts\selftest.py --live
```

追加这些事：比对本机真实 `/object_info` 与内置合成 schema 的字段差异、执行一次 SAPI TTS、一次拟真人配音、一次文生图、一次图生图，并校验产物能被正确收集。

## 5. 升级与卸载

- **升级**：`git pull`。`config.json` 与 `registry.json` 都在仓库根目录且被 `.gitignore` 保护，不会被覆盖。
- **多机同步**：只需要同步 `config.json`（改路径）与 `registry.json`（工作流别名），代码可以重新 clone。
- **卸载**：删目录即可，本工具不写注册表、不装服务、不留后台进程。

## 6. 换机器时的最小改动

| 场景 | 只改这些 |
|---|---|
| 同机换 ComfyUI 版本 | 一般不用改；跑一次 `doctor` 确认节点类 |
| 换机器 | `config.json` 的 `comfyui_root`（其余派生路径会自动算） |
| 端口变了 | `port_scan` 加进新端口，或每次 `--base-url` |
| 工作流目录不在默认位置 | `COMFY_WORKFLOWS_DIR` 环境变量 |

`doctor --write-config` 可以把当前生效的配置（含命令行与环境变量的结果）回写到 `config.json`，方便固化成固定值。
