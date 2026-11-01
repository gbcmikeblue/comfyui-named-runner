# 语音：配音 / 克隆 / 兜底

三条链路，按"质量 ↔ 成本"排列。日常中文配音选 `ming`；要占位音/调试选 `tts`；要方言、多角色、SRT 时间轴选 `cosyvoice3`。

| 别名 | 引擎 | 输出 | 首次耗时 | 显存 | 适用 |
|---|---|---|---|---|---|
| `ming` | Ming-3.0-tts **0.5B**，内置音色 | 44.1 kHz 单声道 | ~22 s（含加载），常驻后 ~7.6 s/句 | ~2.5–2.8 GiB | 正式中文配音 |
| `ming_clone` | 同上，零样本克隆 | 同上 | 同上 | 同上 | 复刻某个真人的音色 |
| `tts` | Windows **SAPI5**（离线） | 16 kHz 单声道 | 秒级 | 0 | 占位、调试、兜底 |
| `cosyvoice3` | CosyVoice3（TTS Audio Suite） | 24 kHz | ~13 s/句（含加载） | 中等 | 多语种 / 方言 / 多角色对话 |

---

## 1. Ming-3.0-tts（主链路）

### 1.1 上游与取舍

| 项 | 内容 |
|---|---|
| 模型 | [`inclusionAI/Ming-3.0-tts`](https://github.com/inclusionAI/Ming-3.0-tts)（MIT）：0.5B 稠密 + 7.9B-A1.3B MoE，多语种、零样本克隆、音色设计、自然语言控制 |
| ComfyUI 移植 | [`Saganaki22/ComfyUI-Ming-3-tts`](https://github.com/Saganaki22/ComfyUI-Ming-3-tts)（MIT）：`MingLoadModel` / `MingGenerate` / `MingSave` / `MingPodcast` / `MingWhisperTranscribe` |
| 为什么选 0.5B | 显存 2.5–2.8 GiB（16 GB 卡占 ~17%，可与其它节点共存）；权重 2.76 GiB；输出 44.1 kHz 单声道，够做朗读/讲解/对话 |
| 为什么不用 Tiny 9B | bf16 需 ~16.7 GiB，16 GB 卡会爆；多说话人播客才需要 |

### 1.2 安装节点与权重

1. 把 `ComfyUI-Ming-3-tts` 装进 `<ComfyUI>/custom_nodes/`，**重启 ComfyUI**。
2. 权重放到任意已注册的 `checkpoints` 根目录下，目录名即模型名：

```
<models>/checkpoints/Ming-3.0-tts-0.5b/model.safetensors     # 2.76 GiB
```

`MingLoadModel` 会扫描所有已注册 `checkpoints` 路径（含 Desktop 的 `extra_model_paths` 注入目录）以及 `models/ming3_tts`。放好后 `/object_info/MingLoadModel` 的 `model` 候选里会多出该目录名，`doctor` 的 `model:*` 检查即以此为准。

3. 拉权重：官方权重在 HuggingFace（`drbaph/Ming-3.0-tts-ComfyUI`）。HF 直连不稳定时用 **ModelScope 镜像**（同名仓库，多线程通常能跑满带宽）：

```powershell
# 用 ComfyUI 自己的 Python 环境（里面通常已经装了 modelscope 依赖栈）
$py = "<ComfyUI>\.venv\Scripts\python.exe"
& $py -c "from modelscope import snapshot_download; snapshot_download('drbaph/Ming-3.0-tts-ComfyUI', allow_patterns=['checkpoints/Ming-3.0-tts-0.5b/*'], local_dir=r'<models>\checkpoints\Ming-3.0-tts-0.5b')"
```

> `snapshot_download` 会保留 `checkpoints/Ming-3.0-tts-0.5b/` 层级，最终必须正好是 `<models>\checkpoints\Ming-3.0-tts-0.5b\model.safetensors`，多余的层级删掉。
> `MingLoadModel` 的 `download_if_missing` 走 HF，网络不通就别开，手动放好文件即可。

### 1.3 用法

```powershell
# 内置音色（开箱即用，不需要录音）
python scripts\comfy.py dub "弯弯的月儿小小的船。小小的船儿两头尖。" --voice 灵小安 --out .\配音

# 音色克隆：10–30 s 干净单人说录音 + 它的逐字转写（不是要合成的新句子）
python scripts\comfy.py dub "小兔子乖乖，把门儿开开。" `
  --ref-audio .\voice\teacher.wav `
  --ref-text "这是一段十五秒左右的普通话朗读示范。" `
  --language Chinese --out .\配音

# 批量：--text-file 每行一句，--prefix 区分课时
python scripts\comfy.py dub --text-file .\lesson02.txt `
  --ref-audio .\voice\teacher.wav --ref-text-file .\voice\teacher.txt `
  --prefix ming_tts/lesson02 --out .\配音 --json
```

**内置音色**有 100+ 个，名字要原样传入（不要翻译）。面向中文教学场景可直接用：

| 音色 | 特点 |
|---|---|
| `花小呗` | 童声，适合对话/低龄内容 |
| `灵朵儿` | 温润知性，适合旁白 |
| `灵小柔` | 清晰标准，适合讲解 |
| `灵小雅` | 新闻/有声书 |
| `灵小安` | 中性通用，默认值 |

完整清单见节点仓库的 `docs/instructions.md`。

### 1.4 音色一致性

- **同一参考音频 + 固定 `--seed`** = 整套课件音色稳定。换 `--seed` 只改变随机性，不改变音色。
- **文本按句切**（单段建议 ≤50 字），长句让模型自己分块容易在停顿处变调。
- 参考音频要求：单人、无 BGM、10–30 s、转写**逐字一致**（数字/缩写先改写成要读出的中文）。
- 参考音频混入第二人声 → 音色漂移；撞 `max_steps` → 音频被截断（调大）。

### 1.5 其它 task（不止 clone / 内置音色）

`MingGenerate` 的 `task` 是**选项 key**，子输入用 `task.<name>` 平铺（这是 ComfyUI v3 `DynamicCombo` 的约定，写成嵌套 dict 会报 `missing 1 required positional argument: 'task'`）：

| task | 子输入 | 用途 |
|---|---|---|
| `ip` | `task.voice` | 内置音色（`ming` 用的就是它） |
| `clone` | `task.reference_audio` + `task.reference_text` + `task.language` | 零样本克隆 |
| `voice_design` | `task.style` | 用文字描述"造"一个音色 |
| `freeform` | `task.instruction` | 自然语言指令控制语气 |
| `basic` | `task.speed` / `pitch` / `volume` | 基础语速/音高/音量 |
| `emotion` | `task.emotion` | 情绪控制（happy/sad/…） |
| `dialect` | `task.dialect` | 方言（川渝/广粤等） |

要换 task：复制 `scripts/workflows/ming_dub_ip.json` 改 `task` 与子键，再登记成新别名：

```powershell
python scripts\comfy.py register ming_freeform --source file:.\my_freeform.json `
  --param text=2.text --param instruction=2.task.instruction
python scripts\comfy.py run ming_freeform -p text="小声点说，别吵醒它" --out .\配音
```

文本里还可以直接写**副语言标签**：`[Laughter]`、`[Sigh]`、`[Breathing]`、`[Question-ah]`。

> `--max-steps` 是每段音频块的生成上限（≈80 ms/块，250 ≈ 20 s），**不是语速**。语速用 `basic` task 的 `task.speed`。

---

## 2. Windows SAPI（离线兜底）

| 项 | 内容 |
|---|---|
| 别名 | `tts`（source `user:tts_zh_sapi.json`，示例文件见 `examples/comfyui-workflows/`） |
| 图结构 | `LocalTTS_SAPI`(1) → `SaveAudioAdvanced`(2, flac) |
| 节点 | 自建 `ComfyUI-LocalTTS-SAPI`：离线调用 SAPI5，无模型、无网络、CPU 即可 |
| 参数 | `text`（必填）、`voice`（`auto` 优先 zh-CN）、`rate`(-10..10)、`volume`(0..100)、`filename_prefix` |

```powershell
python scripts\comfy.py tts "第一句。第二句。" --voice "Microsoft Huihui Desktop" --rate 2 --out .\out
```

定位：机器味明显，但**零成本、秒级、无显存占用**。适合占位音、流水线调试、以及配音模型不可用时的兜底。

- 换系统语音后要删 `<ComfyUI>/custom_nodes/ComfyUI-LocalTTS-SAPI/voices_cache.json` 或重启 ComfyUI，语音清单才会刷新。
- 想换成模型化 TTS：搭好"文本 → 某 TTS 节点 → SaveAudio"的图，`register` 成新别名，再用 `tts --workflow <别名>` 或直接 `run`。

---

## 3. CosyVoice3（多引擎备选）

| 项 | 内容 |
|---|---|
| 插件 | [`diodiogod/TTS-Audio-Suite`](https://github.com/diodiogod/TTS-Audio-Suite)（MIT，19 个引擎：IndexTTS-2 / CosyVoice3 / Qwen3-TTS / F5-TTS / ChatterBox / VibeVoice …） |
| 权重 | `Fun-CosyVoice3-0.5B-RL`（Apache-2.0，约 5.2 GiB），放 `<ComfyUI>/models/TTS/CosyVoice/` |
| 节点类名 | `CosyVoiceEngineNode`（显示名是 "⚙️ CosyVoice3 Engine"）、`CharacterVoicesNode`、`UnifiedTTSTextNode` |

```powershell
python scripts\comfy.py run cosyvoice3 --input-audio .\voice\teacher.wav -p text="春天来了。" --out .\out
```

坑：`instruct_text` 一旦给了就走 instruct 模式并**忽略** `reference_text`，两者只能留一个。该套件的 `install.py` 会压 `numpy<2.3` 并对若干库用 `--no-deps` 安装 —— 升级前先 `pip freeze > before.txt` 便于回滚。

---

## 4. 产物与后处理

- 产物默认落 `./comfy-out`，文件名前缀 `<别名>-<时间戳>-<prompt_id前8位>`，扩展名沿用服务端输出（Ming/CosyVoice 默认 flac）。
- 需要 wav/mp3 时改工作流里 `SaveAudioAdvanced` 的 `format`：`run <别名> -p format=wav`。
- 批量合成后建议用 `ffprobe` 抽查采样率/声道数，确认没有被上游节点重采样。
