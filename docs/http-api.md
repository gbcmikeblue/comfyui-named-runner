# ComfyUI HTTP 接口速查

本项目实际用到的接口集合。基准：ComfyUI 0.43.0（兼容 0.38+），全部在 `http://127.0.0.1:<port>` 上，本地无鉴权。

> 为什么不用新版 `/api/jobs`：本工具面向"能跑就行"的兼容性，坚持经典 `POST /prompt` + `GET /history/<id>` 这条最稳定的路径。

## 1. 健康检查

`GET /system_stats`

```json
{
  "system": {"os": "nt", "comfyui_version": "0.43.0",
             "python_version": "3.13.12 ...", "pytorch_version": "2.12.1+cu130", "ram_total": 0},
  "devices": [{"name": "cuda:0 NVIDIA GeForce ...", "type": "cuda",
               "vram_total": 17037467648, "vram_free": 16283}]
}
```

用于判断"服务是否就绪"，`doctor` 也在这里读版本与显存。**注意**：字段缺失不代表报错，不能只靠它判断 GPU 是否真的可用。

## 2. 节点 schema

`GET /object_info`（全量，首次约 1–5 秒，之后有缓存） / `GET /object_info/<Class>`

转换器只依赖这几个字段：

```json
{
  "KSampler": {
    "input": {
      "required": {
        "model": ["MODEL"],
        "seed": ["INT", {"default": 0, "control_after_generate": true}],
        "sampler_name": [["euler", "dpmpp_2m"]],
        "positive": ["CONDITIONING"]
      },
      "optional": {"denoise": ["FLOAT", {"default": 1.0}]}
    },
    "output": ["LATENT"],
    "output_name": ["LATENT"],
    "category": "sampling",
    "output_node": false
  }
}
```

判定规则（与前端一致）：

- `spec[0]` 是 `INT/FLOAT/STRING/BOOLEAN/COMBO` 或**字符串数组**（下拉）→ 该输入是"组件（widget）"，值来自 `widgets_values`；
- `spec[1].forceInput == true` → 即使类型可组件化，也按连线处理；
- `hidden` 段不参与控件值还原；
- `control_after_generate: true` → 前端会多存一个控制值（`fixed/increment/decrement/randomize`），还原时**必须多吞一个 token**。

## 3. 提交执行

`POST /prompt`

```json
{"prompt": {"1": {"class_type": "LocalTTS_SAPI",
                  "inputs": {"text": "你好", "voice": "auto", "rate": 0, "volume": 100},
                  "_meta": {"title": "文生语音"}},
            "2": {"class_type": "SaveAudioAdvanced",
                  "inputs": {"audio": ["1", 0], "filename_prefix": "audio/tts", "format": "flac"}}},
 "client_id": "comfyui-named-runner"}
```

成功：

```json
{"prompt_id": "4a1c...-uuid", "number": 12, "node_errors": {}}
```

失败（HTTP 400，也可能 200 带 `error`）：`error` 是整体错误，`node_errors` 按节点给细节：

```json
{"error": {"type": "prompt_outputs_failed_validation", "message": "Prompt outputs failed validation"},
 "node_errors": {"2": {"class_type": "SaveAudioAdvanced",
                       "errors": [{"type": "value_not_in_list", "message": "Value not in list",
                                   "details": "format: 'wav' not in ['flac','mp3','opus']"}]}}}
```

本工具会把 `node_errors` 拼成人类可读的 `hint`，并以 `exec` 阶段（退出码 6）返回。

## 4. 查结果

`GET /history/<prompt_id>`（未完成时返回 `{}`）

```json
{"<prompt_id>": {
  "prompt": [12, "<prompt_id>", {...}, {...}, [["2", "SaveAudioAdvanced"]]],
  "outputs": {"2": {"audio": [{"filename": "tts_00001_.flac", "subfolder": "audio", "type": "output"}]}},
  "status": {"status_str": "success", "completed": true,
             "messages": [["execution_start", {...}]]}
}}
```

- 失败时 `status.status_str == "error"`，`messages` 里有 `["execution_error", {"exception_type": ..., "node_id": ..., "node_type": ...}]`；被中断则是 `["execution_interrupted", {...}]`。
- **产物键不止 `images`**：`audio` / `gifs` / `videos` / `text` / `3d` 都可能出现，形状统一是 `{filename, subfolder, type}` 列表。`collect_outputs` 覆盖了这些键。

`GET /queue` → `{"queue_running": [...], "queue_pending": [...]}`：用于判定"既不在 history 又不在队列"的异常（服务重启 / 任务被取消）。

## 5. 取产物

`GET /view?filename=<name>&subfolder=<sub>&type=output`

- `subfolder` 为空也要显式传 `""`；
- 返回二进制，`Content-Type` 随类型变化（flac → `audio/flac`）；
- 文件名不允许 `..` 或绝对路径（服务端出于安全会返回 400）。

## 6. 上传输入

`POST /upload/image`（`multipart/form-data`）

字段：`image`（文件；音频也用这个字段）、`type=input`、`subfolder`、`overwrite=true`。
响应：`{"name": "foo.png", "subfolder": "", "type": "input"}`。

绑定到 `LoadImage.image` / `LoadAudio.audio` 时用 `name`（有 subfolder 时用 `subfolder/name`）。`run --input-image` / `--input-audio` 做的就是这件事。

## 7. 其它

| 接口 | 用途 |
|---|---|
| `POST /interrupt` | 中断当前执行（`interrupt` 子命令） |
| `POST /free` | 卸载模型释放显存（`{"unload_models": true, "free_memory": true}`） |
| `GET /history?max_items=N` | 近期任务列表 |
| `GET /api/jobs` | 新版任务视图（本工具不用，保持兼容） |

## 8. 常见失败对照

| 现象 | 实际原因 | 处理 |
|---|---|---|
| 连接被拒（WinError 10061） | 服务未启动 / 端口被换 | 启动 ComfyUI 后 `wait`，或 `--base-url` 指定端口 |
| 400 `value_not_in_list` | 下拉值不在候选（模型名/格式/采样器） | `nodes` 或 `/object_info/<Class>` 核对精确值 |
| `prompt_outputs_failed_validation` | 输出节点缺必填输入（连线被静音/旁通切断） | `describe` 看该节点输入是否为空 |
| 提交成功但 history 长时间为空、队列也空 | 服务重启或任务被取消 | 重新提交；查服务端日志 |
| 下载 404 | 产物已被清理（temp 目录/手工删除） | 用 `--out` 及时另存，或改工作流输出目录 |
