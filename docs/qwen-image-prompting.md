# Qwen-Image-2.1 提示词写法汇总（官方口径 + 社区实践）

> 面向本项目的 `t2i` / `i2i` 两条链路整理。每条结论标注来源等级：
> **[官方]** 一手文档/官方仓库原文 · **[社区]** 公开仓库或社区手册，可信但与官方可能有偏差 · **[第三方]** 商业站/博客，仅供参考。

## 0. 三条必须先记住的结论

| # | 结论 | 来源 |
|---|---|---|
| 1 | 模型**默认没有 CFG 对抗**（guidance=1），官方发布路径是 40 步、CFG 1、Euler；ComfyUI 模板降到 25 步但同样 CFG 1 | [官方] README / [官方] ComfyUI 文档 |
| 2 | **CFG=1 时负向提示词完全不生效**（负条件分支被跳过）；官方 API 侧 `qwen-image-2.1` 系列干脆**不支持** `negative_prompt` 参数 | [官方] ComfyUI 文档 / [官方] 百炼文档 |
| 3 | 想稳定出好图，官方推荐**先用 PE 重写模型把短提示词扩写成 400–500 词的长描述**（PE-T2I / PE-I2I，各 9B） | [官方] README / PE 仓库 system_prompt |

---

## 1. 官方口径

### 1.1 先分清模式：T2I 与 图像编辑是两套写法

| 模式 | 触发条件 | 提示词职责 |
|---|---|---|
| 文生图（T2I） | 不传任何参考图 | 从零描述一整幅画面 |
| 图像编辑（I2I） | 传 1–10 张参考图 | 在给定素材上做**指定改动**，其余保持 |

官方编辑规范原文强调：*always an image-editing task, never text-to-image from nothing*——编辑模式下不要"重新画一遍"，要"下指令"。[官方 PE-I2I system prompt]

### 1.2 改写开关决定写多细（官方分类口径）

| 案例类型 | 智能改写 | 提示词策略 |
|---|---|---|
| 精选文生图 | 关 | 逐元素逐字锁定，把画面信息说尽 |
| 图像编辑 | 关 | 逐项列"保持不变"清单 + 移除/新增 + 光影统一 |
| 中文 / 英文文生图 | 开 | 只给主题、要素清单、故事脉络，细节交模型扩写 |

判断依据是"**需要逐字锁定**"还是"**允许扩写**"，不是简单的"文生图就开、编辑就关"。
配套参数：百炼侧 `prompt_extend`（默认 true，开启后**多花 3–5 秒**）；`prompt_extend_mode` 的 `direct` 支持 T2I+I2I，`agent` **仅 T2I**（I2I 传 agent 会 400）。[官方] 魔搭手册整理 + 百炼 text-to-image

### 1.3 官方 T2I 结构：8 步分层（PE-T2I system prompt 原文提炼）

重写器的输出是一段英文单段长描述（约 20 句 / 400–500 词），写法按顺序推进：

| 步 | 做什么 | 关键模板/要求 |
|---|---|---|
| 1 | 拆需求：固定项（要渲染的文字、点名的物体/数量/颜色/位置）、任务指令（"用双引号""4K 无噪点"→ **静默遵守，不写进描述**）、开放项（其余全部自己决定） | 短需求 ≠ 短描述；3 词需求也要写出同等体量 |
| 2 | 定画框 | 比例**只写在 `wh_ratio` 字段**，正文绝不出现比例/分辨率/像素数 |
| 3 | 开场句（约 20 词） | `The image is a ⟨vertical/wide/square/tall⟩ ⟨style⟩ ⟨medium⟩ of ⟨subject⟩, ⟨background and palette⟩.` **媒介名词永不可省**；风格词只在此处命名一次 |
| 4 | 先清点再动笔 | 8–14 个方位短语（典型 10 个），必须覆盖四角、四边与中心；另列"可读文字清单" |
| 5 | 走遍画面 | 有分区：背景→顶部带→主体（左→中→右）→底部带；单一主体：背景虚化→姿态→头脸→衣饰→手持物→边缘。约 1/3 句子以方位短语开头，保持单段 |
| 6 | 逐条安置文字 | `a bold black headline across the top reads "…"`；引号内保持原文字系统；换行写 "a second line"；不可读的招牌写 blurred / indistinct，**不要编造字母** |
| 7 | 光线单独成句 | 光源 + 方向 + 性质 + 阴影高光；`The lighting is …`，必须明写不能暗示 |
| 8 | 收尾一句 | `The overall composition is …`，只写一句，覆盖平衡、色调、风格、氛围 |

