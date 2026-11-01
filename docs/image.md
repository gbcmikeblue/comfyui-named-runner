# 图像：文生图与图生图

两条链路都基于 **Qwen Image 2.1**（ComfyUI 0.4x 起自带 `TextEncodeQwenImage21`，无需自定义节点）。

| 别名 | 能力 | 输出尺寸 | 实测耗时（1024²/25 步） | 显存 | 适用 |
|---|---|---|---|---|---|
| `t2i` | 文本 → 图像 | `--width` × `--height`（默认 1024²） | 19.7 s（模型已常驻） | ~10–12 GiB（int8_convrot + bf16 VAE） | 概念图、分镜底图、插画 |
| `i2i` | 参考图 → 风格迁移 / 内容变换 | 跟随参考图比例（`--resolution` 控制预算） | 28.8 s（含参考图编码） | 同上 | 换风格、换材质、局部改内容、涂色 |

> 数据取自 RTX 5060 Ti 16 GB / ComfyUI 0.43.0 / `qwen_image_2.1_int8_convrot`；256²/4 步的小图约 3–5 s，适合调提示词。首次调用还要加上模型加载时间。

---

## 1. 模型与节点

### 1.1 三件套

| 角色 | 节点 | 默认文件 | 说明 |
|---|---|---|---|
| 扩散模型 | `UNETLoader` | `qwen_image_2.1_int8_convrot.safetensors` | int8 convrot 量化版，16 GB 卡首选；质量优先可换 `qwen\qwen_image_2.1_bf16.safetensors` |
| 文本/视觉编码器 | `CLIPLoader`（`type=qwen_image`） | `qwen3vl_8b_int8_convrot.safetensors` | 同时承担提示词编码与参考图视觉编码 |
| VAE | `VAELoader` | `qwen_image_2.1_vae_bf16.safetensors` | 2.1 专用 VAE，别混用旧版 `qwen_image_vae.safetensors` |

`doctor` 会检查这三项：

```powershell
python scripts\comfy.py doctor | Select-String qwen
#   OK   node:TextEncodeQwenImage21 已加载
#   OK   qwen_model:unet_name   可用：qwen\qwen_image_2.1_bf16.safetensors, qwen_image_2.1_int8_convrot.safetensors
#   OK   qwen_model:clip_name   可用：qwen3.5_9b_qwen_image_2.1_pe_i2i.int8_convrot.safetensors, ...
#   OK   qwen_model:vae_name    可用：qwen_image_2.1_vae_bf16.safetensors
```

### 1.2 编码器变体

`clip_name` 候选里若出现 `qwen3.5_9b_qwen_image_2.1_pe_t2i` / `_pe_i2i`，那是 2.1 的**分用途**编码器（t2i 与 i2i 各一个）。默认用的 `qwen3vl_8b_int8_convrot` 兼容两用，两版都验证可出图；追求极致质量时按用途切换：

```powershell
python scripts\comfy.py i2i "改成水彩" --image .\in.png `
  --clip "qwen3.5_9b_qwen_image_2.1_pe_i2i.int8_convrot.safetensors" --out .\图
```

### 1.3 权重在哪

Desktop 版的模型目录由 `extra_model_paths` 注入，**不是** `<ComfyUI>\models`：

```
<models>\diffusion_models\qwen_image_2.1_int8_convrot.safetensors
<models>\text_encoders\qwen3vl_8b_int8_convrot.safetensors
<models>\vae\qwen_image_2.1_vae_bf16.safetensors
```

原始权重见 Comfy-Org 的 `Comfy-Org/Qwen-Image-2.1`（HuggingFace / ModelScope 同名仓库）。放好后**不用重启**（`/object_info` 的候选列表按请求重新扫描），跑一次 `doctor` 确认即可。

---

## 2. 文生图 `t2i`

```powershell
python scripts\comfy.py t2i "雨后的江南小巷，青石板路泛着微光，白墙黛瓦，水彩风格" `
  --width 1536 --height 864 --steps 25 --seed 42 --out .\图 --json
```

要点：

- **尺寸**：必须是 8 的倍数（latent 对齐）；Qwen 2.1 原生支持到 2048。`1536×864`（16:9）与 `864×1536`（9:16）是最常用的两档。
- **横竖构图**：由 `--width/--height` 决定，不靠提示词里的「横版/竖版」。
- **批量**：`--batch 4` 一次出 4 张，产物是一批独立 PNG。
- **复现**：固定 `--seed` 且同一提示词/尺寸 → 完全相同的图；只改 `--prompt` 保留 seed 不同尺寸也会变（latent 变了）。

### 2.1 提示词写法

Qwen Image 2.1 对**中文长句**的支持很好，官方模板本身就是「一句场景描述 + 风格短语」：

