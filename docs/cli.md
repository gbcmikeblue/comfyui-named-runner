# CLI 参考

入口：`python scripts/comfy.py <子命令> [参数]`

全局参数**写在子命令前后都行**：

| 参数 | 说明 |
|---|---|
| `--json` | 机器可读输出。成功时 stdout 为单个 JSON 对象；失败时 stderr 为**单行** JSON |
| `--base-url URL` | 覆盖服务地址，如 `http://127.0.0.1:8189` |
| `--config PATH` | 指定配置文件，跳过默认查找顺序 |

所有命令在 Windows 下会把 stdout/stderr 强制成 UTF-8，中文文本可以直接通过管道传给其他程序。

---

## `doctor`

体检：服务、端口、路径、节点类、模型权重、torch、registry。任一检查失败时退出码为 `3`。

```powershell
python scripts\comfy.py doctor
python scripts\comfy.py doctor --write-config   # 把当前生效配置回写 config.json
python scripts\comfy.py doctor --json
```

`--json` 结构：

```json
{"ok": true,
 "config": {"base_url": "...", "comfyui_root": "...", "...": "..."},
 "runtime": {"base_url": "...", "comfyui_version": "0.43.0", "torch": "...", "device": "cuda:0 ..."},
 "checks": [{"ok": true, "check": "server", "detail": "..."}],
 "config_written": "D:\\...\\config.json"}
```

## `wait`

等待**你手动启动**的 ComfyUI 就绪（本工具不会替你启动服务）。

| 参数 | 默认 | 说明 |
|---|---|---|
| `--timeout` | `180` | 最长等待秒数，超时以 `timeout`（7）退出 |
| `--interval` | `3.0` | 轮询间隔 |

## `list`

列出已登记别名，`--all` 时追加扫描 `workflows_dir` 里**尚未登记**的工作流。

| 参数 | 说明 |
|---|---|
| `--all` | 扫描工作流目录（否则只看 `registry.json`） |
| `--filter KEYWORD` | 对整行 JSON 做关键词过滤 |

输出里 `[文件缺失]` 表示 source 指向的文件已不存在（工作流改名/另存导致的典型现象）。

## `describe`

查看某个工作流转换后的节点、可绑定参数、预期产物，**不提交**。

| 参数 | 说明 |
|---|---|
| `NAME`（位置） | 别名 / 文件名 / 路径（同名解析见 [workflows.md](workflows.md)） |
| `--schema PATH` | 用保存的 `/object_info` 快照代替实时查询（离线可用） |

输出会打印每个节点的 `[id] class_type + 标题` 及其输入值（连线显示为 `<- 上游节点.输出槽`），并在 `warnings` 里给出控件错位、缺必填值等问题。

## `run`

按名称执行工作流。这是最常用的命令。

| 参数 | 说明 |
|---|---|
| `NAME`（位置） | 别名 / 文件名 / 路径 |
| `-p`, `--set KEY=VALUE` | 传参，可重复。值自动转 `int` / `float` / `bool` / JSON；`registry` 里声明了 `type` 时按其转换 |
| `--seed N` | 覆盖图里所有 `seed` / `noise_seed` |
| `--input-image PATH` | 上传本地图片到服务端 input 目录，并绑定到 `image` 输入（img2img / i2v） |
| `--input-audio PATH` | 上传本地音频同上，绑定到 `audio` 输入（参考音色/声音克隆） |
| `--out DIR` | 产物目录，默认 `.\comfy-out`；每次运行以 `<别名>-<时间戳>-<prompt_id前8位>` 作为文件名前缀 |
| `--timeout N` | 等待上限秒数，默认取配置 `timeout_job`（1800） |
| `--dry-run` | 只打印转换后的 API 图，不提交（可与 `--schema` 组合离线跑） |
| `--no-wait` | 提交后立即返回 `prompt_id`，不等结果 |
| `--no-download` | 只返回远端文件名，不下载产物 |
| `--schema PATH` | 用 `object_info` 快照代替实时查询（需配合 `--dry-run`） |

成功输出：

```json
{"ok": true, "workflow": "ming", "title": "拟真人配音·内置音色…",
 "base_url": "http://127.0.0.1:8188", "prompt_id": "uuid",
 "elapsed_sec": 7.6, "output_dir": "C:\\proj\\comfy-out",
 "applied": {"text": {"node": "2", "input": "text", "value": "你好"}},
 "files": [{"path": "…\\ming_…_3_audio_0.flac", "kind": "audio", "node": "3",
            "source": "dub_00001_.flac", "bytes": 184320}],
 "text_outputs": {}, "warnings": []}
```

`ok` 在"没有取到任何文件也没有文本产物"时为 `false`——常见原因是工作流里没有 `Save*` 输出节点。

## `tts`

文生语音的便捷封装，等价于 `run <--workflow>` 并自动带上 `text/voice/rate/volume/prefix`。