**全篇语体纪律**（违反即降质）：[官方]

- 现在时、第三人称、陈述句，像观察者在描述**已完成的画面**；禁用 `you` / `create` / `make sure` / `the AI should`。
- **禁止质量堆词**：`masterpiece`、`8K`、`highly detailed`、`award-winning` 都不写。
- 不确定处**主动模糊**：`appears to be`、`likely`、`suggesting`，歧义给并列（`a notebook or a tablet`）。
- 颜色几乎不用裸色名：`deep navy`、`muted olive`、`warm terracotta`、`blue-grey`；只有用户给 hex 才写 hex。
- 给材质而非只有名词：`brushed metal`、`matte plastic`、`coarse linen`、`weathered wood`、`visible brush strokes`。
- **枚举，绝不概括**：`several items`、`various decorations` 不算描述；小数量写英文单词（three / five）。
- 人物只写可观察表面；年龄只写人生阶段（`in her thirties`），**绝不写具体岁数**；脸背对就直说，不臆造五官。
- 物体按类别不按品牌（`a mirrorless camera`），除非用户点名品牌。
- 物理自洽：阴影背离光源、反射与所对物一致、相邻比例一致。

### 1.4 官方编辑结构：属性解耦（PE-I2I system prompt 原文提炼）

核心一句：**只精确修改用户点名的那一个属性，并推到强烈不可误认；其余全部保持在输入保真度。**

两种对称的失败：

| 失败 | 表现 |
|---|---|
| Leakage（渗漏） | 动了没点名的东西：锐化带偏色调、放大改了构图、换风格漂移人脸、换装丢配饰、换背景顺手清理了杂物 |
| Under-editing（编辑不足） | 改动太弱，输出和原图没差别 |

关键判断：**保持性约束锁的是"内容"，不是"编辑强度"**——要像原图，靠点名保持项，不靠削弱效果。

保真清单的写法纪律（最常被写错的地方）：[官方]

- 用**类型、位置、角色**指称要保留的东西，**不要描述它的外观**——"对模型而言保持性描述读起来就是生成指令，越具体越容易漂移"。
- 优先**一条总括性保持条款**，不要逐处走查画面。
- **身份是最硬的不变量**：人脸 + 可辨识配饰、产品设计/标识/数量、输入媒介（照片/插画/3D）。身份来自参考图时**指图**（`<image1>`），不要用文字描述特征（会让模型重画并降相似度）。
- 只做被要求的事：不清理未被提及的瑕疵；**移除/移动/露出新区域时必须交代**，让结果物理自洽。
- 图内文字是**字面**的：每个字符串加引号、不概括不缩写；落不定的文字干脆不加；外扩画布要明确写 **outpainting**。
- 以**操作开头**（"把 X 换成 Y…"），不是描述成品。

**多图引用（强制规则）**：[官方]

| 输入数 | 引用方式 |
|---|---|
| N ≥ 2 | **必须**用 `<image1>`、`<image2>`…；**禁止**"图1""第一张图""the first image" |
| N = 1 | **不要**用标签，自然指代"the image" |

- 必须声明每张图的**角色**：谁是画布（其构图存活）、谁提供可迁移素材，各自取什么。
- 无画布的场景生成（合影）：所有图都是身份来源，**逐张描述**，绝不压缩成一个区间。
- ComfyUI 里槽位是 `image_1`…`image_16`（本机编辑模板接前 10 个）；`image_1` 默认是"被编辑的图"。

