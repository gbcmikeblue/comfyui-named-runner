# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的结构，版本号遵循语义化版本。

## [Unreleased]

### Added
- **图像链路（Qwen Image 2.1）**：新增 `t2i`（文本 → 图像）与 `i2i`（参考图 → 风格迁移 / 内容变换）两个子命令，随仓库分发 `scripts/workflows/qwen_image_2_1_t2i.json` / `qwen_image_2_1_i2i.json`（API 格式，避开官方模板的子图）。
- `registry.json` 新增 `t2i` / `i2i` 别名：`prompt` / `negative_prompt` / `steps` / `cfg` / `seed` / `denoise` / `width`（t2i）/ `resolution`（i2i）/ `format.bit_depth` 等全部显式绑定到节点 id。
- `doctor` 增加 `node:TextEncodeQwenImage21`、`node:QwenImage21Cache`（可选）与 `qwen_model:unet_name` / `clip_name` / `vae_name` 检查。
- `selftest.py` 增加 L1 图像工作流、L2 文生图/图生图参数绑定（含 v3 动态下拉与 autogrow 的点号键）、L4 真实出图与图生图联调。
- 新增 `docs/image.md`：两条链路的结构、模型变体、参数语义、实测性能与排错；`SKILL.md`、`docs/cli.md`、`docs/workflows.md`、中英文 README 同步更新。
- 新增 `docs/qwen-image-prompting.md`：提示词写法汇总（官方 PE 重写规范的 8 步结构、编辑规范、固定句式、参数搭配、14 条误区），每条结论标注官方/社区/第三方来源与可信度。
- 修正 `docs/image.md` 中负向提示词的描述：默认 `cfg=1` 时 ComfyUI 跳过负条件分支，`--negative-prompt` 实际不生效。

### Changed
- `docs/workflows.md` 补充 v3 动态输入（`COMFY_DYNAMICCOMBO_V3` → `format.bit_depth`、`COMFY_AUTOGROW_V3` → `images.image_1`）的绑定写法。
- README（中/英）新增「平台支持」章节：三平台的环境要求、安装与配置差异、启动与运行方式、路径与命令行差异、换行符 / BOM / 权限等兼容性说明、各平台排错表、子命令 × 平台矩阵。

### Fixed
- `selftest.py` 在非 Windows 平台不再必然失败：`L3`（SAPI 合成）与 `--live` 的 TTS 三项改为标注 `SKIP` 跳过，其余检查（连接、配音、出图、图生图）照常执行。

### Planned
- `uv` / `pipx` 安装入口，提供 `comfy-runner` 控制台脚本。
- 批量任务清单（YAML / JSONL）与并发队列。
- `describe --format schema` 输出参数 JSON Schema。
- 3D 模型、SRT 字幕等更多产物类型的落盘策略。

## [0.1.0] - 2026-11-01

### Added
- **CLI**（`scripts/comfy.py`，10 个子命令）：`doctor`、`wait`、`list`、`describe`、`run`、`tts`、`dub`、`register`、`nodes`、`interrupt`。
- **客户端库**（`scripts/comfy_client.py`，仅标准库）：配置合并、端口扫描与服务发现、提交/轮询/下载、UI→API 转换、参数绑定、产物收集。
- **UI → API 转换器**：按 `/object_info` 顺序还原控件值，解析 `links`，处理 `mode=4` 旁通（按类型透传）、`mode=2` 静音（移除）、`Reroute` 穿透、`seed + 控制值` 双 token，忽略 Note/Primitive 节点；对子图与未安装节点类直接拒绝。
- **别名机制**（`registry.json`）：`user:` / `api:` / `file:` 三种 source，显式绑定（`node` / `node_title` / `node_class` + `input`）与同名自动绑定，值类型转换，ComfyUI v3 带点号键名（如 `task.voice`）支持。
- **语音链路**：Ming-3.0-tts 0.5B 拟真人配音（内置音色 `ming` / 零样本克隆 `ming_clone`）、Windows SAPI 离线兜底（`tts`）、CosyVoice3 备选（`cosyvoice3`）；随仓库分发 3 个 API 格式工作流。
- **可编程接口**：全命令 `--json`，7 个阶段独立退出码（2–8），失败保留 `prompt_id`，不自动重试提交。
- **自检**（`scripts/selftest.py`）：L1 离线结构、L2 离线转换与参数绑定、L3 本机 TTS 发声，`--live` 追加真实服务联调。
- **文档**：安装、CLI、配置、工作流、语音、HTTP 接口、架构、排错共 8 篇；中英文 README；`SKILL.md` 作为 Agent Skill 入口。
