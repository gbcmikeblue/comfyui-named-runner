---
name: comfyui-local
description: 连接本机 ComfyUI 服务并按名称执行已有工作流，支持参数传入、产物下载、工作流查找与登记，内置文生图与图生图（Qwen Image 2.1）、离线文生语音（SAPI）与拟真人配音（Ming-3.0-tts 0.5B：内置音色 / 真人音色克隆）。用于任何需要调用本机 ComfyUI 出图/出视频/出语音/做配音的项目，也用于把新工作流登记成可复用别名。
description_zh: 连接本机 ComfyUI（127.0.0.1:8188）并按名称运行已有工作流、传参取回产物、查找/登记工作流、文本生成图像、图像重绘/风格迁移、文本转语音、拟真人配音与音色克隆。
---

# ComfyUI 本地调用

把本机 ComfyUI 当成一个「按名字调用 → 传参 → 拿结果」的执行后端。**本 skill 不启动、不重启、不关闭 ComfyUI**：服务由用户手动启动，skill 只负责发现端口、连接、提交与取回。

## 0. 适用目录与前置条件

| 项目 | 值 |
|---|---|
| 安装目录（用户级） | `<用户目录>/.codebuddy/skills/comfyui-local`（任意目录亦可） |
| 入口脚本 | `scripts/comfy.py`（CLI）、`scripts/comfy_client.py`（可被其他项目 import） |
| 依赖 | 仅 Python 标准库（3.9+） |
| 服务地址 | `http://127.0.0.1:8188`（端口冲突时自动扫描 8188–8192） |
| 配置 | `<安装目录>/config.json`（本机路径），优先级：默认值 < config.json < 环境变量 < 命令行 |
| 别名表 | `<安装目录>/registry.json`（`register` 会改写） |
| 图像链路依赖 | ComfyUI 0.4x+ 自带的 `TextEncodeQwenImage21`；权重 `qwen_image_2.1_int8_convrot.safetensors`（unet）、`qwen3vl_8b_int8_convrot.safetensors`（clip）、`qwen_image_2.1_vae_bf16.safetensors`（vae） |

启动方式（用户手动）：在 ComfyUI Desktop 里点 Launch，或用**带 torch 的** Python 运行 `main.py`。启动后：

```powershell
python scripts\comfy.py doctor     # 体检：服务、节点、registry、路径、torch
python scripts\comfy.py wait       # 等服务就绪（默认 180s）
```

> 同时只跑一个实例：Desktop 的 Launch 与命令行启动并存会抢显存，`doctor` 只能看到实际监听 8188 的那个。
> 手动启动时必须补齐 Desktop 的目录参数（`--extra-model-paths-config` / `--input-directory` / `--output-directory`），否则模型与产物会落到错误位置。

## 1. 调用方式

```powershell
$COMFY = "<安装目录>\scripts\comfy.py"

python $COMFY doctor                          # 体检 + 配置
python $COMFY list --all                      # 已登记别名 + 可发现工作流
python $COMFY describe ming                   # 节点/参数/产物结构
python $COMFY t2i "雨后的江南小巷，水彩" --out .\图    # 文生图（Qwen Image 2.1）
python $COMFY i2i "改成油画风格" --image .\in.png --out .\图   # 图生图 / 风格迁移
python $COMFY dub "你好" --out .\配音            # 拟真人配音（内置音色）
python $COMFY dub "你好" --ref-audio .\v.wav --ref-text "样本原话" --out .\配音   # 音色克隆
python $COMFY tts "你好，世界" --out .\out        # 文生语音（SAPI 保底）
python $COMFY run ming -p text="你好" --out .\out  # 按别名执行
python $COMFY nodes "Qwen"                     # 查已安装节点类
python $COMFY interrupt                       # 中断当前执行
```

通用全局参数（子命令前后都能写）：`--json`（机器可读输出）、`--base-url`、`--config`。

`run` 关键参数：