### 1.5 官方固定句式（必须原样套用）

| 输出类型 | 官方约束 |
|---|---|
| 透明图（RGBA） | 首句 `This is an RGBA image with transparency.` + 主体描述 + 末句 `The image has alpha channel and the background is transparent.` |
| 360° 全景 | 必须写 `true equirectangular projection`、360° 水平 / 180° 垂直视野、左右边缘无缝、输出 2880×1440 且严格 2:1 |

中文社区版把这套句式译成「这是一张带有透明度的 RGBA 图像……／该图像具有 alpha 通道，背景是透明的。」——[社区] 魔搭手册标明这是"官方口径"的等价中文写法，但**官方仓库只给了英文原文**，中英混用时建议直接用英文原句更保险。

### 1.6 官方参数

| 参数 | 官方值 | 说明 |
|---|---|---|
| `num_inference_steps` | **40** | Diffusers/README 全部示例统一；Turbo 版 **8 步**（内置 ManualSigmas，单改步数无效） |
| guidance / CFG | **1** | SGLang 示例显式 `--guidance-scale 1`；ComfyUI 模板同为 1 |
| 分辨率 | 原生 **2048²** 起 | 官方宽高比表：1:1 2048×2048 / 4:3 2400×1792 / 3:4 1792×2400 / 3:2 2528×1696 / 2:3 1696×2528 / 16:9 2752×1536 / 9:16 1536×2752 |
| 百炼 2K 推荐 | 2048×2048 / 2688×1536 / 1536×2688 / 2368×1728 / 1728×2368 | 总像素 512²–2048²，宽高比 1:8–8:1，不指定时模型自动选 |
| 提示词长度 | 百炼：推荐 ≤4500 token（API 参考另处写 800 token 上限，2.0 系列 1300） | 两处数字不一致，**以具体模型 API 参考为准**，实践上控制在千字内 |
| `negative_prompt` | **qwen-image-2.1 系列不支持** | 不要的元素写进正向："不要出现 xxx" |
| `seed` | 0–2147483647 | 固定 seed 结果相对稳定 |
| `n` | 1–6（百炼） | 本地 ComfyUI 用 batch_size |
| PE 重写器 | PE-T2I / PE-I2I 各 9B；`max_new_tokens` 推荐 T2I 16256 / I2I 24000（开 thinking） | ComfyUI 内是 int8 版，`max_length` 默认 4096、上限 32768 |

**关于 `shift`**：README 只提到调度器是 "Flow Matching + Euler discrete + dynamic shifting"，**没有暴露可调参数与推荐值**；Lightning LoRA 场景下 ComfyUI 内置偏移是"在 1024×1024 上拟合"的，换尺寸匹配会变松。[官方 README / ComfyUI 文档]

### 1.7 官方对"图内文字"的边界

- 模型能生成中英文文字，但**长文本难以逐字精准**（完整古诗、长段落、多行）→ 易错字、漏字、形近字替代。
- 官方建议：缩短图内文字，只留关键标题/短语，关键文字后期修。
- 反例意识：PE 规范要求"落不定的文字就不要加"，但**文生图场景里**官方又给了 `A neon shop sign that reads "QWEN IMAGE 2.1"` 这种**用引号包裹精确文案**的写法——短文案用引号锁，长段落别硬塞。

---

## 2. 社区实践

### 2.1 中文手册的分层骨架（可当日常模板用）

[社区] 魔搭《Qwen-Image-2.1 提示词写法指导手册》把官方案例归纳成更好记的分层顺序，**与 1.3 的官方 8 步并不冲突**，是它的通俗化表达：

