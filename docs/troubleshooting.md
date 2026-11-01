# 排错

先跑这三条，80% 的问题能定位：

```powershell
python scripts\comfy.py doctor                 # 环境 / 服务 / 节点 / 模型
python scripts\comfy.py list --all             # 别名是否还指向存在的文件
python scripts\comfy.py describe <别名>         # 转换结果与告警
```

## 连接类

| 现象 | 原因 | 处理 |
|---|---|---|
| `[connect] 无法连接 ...`（退出码 3） | 服务没启动 | 在 ComfyUI Desktop 点 Launch，或 `python main.py`；再 `wait` |
| 上一个命令还好，突然连不上 | Desktop 因端口冲突换到了 8189+ | `doctor` 看实际端口；或把端口加进 `port_scan`；或 `--base-url` 直连 |
| `wait` 一直超时 | 服务在初始化（加载自定义节点很慢） | 加大 `--timeout`；看 ComfyUI 控制台是否卡在 import |
| 连上了但 `doctor` 的 `torch` 失败 | 用了没有 torch 的解释器启动（如 `standalone-env`） | 用 `<ComfyUI>/.venv/Scripts/python.exe`；同时确认没起两个实例 |

## 工作流类

| 现象 | 原因 | 处理 |
|---|---|---|
| `[workflow] 工作流不存在`（4） | 别名 source 失效 / 文件名变了 | `list --all` 找新名字，重新 `register` |
| `[workflow] 含子图` | UI 图里有 `definitions.subgraphs` | 界面里展开子图，或用「导出 (API)」重新导出后登记 |
| `[workflow] 节点类未安装` | 自定义节点没装 / 装了没重启 | 安装节点 → **重启 ComfyUI** → `nodes <关键词>` 确认类名 |
| `describe` 有 `warning`，值是"中文标签" | 该节点把**显示标签**写进了控件值 → 位置错位 | 改用 API 格式（界面导出 API） |
| `describe` 有 `warning`，值是某个文件名 | 模型文件缺失或名字不对 | 补文件；或用 `nodes` / `/object_info` 核对候选值 |
| 提交成功但没有任何产物 | 工作流没有 `Save*` 之类的输出节点 | 加输出节点；或在界面确认该节点没被静音 |

## 参数类

| 现象 | 原因 | 处理 |
|---|---|---|
| `[param] 参数 X 在工作流里找不到对应输入`（5） | 名字不对，或该输入是 `task.x` 这类带点键名 | 看错误里的"可用输入"清单；在 registry 里写 `"input": "task.x"` |
| `[param] 参数 X 在多个节点上存在` | 同名输入多处出现 | 在 registry 里显式绑定 `node` / `node_title` / `node_class` |
| `[param] 参数绑定的节点 id 不存在` | 工作流另存后 id 变了 | `describe` 拿新 id 再 `register` |
| 值类型不对（如 `"1024"` 当字符串） | 自动推断失败 | registry 里给 `"type": "int"`（或 `float` / `bool` / `string`） |
| `--seed` 没生效 | 该图没有 `seed` / `noise_seed` 输入 | 属正常提示（会写进 `warnings`） |
| 离线 schema 模式下 `--input-image` 报错 | 离线模式无法上传 | 连上服务后再传 |

## 执行类

| 现象 | 原因 | 处理 |
|---|---|---|
| `[exec] 提交被拒`，hint 里是 `value_not_in_list` | 下拉值不在候选（模型名/格式/采样器） | 用候选值；`nodes` 查精确类名与取值 |
| `[exec]` 里提到 `missing required input` | 必填输入被静音/旁通切断 | `describe` 看该节点输入 |
| 任务从队列消失、history 也没有 | 服务重启或任务被取消 | 重新提交；查服务端日志 |
| `[timeout]`（7） | 任务比 `--timeout` 慢（首次加载模型很常见） | 加大 `--timeout`；用打印出的 `prompt_id` 查 `/history` |
| 显存不足（OOM） | 模型太大 / 与其它任务共存 | 用 int8/更小模型；`POST /free` 卸载；串行执行 |

## 配音相关

| 现象 | 原因 | 处理 |
|---|---|---|
| `model 候选里没有 Ming-3.0-tts-0.5b` | 权重目录层级不对 | 必须是 `<checkpoints 根>/Ming-3.0-tts-0.5b/model.safetensors` |
| 克隆出来不像参考音色 | 参考音频有 BGM / 多人 / 转写不逐字 | 换干净单人 10–30 s；转写改成完全对应的文字（数字写成要读出的中文） |
| 音频被截断 | `max_steps` 太小 | `--max-steps` 调大（≈80 ms/块） |
| 音色每批不一样 | `--seed` 没固定 / 参考音频换了 | 固定参考音频 + 固定 `--seed` |
| `--voice` 没效果 | 当前走的是 `ming_clone`（克隆模式忽略内置音色） | 去掉 `--ref-audio`，或显式 `--workflow ming` |
| SAPI 报找不到语音 | 系统没装该中文语音 | 用 `--voice auto`；或安装系统语音后删 `voices_cache.json` 并重启 |

## 其它

- **不要用本工具启动/重启 ComfyUI**：它只做发现与调用。端口/进程问题请在 ComfyUI 一侧解决。
- **换了 Python 环境后**：所有命令重新 `doctor` 一次（torch、节点缓存都会变）。
- **产物下载 404**：服务端产物可能放在 `temp` 子目录或被清理，用 `--out` 及时另存。
- **报错看不懂**：所有命令加 `--json`，`hint` 字段通常直接给出下一步动作。