| 参数 | 说明 |
|---|---|
| `-p/--set KEY=VALUE` | 传参，可重复；值自动转 int/float/bool/JSON，也可用 registry 声明的 type 强制 |
| `--seed N` | 覆盖图里所有 `seed` / `noise_seed` |
| `--input-image path` | 上传本地图片到 input 目录并绑定到 `image` 输入（img2img / i2v 用） |
| `--input-audio path` | 上传本地音频到 input 目录并绑定到 `audio` 输入（配音参考音色用） |
| `--out DIR` | 产物落盘目录，默认 `.\comfy-out` |
| `--dry-run` | 只打印转换后的 API 工作流，不提交（可配 `--schema` 离线跑） |
| `--no-wait` | 提交后立即返回 `prompt_id` |
| `--timeout N` | 等待上限，默认 `timeout_job`（1800s） |

成功时 stdout 输出 `{"ok":true,"prompt_id":...,"elapsed_sec":...,"files":[...],"text_outputs":{...},"applied":{...}}`。

## 2. 配置项

文件：`<安装目录>\config.json`（`doctor --write-config` 可回写当前生效值）。

| 键 | 含义 |
|---|---|
| `base_url` | 服务地址，默认 `http://127.0.0.1:8188` |
| `port_scan` | 连接失败时扫描的端口（默认 8188–8192） |
| `comfyui_root` | ComfyUI 代码根目录（其余路径由此派生） |
| `workflows_dir` | UI 工作流目录（`user:<path>` 的基准） |
| `output_dir` / `input_dir` | 服务端输出/输入目录（诊断与上传用） |
| `python` | `doctor` 检查 torch 用的解释器（默认自动探测 `.venv`） |
| `timeout_submit` / `timeout_job` / `poll_interval` | 提交、执行、轮询 |
| `client_id` | 写入 `/prompt` 的客户端标识 |

环境变量覆盖：`COMFY_URL`、`COMFYUI_ROOT`、`COMFY_WORKFLOWS_DIR`、`COMFY_OUTPUT_DIR`、`COMFY_INPUT_DIR`、`COMFY_SKILL_CONFIG`。

## 3. 工作流：查找、转换、复用

**查找顺序**（`run` / `describe` 的 `name` 参数）：

1. `registry.json` 里的别名（大小写不敏感）
2. 直接路径（`.json` 文件）
3. `workflows_dir` 下的文件名 / 相对路径（精确 → 大小写不敏感 → 唯一子串匹配）
4. 都找不到 → `workflow` 错误并提示用 `list --all`

**格式支持**：

- **UI 格式**（`nodes` + `links`）→ 自动转 API：按 `/object_info` 的输入顺序还原 `widgets_values`，解析连线，处理 `mode=4 旁通`（按类型透传）、`mode=2 静音`（移除）、`Reroute`、`seed + 控制值`。
- **API 格式**（`{"1": {"class_type": ...}}`）→ 直接使用，可完全离线校验。
- **不支持**：带子图（`definitions.subgraphs`）、未安装节点类的工作流 —— 明确拒绝并提示展开子图或导出 API 格式。

**自定义节点多的工作流**：节点常把显示标签写进控件值导致错位，`describe` 会给 warning；这类图请在 GUI 里 Export (API) 后再 `register`。

**登记成别名**：

```powershell
# 推荐：GUI 里 Export (API) 导出的图，参数显式绑定（NAME=NODE_ID.INPUT，或 NAME=NODE@标题片段.INPUT）
python $COMFY register my_flow --source file:.\my_t2i_api.json `
  --param prompt=27.text --param width=30.width --param height=30.height `
  --default width=1024 --default height=1024

# 简单 UI 图（核心节点、无子图）：参数靠自动绑定（图里同名输入唯一时）
python $COMFY register my_simple --source user:my_simple_flow.json --title "简单链路"
```

> 图像/语音的现成别名（`t2i`、`i2i`、`ming`、`ming_clone`…）已随仓库分发，见 §4、§5；ComfyUI 自带的 Qwen 模板图带**子图**，不能直接登记，可用内置别名或自己在 GUI 里展开后导出 API。