1. 一句话锚定画面身份（"这是一张……建筑讲解图板""一张真实日常的手机随手拍摄生活照"）
2. 主体外观与姿态 → 环境与前景背景 → 光照（方向/时段/冷暖/光比）→ 材质纹理 → 构图（视角/焦段/横竖/主体占比）→ 整体风格质感
3. 用**具体名词与数值**替代空泛形容词（"带猫眼光泽的棕黄色虎眼石圆珠""右后方 45 度暖色自然光，面部左侧伦勃朗式三角光"）
4. 主动写**排除项**（"不出现人物""不渲染标注线""无文字无 logo 无水印""不要拼贴"）

该手册明确标注了自己的边界：颜色 hex、`8k/超高清` 画质词、`1:1/3:4/16:9` 常规比例预设都属「**非官方·经验补充**」，且指出通用"负面提示词"框架**不是** 2.1 的官方做法（官方是把排除项写进正文）。

### 2.2 词汇表（社区补充，官方未给清单）

速查表来自 `iamyoki/qwen-image-2.1-skill`（对官方 system prompt 的工程化落地）：[社区]

| 维度 | 可用词 |
|---|---|
| 媒介（必填） | photograph, poster, illustration, scene, portrait, infographic, close-up, graphic, page, card, sheet, logo, editorial |
| 摄影风格 | photorealistic, editorial fashion, cinematic, documentary, macro close-up, tilt-shift, vintage film (Kodak Portra) |
| 插画/艺术 | flat-vector, watercolour, hand-drawn sketch, ink wash, woodcut, ukiyo-e, gouache, retro comic, storybook |
| 数字/3D | isometric 3D render, claymation, octane render, low-poly, cyberpunk neon |
| 金属 | brushed stainless steel, anodized aluminum, tarnished brass, polished copper, matte chrome |
| 玻璃/液体 | frosted glass, fluted glass, leaded crystal, condensation droplets, glossy glaze |
| 织物 | coarse linen, ribbed cotton knit, distressed denim, supple lambskin, sheer silk chiffon, houndstooth wool |
| 表面/建筑 | weathered teak, exposed aggregate concrete, polished travertine, cracked asphalt, terracotta tiles |
| 自然光 | soft diffused daylight through overcast sky / harsh midday sun with sharp short shadows / warm golden-hour glow from the left / cool blue twilight |
| 影棚光 | three-point studio lighting with a large softbox / directional rim lighting / warm overhead pendant / single dramatic spotlight |
| 氛围光 | volumetric god rays through mist / neon ambient spill from signage / flickering firelight from one side |
| 方位短语 | upper-left corner, across the top band, along the left edge, in the absolute centre, across the lower third, tucked behind, nestled between, receding into the background, jutting outward from the bottom edge |

### 2.3 ComfyUI 实操经验（与本项目直接相关）

[官方] ComfyUI 文档给的是"参数怎么调"，这部分社区与官方高度一致：

| 项 | 实践结论 |
|---|---|
| steps | 模板 25 步是官方给 ComfyUI 的默认；**简单局部编辑 4–8 步**就够（改个衣服颜色），整帧重绘要回满 25；手指等细节 30 步左右收敛，25→40 减少细节噪点闪烁 |
| cfg | 保持 1；**cfg 2** 更贴密集提示（小字、数字）但边缘过锐；更高会偏亮/偏暗，cfg 5 质量崩，0.5 直接破图 |
| 分辨率 | 文生图用 Resolution Selector 的"百万像素"目标，2K ≈ 4.0 MP；**远超 2K（如 4K）提示遵循度下降** |
| 编辑 resolution 语义 | 0 = 保持 image_1 原始像素；>0 = 把 image_1 缩到"resolution² 总像素预算"。**它只决定出图大小，不增加细节**；耗时由画布像素决定，慢就先降它 |
| 局部编辑 | Mask Editor 用 Paint Pen 涂抹 → 涂抹色会写回节点成为参考内容 → 提示词里点明颜色（"change the jacket in the red area"），并说明期望颜色 |
| 提示增强 | `refine_prompt` 开 → 用改写后的提示词采样；`thinking` 开启后质量更好，但 `max_length` 小于推理块长度会**返回空字符串**（症状：编辑几乎不变 / 文生图丢需求）；用 `Preview Any` 看实际送入模型的提示词 |
| 已知缺陷 | stock VAE 在写实细节上留**棋盘纹**（解码器问题，加步数无效），可换社区 `texture_fix_vae_*`；VAE 输出 4 通道带 alpha，喂给只吃 3 通道的节点会报错，需 `SplitImageWithAlpha` |