```
<主体与动作>, <环境与光线>, <材质与镜头>, <风格短语>
例：成年东方青年男性站在白色影棚中央，柔光箱正面主光，皮肤可见毛孔与自然纹理，85mm 镜头，电影级摄影质感
```

**负向提示词在默认 `--cfg 1` 下不生效**：ComfyUI 在 cfg=1 时直接跳过负条件分支，官方 API 侧 `qwen-image-2.1` 系列也不支持 `negative_prompt` 参数。排除项（"不要出现文字、水印"）写进正向提示词；确实需要负向就把 `--cfg` 提到 2，代价是边缘变锐。完整写法见 **[qwen-image-prompting.md](qwen-image-prompting.md)**。

---

## 3. 图生图 `i2i`

```powershell
python scripts\comfy.py i2i "把这张照片改成油画风格，笔触粗犷，保留人物五官与构图" `
  --image .\photo.png --out .\图
```

### 3.1 它和 SD 的 img2img 不一样

| 维度 | SD img2img | Qwen Image 2.1 `i2i` |
|---|---|---|
| 参考图进入方式 | 图像加噪后作为采样起点 | 编码成条件（`reference_latents`）+ 视觉塔 token |
| `denoise` 作用 | 越低越像原图 | 保持 1.0；调低**不会**让结果更像原图，只会让采样不充分 |
| 输出尺寸 | 自由设定 | 跟随参考图比例（编码节点输出的 latent），改尺寸会让编辑偏移 |
| 提示词怎么写 | 描述最终画面 | 写「改成什么」：`把 X 改成 Y`、`保留 A，替换 B` |

### 3.2 常用改法

| 目标 | 提示词骨架 |
|---|---|
| 换画风 | `改成<油画/水彩/铅笔素描/赛博朋克>风格，保留人物五官与构图` |
| 换材质/季节 | `把<木质>换成<金属>，光线保持柔和` |
| 局部改内容 | `把背景的<街道>换成<海边>，主体不动` |
| 多视角 / 设定板 | `根据这张图生成正面/侧面/背面三视图，白底，同一人物` |

### 3.3 参数

- `--resolution`：参考图编码前的缩放预算（默认 1024，即约 100 万像素）。要出 2K 编辑图时给 2048，显存与耗时同步上升。
- 参考图建议长边 ≤2048、主体清晰；图太小（<512）会让视觉塔的 token 过少，编辑变得含糊。
- 多图参考：图里 `images.image_1..image_16` 都可接，CLI 只绑定第一张。需要多图时用
  `python scripts\comfy.py run i2i -p image=a.png -p images.image_2=b.png ...`（把节点 5 的第二路接上需自建工作流）。

---

## 4. 工作流文件（API 格式）

| 文件 | 别名 | 节点 |
|---|---|---|
| `scripts/workflows/qwen_image_2_1_t2i.json` | `t2i` | 8 个：3 加载 + 编码 + 空 latent + 采样 + 解码 + 保存 |
| `scripts/workflows/qwen_image_2_1_i2i.json` | `i2i` | 8 个：3 加载 + `LoadImage` + 编码（含 `images.image_1`）+ 采样（latent 取编码节点）+ 解码 + 保存 |

为什么不用 ComfyUI 自带的 `qwen_image_2_1_t2i.json`：那些模板用了**子图**（`definitions.subgraphs`），本工具的 UI→API 转换器会明确拒绝。内置这两份是等价节点手写的 API 图，可以离线校验、可以直接 diff。

改结构的方式：复制一份改节点，然后

```powershell
python scripts\comfy.py register my_t2i_big --source file:.\my_t2i_big.json `
  --title "我的文生图" --param prompt=4.prompt --param width=5.width --default width=2048
```

---

## 5. 排错

| 现象 | 原因 / 处理 |
|---|---|
| `Required input is missing: format.bit_depth` | `SaveImageAdvanced` 的动态下拉子输入没给。API 图里必须写 `format` + `format.bit_depth` + `format.input_color_space`（点号键） |
| 提交成功但图里没有参考图效果 | `images.image_1` 键名不对会被**静默忽略**（该输入 min=0）。核对键名，或看产物宽高比是否等于参考图 |
| `'str' object has no attribute 'movedim'`（node TextEncodeQwenImage21） | `images.image_1` 给成了字符串而不是 `["4", 0]` 这类连线引用 |
| 出图全黑 / 噪声 | `vae_name` 用错（混了旧版 `qwen_image_vae.safetensors`），或 `cfg` 被照搬成 SD 的 7 |
| 人物/构图与参考图偏差大 | 参考图分辨率过低，或 `--resolution` 设得太小；也可能是提示词写成了「画什么」而不是「改成什么」 |
| 显存不足 | 换 `int8_convrot` unet、降 `--resolution`/`--width`、单张跑（`--batch 1`） |
| `workflow` 错误：含子图 | 用内置 `t2i` / `i2i`，或在 GUI 里展开子图后 Export (API) |