`source` 三种写法：`user:<workflows_dir 相对路径>`、`api:<安装目录>\scripts\workflows\相对路径`（随仓库分发的 API 图）、`file:<绝对路径>`。

**参数约定**：

- 显式绑定优先（`node` / `node_title` / `node_class` + `input`）。
- 未显式绑定的参数按**输入名**自动绑定；同名输入出现在多个节点时报 `param` 错误并列出候选，不会猜。
- 未声明的参数名 → `param` 错误（退出码 5），并给出该图可用输入清单。
- `input` 支持 **ComfyUI v3 节点的带点号键名**（如 `task.voice`、`task.reference_text`）。
- 值转换：`true/false`→bool、整数→int、小数→float、`[`/`{` 开头→尝试 JSON、其余→字符串；`type` 可强制。

## 4. 图像：文生图与图生图（Qwen Image 2.1）

两条链路都以别名内置（`api:` 源，随仓库分发 API 图），**不依赖用户目录里带子图的模板工作流**。

| 别名 | 能力 | 尺寸由谁决定 |
|---|---|---|
| `t2i` | 文本 → 图像 | `--width` / `--height`（默认 1024×1024，Qwen 2.1 原生支持到 2K） |
| `i2i` | 参考图 → 风格迁移 / 内容变换 | 跟随参考图比例，`--resolution` 控制缩放预算（默认 1024） |

图结构（两者同构，i2i 多一个 `LoadImage`）：

```
UNETLoader ┐
CLIPLoader ┤→ TextEncodeQwenImage21 ─┬→ KSampler → VAEDecode → SaveImageAdvanced
VAELoader  ┘   ↑ images.image_1      └→ latent_image（i2i 用，参考图尺寸）
               LoadImage（i2i）        EmptyLatentImage（t2i 用，width/height）
```

```powershell
# 文生图：任意宽高
python $COMFY t2i "雨后的江南小巷，水彩，细节丰富" --width 1536 --height 864 --out .\图

# 图生图：上传本地图 → 换风格 / 换材质 / 改内容
python $COMFY i2i "改成油画风格，笔触粗犷" --image .\photo.png --out .\图

# 固定种子换提示词 = 同构图试探
python $COMFY t2i "同一场景，夜晚，霓虹灯" --seed 42 --out .\图
```

关键参数（两条链路一致）：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--steps` / `--cfg` / `--denoise` | 25 / 1.0 / 1.0 | Qwen Image 2.1 用低 CFG，别照搬 SD 的 7 |
| `--seed` | 42 | 固定后可复现；只影响采样 |
| `--sampler-name` / `--scheduler` | `euler` / `simple` | 与本机官方模板一致 |
| `--model` / `--clip` / `--vae` | 见 §0 依赖 | 换 `-bf16` / `-pe_t2i` / `-pe_i2i` 变体时用 |
| `--format` / `--bit-depth` | `png` / `8-bit` | 走 `SaveImageAdvanced` 的动态下拉子输入 |
| `--prefix` | `Qwen_image_2.1/t2i`、`/i2i` | ComfyUI 输出前缀 |
| `-p KEY=VALUE` | — | 直传 registry 里的其它参数（如 `color_space`、`unet_name`） |

要点：

- **i2i 的输出尺寸跟随参考图**：编码节点的 latent 输出就是「第一张参考图尺寸的空 latent」，官方明确说明换成别的尺寸会让编辑结果偏移 —— 所以 i2i 不暴露 `--width/--height`。
- **参考图是条件而非加噪起点**：Qwen 2.1 把参考图编码成 `reference_latents`，所以 `--denoise` 保持 1.0，调低没有「更像原图」的效果。
- **多图参考**：图里 `images.image_1..image_16` 都可接，CLI 只绑定第一张；多图用 `run i2i -p images.image_2=...` 或另建工作流登记。
- **没有隐式猜测**：`registry.json` 把 `width/height/seed/steps/...` 全部显式指到节点 id，不依赖同名自动匹配。
- **与自带模板的关系**：ComfyUI 自带的 `qwen_image_2_1_t2i.json` / `image_qwen_image_2_1_image_edit.json` 用了**子图**，本工具的 UI→API 转换器会拒绝；内置别名是用等价节点手写的 API 图，可离线校验、可直接复用。

## 5. 配音与语音：三条链路

### 5.1 拟真人配音 `ming` / `ming_clone`（Ming-3.0-tts 0.5B，主链路）

| 项 | 内容 |
|---|---|
| 上游模型 | `inclusionAI/Ming-3.0-tts`（MIT）：0.5B 稠密 + 7.9B-A1.3B MoE，多语种、零样本克隆、音色设计 |
| ComfyUI 移植 | `Saganaki22/ComfyUI-Ming-3-tts`（MIT）：`MingLoadModel` / `MingGenerate` / `MingSave` |
| 资源占用 | 显存 ~2.5–2.8 GiB，权重 2.76 GiB，44.1 kHz 单声道 |
| 别名 | `ming`（内置音色）、`ming_clone`（参考音频 + 逐字转写克隆） |
| 权重位置 | `<checkpoints 根>\Ming-3.0-tts-0.5b\model.safetensors` |

```powershell
# 内置中文音色（开箱即用）
python $COMFY dub "弯弯的月儿小小的船。" --voice 灵小安 --out .\配音