### 2.4 社区对"要不要开 PE 重写"的分歧

- [社区] awesome 列表：PE 可选，基础模型不开也能跑；PE 输出是"推理块 + JSON"，要切 think-tag；T2I 版会返回 `wh_ratio` 可直接映射尺寸。
- [第三方] KoalaAPI、梦兽编程等：官方 demo 默认接 PE-I2I，不接则"局部编辑的指令遵循会弱一截"；9B 与 7B 同机部署压力大。
- 本机现实：`qwen3.5_9b_qwen_image_2.1_pe_t2i.int8_convrot.safetensors`（约 9.47 GB）已在 `text_encoders` 里，**属于可选分支**，不开也能出图。

---

## 3. 参数搭配速查

| 任务 | steps | cfg | 分辨率 | PE | 提示词写法 |
|---|---|---|---|---|---|
| 快速验证构图 | 8–12 | 1 | 512–768 总像素 | 关 | 只写主体 + 风格 |
| 常规文生图（海报/插画） | 25（追求细节 40） | 1 | 1024²–2048² | 可选开 | 8 步分层长描述（1.3） |
| 图内小字 / 数据表 | 40 | 2 | 2048² | 开 | 文字逐条 + 字体层级 + 防乱码三件套 |
| 局部编辑（换色/换物） | 4–8 | 1 | resolution 0 或 1024 | 关 | 操作开头 + 保持条款 + 标记颜色 |
| 风格迁移 | 25 | 1 | 跟随 image_1 | 可选开 | 点名介质词 + "保留构图、比例与可辨识文字" |
| 多图合成（穿搭/合影） | 25–40 | 1 | 画布图比例 | 开 | `<imageN>` 逐张声明角色 + 逐图描述 |
| Turbo | 8 | 1 | 2048² | 可选 | 同上（别乱改步数，调度在权重里） |
| Lightning LoRA | 4 | 1 | 1024²（偏移在此拟合） | 关 | 同上 |

---

## 4. 常见误区（按踩坑频率排序）

| # | 误区 | 正确做法 | 来源 |
|---|---|---|---|
| 1 | 写一大堆 `8k, masterpiece, best quality, ultra detailed` | 官方明令禁止质量堆词；质感靠材质、光线角度、镜头语言 | [官方] PE system prompt |
| 2 | 指望负向提示词压住"多余手指" | cfg=1 时负条件被跳过，API 也不支持 `negative_prompt`；写进正向"不要出现 xxx"或调 cfg=2 | [官方] ComfyUI / 百炼 |
| 3 | 编辑时把"保持不变"的内容描述得很细 | 保持项只用类型/位置/角色指称，**越细越容易漂移**；只对要改的东西写具体 | [官方] PE-I2I |
| 4 | 编辑指令写"画一个……的人" | 编辑模式要以**操作**开头（"把 X 换成 Y"），不要重画 | [官方] PE-I2I |
| 5 | 多图用"第一张图/图1" | 必须 `<image1>`/`<image2>`，且声明每张的角色 | [官方] PE-I2I + ComfyUI |
| 6 | 在提示词里写"16:9、2K"来控制尺寸 | 比例/分辨率属于参数层（`wh_ratio` / width×height），正文写了反而干扰 | [官方] PE 规范 |
| 7 | 短需求就写一句短的 | 关闭改写时**短需求要你自己补全画面**（3 词需求也要 400–500 词）；开启改写时反过来只给骨架 | [官方] PE / [官方] 百炼 prompt_extend |
| 8 | 透明图用"生成 RGBA 透明背景图像"这类简写 | 必须套官方首末句原文 | [官方] README |
| 9 | 长段中文文案硬塞进画面 | 官方明说长文本易错字；拆短、留标题、后期修 | [官方] 百炼 |
| 10 | 用超 2K（4K）尺寸求更多细节 | 超出训练分辨率会掉提示遵循度；要细节就抬 steps、换 bf16、用 PE | [官方] ComfyUI |
| 11 | 用 SD 习惯把 cfg 拉到 7 | cfg 1 是发布路径；2 是"更贴密集提示"的上限，5 崩 | [官方] ComfyUI |
| 12 | 分镜图不写格数与排布约束 | 必须写死"恰好 6 格、单横排 1 行 6 列、每格竖长条、编号不重复不跳号" | [社区] 魔搭手册 |
| 13 | 编辑后画面发假 | 忘了"统一光影逻辑"：光源方向、接触阴影、景深要显式交代 | [社区] 魔搭手册 |
| 14 | 打开 PE 却把 `max_length` 留在小值 | 推理块不闭合 → 返回空串 → 编辑几乎不变 | [官方] ComfyUI |

