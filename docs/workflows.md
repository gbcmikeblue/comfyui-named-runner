# 工作流：解析、转换、登记

## 1. 名称解析顺序

`run` / `describe` / `t2i` / `i2i` / `tts` / `dub` 的 `NAME` 按以下顺序解析，命中即停：

1. `registry.json` 里的**别名**（大小写不敏感）
2. 直接给**路径**（`.json` 文件，相对或绝对）
3. `workflows_dir` 下的**文件名 / 相对路径**：精确匹配 → 大小写不敏感 → 唯一子串匹配
4. 都找不到 → `workflow`（退出码 4），并提示用 `list --all` 查看可选清单

一旦某级别出现多个候选（例如两个文件名都包含关键词），**不做猜测**，直接报歧义。

## 2. 支持的格式

### UI 格式（界面默认保存）

特征是顶层有 `nodes` + `links`。转换器会：

| 情况 | 处理 |
|---|---|
| 控件值 | 按 `/object_info` 的 `required → optional` 顺序还原 `widgets_values`；`widgets_values` 为对象时按名取值 |
| `control_after_generate` 或 `seed`/`noise_seed` 后紧跟 `fixed/increment/decrement/randomize` | 多吞一个 token，避免后续控件整体错位 |
| `mode == 4`（旁通） | 删除节点，下游按**输出类型匹配**的第一个已连线输入透传 |
| `mode == 2`（静音） | 删除节点，其下游该输入缺失（交给服务端报必填） |
| `Reroute` | 穿透：上游直接连到下游 |
| 组件输入同时有连线 | 以连线为准（组件值仍被消费，保证后续 token 位置对齐） |
| `Note` / `MarkdownNote` / `PrimitiveNode` | 忽略 |
| `definitions.subgraphs` 非空 | **拒绝**：提示在界面里展开子图或导出 API |
| 节点类不在 `object_info` | **拒绝**：列出缺失类名（多半是自定义节点没装/没重启） |

转换后会给"缺必填组件值"的节点记 `warning`（不阻断），便于提前发现。

### API 格式（界面「工作流 → 导出 (API)」）

形如 `{"1": {"class_type": "KSampler", "inputs": {...}}}`，直接使用，无需 `object_info` —— 这意味着**API 格式的工作流可以在完全离线的情况下做参数校验**（搭配 `--dry-run --schema {}`）。

### 兼容性实测（服务端 0.43.0 / 2211 个节点类）

| 工作流类型 | UI→API | 说明 |
|---|---|---|
| 核心节点线性链路（如 TTS：加载 → 生成 → 保存） | 通过 | 控件、连线、参数全部命中 |
| 复杂自定义节点（如某些"一体化"视频节点） | 可转换但告警 | 节点把**显示标签**写进控件值（如"首帧优先"），且可能多一个 `null` 占位 → 整体错位。这类图**必须**导出 API 格式 |
| 含子图的工作流 | 拒绝 | 转换器不展开 `definitions.subgraphs`。Qwen Image 2.1 的官方模板（`qwen_image_2_1_t2i.json`、`image_qwen_image_2_1_image_edit.json`）就是这种 → 用内置的 `t2i` / `i2i` 别名（等价节点手写的 API 图） |

**经验法则**：节点少、用核心节点的图可以直接用 UI 格式；自定义节点多、或用了子图的，一律先在界面里导出 API 格式，再用 `register --source file:<导出文件>`。

判断是"模型文件缺失"还是"控件错位"：看 `describe` 的 `warnings` 里值是否像标签文字（错位）还是一个不存在的文件名（缺文件）。

## 3. 别名登记（`registry.json`）

```json
"my_t2i": {
  "title": "Qwen 文生图",
  "source": "user:qwen_image_t2i_api.json",
  "params": {
    "prompt": {"node": "27", "input": "text", "type": "string"},
    "steps":  {"node_title": "采样", "input": "steps", "type": "int"},
    "seed":   {"node_class": "KSampler", "input": "seed", "type": "int"}
  },
  "defaults": {"steps": 20, "width": 1024}
}
```

`source` 三种写法：

| 写法 | 基准目录 |
|---|---|
| `user:<rel>` | `<comfyui_root>/user/default/workflows` |
| `api:<rel>` | `<repo>/scripts/workflows`（随仓库分发的 API 图） |
| `file:<abs>` | 任意绝对路径 |