# 克隆真人音色：10-30s 干净单人说录音 + 它的逐字转写（不是要合成的新句子）
python $COMFY dub "小兔子乖乖，把门儿开开。" --ref-audio .\voice\teacher.wav `
  --ref-text "这是一段十五秒左右的普通话朗读示范。" --language Chinese --out .\配音

# 长文本批量：--text-file 每行一句，--prefix 区分课时
python $COMFY dub --text-file .\lesson02.txt --ref-audio .\voice\teacher.wav `
  --ref-text-file .\voice\teacher.txt --prefix ming_tts/lesson02 --out .\配音 --json
```

要点：

- **音色一致性**：同一 reference 音频 + 固定 `--seed` 会让整套课件音色稳定；换 `--seed` 只改变随机性，不改变音色。
- **内置中文音色有 100+ 个**（清单见节点仓库 `docs/instructions.md`）。名字要原样传入，不要翻译。
- **task 不止 ip/clone**：`voice_design`、`freeform`、`basic`、`emotion`、`dialect`；改这些需新建工作流或用 `run ming -p task.xxx=...` 显式传键。
- **文本内可用副语言标签**：`[Laughter]`、`[Sigh]`、`[Breathing]`、`[Question-ah]`。
- 单段建议 ≤50 字；`--max-steps` 是每段音频块上限（≈80 ms/块），不是语速。

### 5.2 离线保底 `tts`（Windows SAPI）

| 项 | 内容 |
|---|---|
| 别名 | `tts`（源 `user:tts_zh_sapi.json`，示例见 `examples/comfyui-workflows/`） |
| 图结构 | `LocalTTS_SAPI`(1) → `SaveAudioAdvanced`(2, flac) |
| 节点 | 自建 `ComfyUI-LocalTTS-SAPI`，离线调用 Windows SAPI5，无模型、无网络 |
| 参数 | `text`（必填）、`voice`（`auto` 优先 zh-CN）、`rate`(-10..10)、`volume`(0..100)、`filename_prefix` |

```powershell
python $COMFY tts "第一句。第二句。" --voice "Microsoft Huihui Desktop" --rate 2 --out .\out
```

定位：机器味但零成本、秒级、无 GPU 占用，适合占位音、调试与兜底；正式配音走 4.1。

### 5.3 备选 `cosyvoice3`（TTS Audio Suite，多引擎）

需要方言/多语种/多角色对话/SRT 时间轴时再切；日常中文配音优先 `ming`（更轻、更快、许可证更干净）。

```powershell
python $COMFY run cosyvoice3 --input-audio .\voice\teacher.wav -p text="春天来了。" --out .\out
```

> 坑：`CosyVoiceEngineNode` 的 `instruct_text` 一旦给了就走 instruct 模式并**忽略** `reference_text`；两者只能留一个。

## 6. 错误处理

失败时 stderr 输出 `{"ok":false,"stage":...,"error":...,"hint":...}`（加 `--json` 为单行 JSON），退出码区分阶段：

| 退出码 | stage | 典型原因 / 处理 |
|---|---|---|
| 2 | config | 配置文件无法解析、`--schema` 读不到、离线模式却要提交 → 修配置 |
| 3 | connect | 服务未启动 / 端口不对 → 手动启动 ComfyUI 后 `wait`；或 `--base-url` 指定端口 |
| 4 | workflow | 工作流不存在、JSON 损坏、用了子图、节点类未安装 → `describe`/`list --all` 核对 |
| 5 | param | 参数名不存在、同名输入有歧义、绑定节点 id 不存在 → 显式 `--param` 绑定 |
| 6 | exec | 提交被拒（缺模型/必填项）、执行报错、任务从队列消失 → 看 `hint` 里的节点级错误 |
| 7 | timeout | 等待超时（`--timeout`）；任务可能仍在跑 → 记下 `prompt_id` 查 `/history` |
| 8 | io | 上传/下载失败、产物写盘失败 |

自愈要点：**不重试提交**（避免重复出图/配音），只在等待阶段容忍偶发 HTTP 抖动；任何阶段失败都保留已生成的 `prompt_id`，便于人工追查。

## 7. 验证可被其他项目调用

```powershell
# 1) 离线自检（不需要 ComfyUI 在跑）：结构 / 转换 / 参数 / SAPI 发声
python scripts\selftest.py