---

## 5. 可直接抄的骨架与示例

### 5.1 五套骨架（社区整理，源自官方案例）

| 场景 | 骨架 |
|---|---|
| 文生图 · 关闭改写（全细节） | 品类/风格定调句 → 主体外观 → 环境前景 → 光照方向时段 → 材质纹理 → 构图占比 → 文字区（逐字+分区+字体）→ 收束（风格质感 + 排除项） |
| 文生图 · 开启改写（大纲） | 一句主题风格 → 要素清单（人物/场景/道具/配色）→ 结构要求（格数/时间轴/版式）→ 一致性约束 |
| 图像编辑 | 引用图角色 → "保持【清单】完全不变" → "移除【…】" → "新增/替换为【…】并逐元素描述" → "统一光影（光源/接触阴影/景深）" → "其余与输入一致" |
| 信息图/科普卡 | 版式定调 → 分区编号逐区填（标题/图表/表格数值/图例/图注逐字）→ 字体层级 → 防乱码三件套 |
| 分镜/故事板 | 画风定调 → 分格硬约束（格数/排布/比例/编号防错）→ 角色一致性锚定 → 逐格脚本或时间轴 → 镜头节奏 → 收束 |

### 5.2 官方原文示例（可直接验证）

```text
# RGBA 透明图（README 原文）
This is an RGBA image with transparency. A cute cartoon dragon sticker.
The image has alpha channel and the background is transparent.

# 短文案 + 场景（model card 原文，注意引号锁文案）
A neon shop sign that reads "QWEN IMAGE 2.1", rainy night, reflections on wet pavement

# 多图编辑（ComfyUI 官方模板提示词，槽位指代）
Keep the character and pose in <image1> unchanged, put this light blue denim shirt
from <image2> on the character, preserve the original facial features, hair, body shape and pose

# 去背景（官方模板）
Remove the background, and output a PNG image
```

### 5.3 组合示例（官方规范 + 本项目用法）

```text
# 文生图：中长描述 + 分层（适合关闭改写、直接采样）
一幅竖版的写实摄影作品，画面主体是一位站在老街石阶上的中年男子。
他身穿深藏青色粗纺亚麻长衫，袖口有磨损的浅色毛边，右手握一把合拢的黑伞。
画面左侧沿墙堆着三只藤编竹篮，篮中露出赭红色的干辣椒。
背景是雨后的青石板巷，墙面斑驳的灰白灰泥上有细密裂纹。
The lighting is 从画面右后上方斜射的柔和阴天漫射光，在人物左侧面部形成低对比的柔和阴影，地面湿光反射天光。
整体构图以人物为中线偏右，留出左侧三分之一负空间，色调冷灰偏青，风格统一为纪实人文摄影。
画面中不要出现文字、水印与任何现代招牌。
```