节点定位三选一：

- `node`：节点 id（字符串，`describe` 打印的 `[id]` 就是它）
- `node_title`：标题**包含**该片段的**唯一**节点
- `node_class`：该类在图中只有**唯一**实例时才可用

> 工作流另存/重排后节点 id 会变。以**当次** `describe` 的输出为准，不要照抄旧文档里的 id。

## 4. 参数约定

1. **显式绑定优先**：`registry` 里为该参数声明了 `spec` 就用它。
2. **同名自动绑定**：未声明 `spec` 时，按参数名去找图里的同名输入；**全图只有一个**节点有这个输入才写入。
3. **歧义直接报错**：多个节点同名输入 → `param` 错误并列出候选节点 id（这是有意为之，宁可报错也不猜）。
4. **未知名报错**：图里根本没有该输入 → `param`（退出码 5）并列出可用输入清单。
5. **带点号的键名**：支持 ComfyUI v3 节点的 `task.voice` / `task.reference_text` 这类命名，先按整键匹配，再回退到字典型输入的嵌套路径。
6. **值转换**：`true/false` → bool；整数 → int；小数 → float；以 `[` / `{` 开头 → 尝试 JSON；其余 → 字符串。`spec.type` 可强制。
7. **命令行覆盖默认值**：`defaults` 里没被命令行覆盖的值会写入图；`-p` 永远优先。

### 两组「看起来不像输入名」的 v3 动态输入

Qwen Image 2.1 的链路两种都踩到了，登记时按下面的写法绑：

| 类型 | object_info 里的样子 | API 图里的键 | 例子 |
|---|---|---|---|
| 动态下拉（`COMFY_DYNAMICCOMBO_V3`） | `format` 是下拉，其选项自带子输入 `bit_depth` / `input_color_space` | `format` 本体 + `format.bit_depth` 这样的**扁平点号键** | `SaveImageAdvanced` |
| 自动增长（`COMFY_AUTOGROW_V3`） | `images` 带 `template.names = [image_1 … image_16]` | `images.image_1`、`images.image_2`… 扁平点号键 | `TextEncodeQwenImage21` |

`registry.json` 里直接把 `input` 写成点号键即可（`comfy_client._set_input` 先整键匹配再回退嵌套）；漏写子输入时服务端会报 `Required input is missing: format.bit_depth`，而不是静默用默认值。

## 5. 登记模板

```powershell
# 1) 先看看目录里有什么
python scripts\comfy.py list --all

# 2) 只登记，参数靠自动绑定
python scripts\comfy.py register my_t2i --source user:qwen_image_t2i_api.json --title "Qwen 文生图"

# 3) 看节点 id 与输入名，再补显式绑定
python scripts\comfy.py describe my_t2i

# 4) 显式绑定 + 默认值
python scripts\comfy.py register my_t2i --source user:qwen_image_t2i_api.json `
  --param prompt=27.text --param width=30.width --param height=30.height `
  --default width=1024 --default height=1024
```

图生视频（需要先上传首帧）：

```powershell
python scripts\comfy.py register my_i2v --source file:D:\models\workflows\i2v_api.json `
  --param prompt=6.text --param image=4.image
python scripts\comfy.py run my_i2v --input-image .\first_frame.png -p prompt="镜头缓慢推进" --out .\out
```

> 上面的 `my_t2i` / `my_i2v` 只是演示登记格式。文生图、图生图、三条语音链路**已经内置**（`t2i` / `i2i` / `ming` / `ming_clone` / `tts` / `cosyvoice3`），直接用别名即可，不需要自己 `register`；需要改节点结构时复制 `scripts/workflows/*.json` 再登记新版。

## 6. 维护提示

- 工作流在界面里改名 / 另存 → `user:` 相对路径失效，`list` 会标 `[文件缺失]`。
- Desktop 更新 ComfyUI 会重写运行环境，更新后先跑 `doctor`（含 torch 预检）。
- 新增自定义节点后**必须重启 ComfyUI**，否则不出现在 `/object_info`，转换会以"节点类未安装"拒绝。
- 建议把工作流连同项目代码一起版本化，登记时用 `file:<项目内相对绝对路径>`，避免依赖 ComfyUI 的用户目录。