# 2) 手动启动 ComfyUI 后，真实联调：节点加载、schema 一致、跑一次 TTS + 一次配音 + 一次出图 + 一次图生图
python scripts\selftest.py --live
```

跨项目验证（任选一个项目目录执行）：

```powershell
cd D:\任意项目
python "<安装目录>\scripts\comfy.py" doctor --json
python "<安装目录>\scripts\comfy.py" t2i "跨项目出图测试" --width 512 --height 512 --out .\comfy-out --json
python "<安装目录>\scripts\comfy.py" dub "跨项目配音测试" --voice 灵小安 --out .\comfy-out --json
Get-ChildItem .\comfy-out -Recurse -Include *.png,*.flac   # 应看到图像与音频产物
```

判定标准：

- `doctor --json` 的 `checks` 里 `server`、`node:MingLoadModel`、`node:MingGenerate`、`node:TextEncodeQwenImage21`、`ming_model`、`qwen_model:unet_name` / `qwen_model:clip_name` / `qwen_model:vae_name` 全部为 `true`。
- `dub --json`：`ok=true`、`files[].kind=="audio"`、`bytes>5000`，产物可用播放器打开。
- `t2i --json`：`ok=true`、`files[].kind=="images"`、`bytes>50000`（1024² 通常 300 KB~1.5 MB）。
- `i2i --json`：`ok=true`、`files[].kind=="images"`，且产物宽高比与参考图一致（这是参考图真的生效的判据）。

**给其他项目调用**：三选一 ——

1. 直接命令行：`python <安装目录>\scripts\comfy.py ... --json`，解析 stdout 的 JSON。
2. Python 内 import：`sys.path.insert(0, r"<安装目录>\scripts")` 后 `import comfy_client as C`，用 `C.load_config()` / `C.Server(cfg).submit(...)` / `C.ui_to_api(...)` / `C.bind_params(...)`（示例见 `examples/python_embed.py`）。
3. 项目内约定：把 `COMFY_URL` / `COMFY_WORKFLOWS_DIR` 写进项目环境变量，其它机器只需改这两个值。

## 8. 参考

- `docs/http-api.md`：用到的 ComfyUI HTTP 接口、请求/响应要点、失败样例。
- `docs/workflows.md`：工作流查找、UI→API 转换规则细节、登记模板。
- `docs/image.md`：文生图 / 图生图链路、Qwen Image 2.1 模型与参数、实测性能、排错。
- `docs/tts.md`：三条语音链路、模型下载、音色一致性与批量配音。
- `docs/troubleshooting.md`：常见故障定位表。