```powershell
# 本项目调用（注意：--negative-prompt 在 cfg=1 下无效，排除项请写进正向）
python scripts\comfy.py t2i "（上面的长描述，排除项已并入正文）" --width 1536 --height 2304 --steps 25 --cfg 1 --out .\图
```

```text
# 图像编辑：操作开头 + 保持条款抽象 + 只描述改动
将 <image1> 中人物外套的颜色改为深橄榄绿，保留原有的立领版型、纽扣数量与缝线细节。
保持 <image2> 的街景作为背景，人物姿态、面部特征与发型完全不变。
The lighting is 与输入一致：右上方主光，左侧柔和补光，接触阴影方向不变。
画面其余部分与输入图保持一致，不要重新构图，不要添加新的文字或装饰。
```

### 5.4 分镜/多宫格（社区高频场景）

```text
恰好 6 格、等宽、单横排 1 行 6 列、每格为竖长条，不是网格也不是两行，绝不把任何一格再拆成上下两块。
每格左上角一个数字徽标，编号 1–6，不重复、不跳号、不缺号。
角色以 <image1> 的三视图为准：发型、服饰、身材比例全程一致，只改变姿势、表情与所处场景。
第 1 格 清晨窗边捧杯；第 2 格 街头回眸；第 3 格 地铁站台低头看手机；
第 4 格 雨中撑伞奔跑；第 5 格 咖啡馆窗前落座；第 6 格 夜色天台远眺。
每一格都必须画出角色本人并占据画面主体，严禁出现只有背景的空格。
```

---

## 6. 与本项目（comfyui-named-runner）的对接

| 主题 | 结论 |
|---|---|
| `t2i` 的提示词长度 | CLI 直接把字符串塞进 `TextEncodeQwenImage21.prompt`，**不做任何改写**；所以"开/关改写"的分水岭在本项目里等价于"你自己写长/写短"。想要 PE 效果，得在请求前自己调 PE 模型，或把 `--clip` 换成 `..._pe_t2i` 并在工作流里加 PE 分支（内置图没有这个分支） |
| `--negative-prompt` | 工作流里有这个输入，但 **cfg=1 时 ComfyUI 跳过负条件分支，等于无效**。排除项写进正向；真要负向就把 `--cfg 2` 并接受边缘变锐 |
| `i2i` 提示词 | 写指令不写画面（1.4）；参考图即 `<image1>`，多图需自建工作流绑 `images.image_2..16` |
| 尺寸 | 用 `--width/--height`（t2i，8 的倍数）与 `--resolution`（i2i，总像素预算）；**别在提示词里写 16:9 / 2K** |
| steps | 默认 25 已与 ComfyUI 官方模板一致；细节/小字场景抬到 40；局部小改用 4–8 快试 |
| seed | 固定 `--seed` 便于 A/B 单一变量对比（官方也建议"一次只改一个值"） |

---

## 7. 来源清单与可信度