| 参数 | 说明 |
|---|---|
| `TEXT`（位置） | 要合成的文本；给了 `--text-file` 时可省略 |
| `--text-file PATH` | 从 UTF-8 文件读取（整篇作为一个 `text` 值） |
| `--workflow ALIAS` | 默认 `tts` |
| `--voice NAME` | 语音名，默认 `auto`（优先 zh-CN） |
| `--rate -10..10` / `--volume 0..100` | 语速 / 音量 |
| `--prefix PREFIX` | ComfyUI 输出前缀，默认 `audio/tts` |
| `--out` / `--timeout` / `--dry-run` / `--no-wait` / `--no-download` | 同 `run`（`--timeout` 默认 600） |

> `--voice` / `--rate` / `--volume` 是 SAPI 工作流的参数名。换成别的 TTS 引擎时，请用 `run <别名> -p ...` 传该引擎自己的参数名。

## `dub`

拟真人配音 / 音色克隆（Ming-3.0-tts 0.5B）。**给了 `--ref-audio` 自动走 `ming_clone`，否则走 `ming`**。

| 参数 | 说明 |
|---|---|
| `TEXT` / `--text-file` | 要配音的文本 |
| `--workflow ALIAS` | 手动指定别名（默认按有无 `--ref-audio` 自动选） |
| `--voice NAME` | 内置音色名（`灵小安` / `灵朵儿` / `花小呗` …），仅 `ming` 有效；名字原样传入，不要翻译 |
| `--ref-audio PATH` | 真人参考音频（10–30 s，单人、无 BGM），上传后绑定到 `audio` 输入 |
| `--ref-text TEXT` / `--ref-text-file PATH` | 参考音频的**逐字转写**（不是要合成的新句子） |
| `--language LANG` | 输出/克隆语言，默认 `Chinese` |
| `--model NAME` | 默认 `Ming-3.0-tts-0.5b`；显存紧时换 `-int8-convrot` |
| `--cfg` / `--flow-steps` / `--max-steps` / `--temperature` / `--seed` | 采样参数，见 [tts.md](tts.md) |
| `--prefix` | 输出前缀，默认 `ming_tts/dub` |
| `--out` / `--timeout`（1800） / `--dry-run` / `--no-wait` / `--no-download` | 同 `run` |

## `register`

把已有工作流登记成别名，写入 `registry.json`。

| 参数 | 说明 |
|---|---|
| `ALIAS`（位置） | 别名（大小写不敏感） |
| `--source` | `user:<rel>` / `api:<rel>` / `file:<abs>`，**必填** |
| `--title` | 中文说明，用于 `list` / `describe` |
| `--param NAME=NODE.INPUT` | 显式绑定，可重复；也支持 `NAME=NODE@标题片段.INPUT` |
| `--default NAME=VALUE` | 默认值，可重复 |

登记时会尝试读取工作流并列出"可自动绑定的输入名"，便于下一步补 `--param`。

## `nodes`

查询服务端已安装的节点类（解决"这个节点的精确类名/取值到底是什么"）。

```powershell
python scripts\comfy.py nodes Ming
python scripts\comfy.py nodes --json | Select-String sampler_name
```

## `interrupt`

中断当前正在执行的任务（对应 `POST /interrupt`）。

---

## 退出码

| 退出码 | stage | 含义 |
|---|---|---|
| `0` | — | 成功 |
| `2` | `config` | 配置/参数文件问题；离线模式却要求提交；schema 读不到 |
| `3` | `connect` | 连不上服务、端口不对、`doctor` 有检查项失败 |
| `4` | `workflow` | 工作流不存在、JSON 损坏、含子图、节点类未安装 |
| `5` | `param` | 参数名不存在、同名输入歧义、绑定节点 id 不存在、离线模式下上传输入 |
| `6` | `exec` | 提交被拒、执行报错、任务从队列消失 |
| `7` | `timeout` | 等待超时（任务可能仍在跑） |
| `8` | `io` | 上传/下载/写盘失败 |

失败输出（stderr，`--json` 时单行）：

```json
{"ok": false, "stage": "param", "error": "参数 reference_text 在工作流里找不到对应输入",
 "hint": "可用输入：audio, cfg, ..., task.reference_text, text"}
```

**不自动重试提交**是有意的：出图/配音都可能有成本，宁可让人看到失败原因，也不要静默重复跑。任何阶段失败都会保留已拿到的 `prompt_id`。

## Python 内嵌调用

不想走 CLI 时，直接 import 库（同一个仓库，无需安装）：

```python
import sys
sys.path.insert(0, r"D:\tools\comfyui-named-runner\scripts")
import comfy_client as C

cfg = C.load_config()
ref, data = C.resolve_workflow("ming", cfg)
server = C.Server(cfg)
server.resolve()                      # 自动扫描端口
prompt, warnings = C.ui_to_api(data, server.object_info())
applied, _ = C.bind_params(prompt, ref, {"text": "你好"})
pid = server.submit(prompt)
history = server.wait(pid, timeout=600)
files, texts, warn = C.collect_outputs(history, server, "./out", "demo")
```

完整示例见 [examples/python_embed.py](../examples/python_embed.py)。
