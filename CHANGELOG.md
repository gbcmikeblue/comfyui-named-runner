# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的结构，版本号遵循语义化版本。

## [Unreleased]

### Planned
- `uv` / `pipx` 安装入口，提供 `comfy-runner` 控制台脚本。
- 批量任务清单（YAML / JSONL）与并发队列。
- `describe --format schema` 输出参数 JSON Schema。
- 3D 模型、SRT 字幕等更多产物类型的落盘策略。

## [0.1.0] - 2026-11-01

### Added
- **CLI**（`scripts/comfy.py`，11 个子命令）：`doctor`、`wait`、`list`、`describe`、`run`、`tts`、`dub`、`register`、`nodes`、`interrupt`。
- **客户端库**（`scripts/comfy_client.py`，仅标准库）：配置合并、端口扫描与服务发现、提交/轮询/下载、UI→API 转换、参数绑定、产物收集。
- **UI → API 转换器**：按 `/object_info` 顺序还原控件值，解析 `links`，处理 `mode=4` 旁通（按类型透传）、`mode=2` 静音（移除）、`Reroute` 穿透、`seed + 控制值` 双 token，忽略 Note/Primitive 节点；对子图与未安装节点类直接拒绝。
- **别名机制**（`registry.json`）：`user:` / `api:` / `file:` 三种 source，显式绑定（`node` / `node_title` / `node_class` + `input`）与同名自动绑定，值类型转换，ComfyUI v3 带点号键名（如 `task.voice`）支持。
- **语音链路**：Ming-3.0-tts 0.5B 拟真人配音（内置音色 `ming` / 零样本克隆 `ming_clone`）、Windows SAPI 离线兜底（`tts`）、CosyVoice3 备选（`cosyvoice3`）；随仓库分发 3 个 API 格式工作流。
- **可编程接口**：全命令 `--json`，7 个阶段独立退出码（2–8），失败保留 `prompt_id`，不自动重试提交。
- **自检**（`scripts/selftest.py`）：L1 离线结构、L2 离线转换与参数绑定、L3 本机 TTS 发声，`--live` 追加真实服务联调。
- **文档**：安装、CLI、配置、工作流、语音、HTTP 接口、架构、排错共 8 篇；中英文 README；`SKILL.md` 作为 Agent Skill 入口。