| # | 来源 | 类型 | 覆盖内容 | 可信度 |
|---|---|---|---|---|
| 1 | [QwenLM/Qwen-Image-2.1 README](https://github.com/QwenLM/Qwen-Image-2.1) | 官方仓库 | 架构、40 步/2048²、宽高比表、PE 用法、RGBA 句式、生态 | ★★★★★ 一手，但提示词细则较少 |
| 2 | [HF Qwen/Qwen-Image-2.1 model card](https://huggingface.co/Qwen/Qwen-Image-2.1) | 官方 | RGBA 句式、引号锁文案示例、示例代码 | ★★★★★ 内容比 GitHub README 更薄，无 CFG/shift/多图语法 |
| 3 | [HF Qwen/Qwen-Image-2.1-PE-T2I `system_prompt.txt`](https://huggingface.co/Qwen/Qwen-Image-2.1-PE-T2I) | 官方原文 | **T2I 8 步结构、语体纪律、长度、宽高比规则、输出 JSON** | ★★★★★ 本汇总"官方结构"的主要依据 |
| 4 | [HF Qwen/Qwen-Image-2.1-PE-I2I `system_prompt.txt`](https://huggingface.co/Qwen/Qwen-Image-2.1-PE-I2I) | 官方原文 | **编辑规范 v2：语言双轨、属性解耦、`<imageN>` 强制、wh_ratio/ratio_follow 互斥、尺寸判定表** | ★★★★★ |
| 5 | [ComfyUI 官方文档 · Qwen-Image-2.1](https://docs.comfy.org/tutorials/image/qwen/qwen-image-2-1)（2026-10-27 更新） | 官方 | 25 步/cfg1/euler/simple、cfg 行为曲线、steps 分场景、编辑 resolution 语义、Mask 标记法、thinking 陷阱、VAE 棋盘纹 | ★★★★★ 与本项目链路最贴近 |
| 6 | [阿里云百炼 · 文生图 Prompt 指南](https://help.aliyun.com/zh/model-studio/text-to-image-prompt) | 官方（面向万相，Qwen-Image 通用） | 基础公式（主体+场景+风格）、进阶公式（+镜头/氛围/细节）、五维词典 | ★★★★☆ 公式与词典通用，但主体是万相 |
| 7 | [阿里云百炼 · 文生图使用方式](https://help.aliyun.com/zh/model-studio/text-to-image) | 官方 | `prompt_extend`/`prompt_extend_mode`、**2.1 不支持 negative_prompt**、2K 推荐分辨率、图内文字限制 | ★★★★★ |
| 8 | [千问-图像生成与编辑 API 参考](https://help.aliyun.com/zh/model-studio/qwen-image-generation-and-editing-api-reference) | 官方 | prompt token 上限、size 范围 512²–2048²、1:8–8:1、n/seed/watermark | ★★★★★ 注意 token 上限各处口径不一致 |
| 9 | [魔搭《Qwen-Image-2.1 提示词写法指导手册》](https://modelscope.cn/posts/436932)（alding86，2026-09-24 / 11-01 更新） | 社区，基于官方案例库 | 三条底层认知、分层骨架、文字密集图、编辑/多图/分镜写法、避坑清单、**明确标注非官方项** | ★★★★☆ 中文最系统；少数条目自认"经验补充" |
| 10 | [iamyoki/qwen-image-2.1-skill](https://github.com/iamyoki/qwen-image-2.1-skill) | 社区（Agent skill） | t2i_rules / edit_rules / cheat_sheet：官方 system prompt 的工程化落地与词汇表 | ★★★★☆ 与官方原文高度一致，但属二次整理 |
| 11 | [wildminder/awesome-qwen-image](https://github.com/wildminder/awesome-qwen-image)（约 137 stars） | 社区索引 | PE 双模型与量化生态、DHQ 量化、"默认 40 步无 CFG" | ★★★☆☆ 索引准确，经验条目未逐条验证 |
| 12 | [qwenimages.com 发布解读](https://qwenimages.com/zh/blog/qwen-image-2-1-release)、[pixeldojo 指南](https://pixeldojo.ai/guides/qwen-image-2-1-prompting-guide)、[themindstudio 指南](https://themindstudio.cc/mindcraft/docs/tutorial/prompt-guide-qwen-image-2-1) | 第三方商业站 | 案例与设置建议（Turbo 8 步 / full 40 步、16 倍数对齐等） | ★★☆☆☆ 有营销成分，参数与官方不一致处以官方为准 |
| 13 | qwen.ai 官方博客 `?id=qwen-image-2.1` | 官方 | —— | 未能抓取：页面为 CSR 单页应用，服务端 HTML 无正文 |

**已知未取到的内容**：官方博客正文（SPA）；README/model card 中的 `true_cfg_scale` 与 `shift` 推荐值（两者在公开文档里都不存在）；官方中文提示词示例（官方示例全为英文，中文写法多为社区归纳）。
