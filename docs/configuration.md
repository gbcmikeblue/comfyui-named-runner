# 配置

## 1. 优先级

```
内置默认值  <  config.json  <  环境变量  <  命令行参数
```

配置文件查找顺序（取第一个存在的）：

1. `--config <path>` 显式指定
2. 环境变量 `COMFY_SKILL_CONFIG` 指向的文件
3. **仓库根目录**的 `config.json`
4. 当前工作目录的 `.comfyui-skill.json`（适合"项目级配置"：把这个文件放进项目仓库，就能让该项目指向不同 ComfyUI 实例）

以 `_` 开头的键会被忽略，可以放心写 `"_comment": "..."` 之类的注释。

## 2. 配置键

| 键 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `base_url` | str | `http://127.0.0.1:8188` | 服务地址；连不上时按 `port_scan` 依次试探 |
| `port_scan` | list[int] | `[8188..8192]` | 端口扫描列表（ComfyUI Desktop 冲突时会换端口） |
| `comfyui_root` | str | 环境变量 `COMFYUI_ROOT`，否则当前目录 | ComfyUI 代码根目录，其余路径由此派生 |
| `workflows_dir` | str | `<root>/user/default/workflows` | UI 工作流目录，`user:<rel>` 的基准 |
| `output_dir` | str | `<root>/output` | 服务端输出目录（只读诊断用） |
| `input_dir` | str | `<root>/input` | 服务端输入目录（上传参考图/音频用） |
| `python` | str | 自动探测 `.venv` | `doctor` 检查 torch 用的解释器 |
| `timeout_submit` | int | `120` | 单次 HTTP 提交超时（秒） |
| `timeout_job` | int | `1800` | `run` 等待任务完成的总超时（秒），可被 `--timeout` 覆盖 |
| `poll_interval` | float | `1.5` | 轮询 `/history` 的间隔（秒） |
| `http_timeout` | int | `60` | 普通请求超时（秒） |
| `client_id` | str | `comfyui-named-runner` | 写入 `/prompt` 的客户端标识，便于在多客户端场景下区分任务 |

> `python` 的自动探测顺序：`<root>/.venv/Scripts/python.exe` → `<root>/.venv/bin/python` → `<root>/../standalone-env/python.exe`。前两个才是 Desktop 的真实运行环境。

## 3. 环境变量

| 变量 | 覆盖的键 |
|---|---|
| `COMFY_URL` | `base_url` |
| `COMFYUI_ROOT` | `comfyui_root` |
| `COMFY_WORKFLOWS_DIR` | `workflows_dir` |
| `COMFY_OUTPUT_DIR` | `output_dir` |
| `COMFY_INPUT_DIR` | `input_dir` |
| `COMFY_SKILL_CONFIG` | 配置文件路径本身 |

这一组是**跨项目复用**的关键：把 `COMFY_URL` + `COMFY_WORKFLOWS_DIR` 写进项目的环境变量或 `.env` 加载脚本，换机器时只改这两处。

## 4. 最小示例

只写你想覆盖的键即可，其余走默认：

```json
{
  "comfyui_root": "D:\\ComfyUI"
}
```

全部键都写（含 Desktop 的共享目录布局）：

```json
{
  "base_url": "http://127.0.0.1:8188",
  "port_scan": [8188, 8189, 8190, 8191, 8192],
  "comfyui_root": "D:\\Comfy-Desktop\\ComfyUI-Installs\\c1\\ComfyUI",
  "workflows_dir": "D:\\Comfy-Desktop\\ComfyUI-Installs\\c1\\ComfyUI\\user\\default\\workflows",
  "output_dir": "D:\\Comfy-Desktop\\ComfyUI-Shared\\output",
  "input_dir": "D:\\Comfy-Desktop\\ComfyUI-Shared\\input",
  "python": "D:\\Comfy-Desktop\\ComfyUI-Installs\\c1\\ComfyUI\\.venv\\Scripts\\python.exe",
  "timeout_job": 1800,
  "poll_interval": 1.5,
  "client_id": "comfyui-named-runner"
}
```

## 5. 回写配置

```powershell
python scripts\comfy.py doctor --write-config
```

把**当前生效**的配置（含环境变量与命令行覆盖）写进 `config.json`，适合把"临时试出来的正确值"固化下来。写入前建议先 `--json` 看一眼结果。

## 6. 关于 `config.json` 与版本控制

`config.json` 含本机绝对路径，**已在 `.gitignore` 中排除**；仓库里只保留 `config.example.json` 作为模板。同理，`registry.json` 是会被 `register` 改写的文件——如果你的别名里有本机路径，建议用 `user:` / `api:` 相对写法，或改完自行决定是否提交。

## 7. 离线模式

没有启动 ComfyUI 时，下面这些仍然可用（不需要服务）：

| 命令 | 说明 |
|---|---|
| `list` | 只读 `registry.json` 与工作流目录 |
| `describe <名> --schema <object_info.json>` | 用保存的 schema 快照做转换 |
| `run <名> --dry-run --schema <object_info.json>` | 打印转换后的 API 图，不提交 |
| `--dry-run` 配合真实服务 | 拿实时 `/object_info` 校验，同样不提交 |

导出 schema 快照的办法（服务在跑的时候做一次）：

```powershell
curl.exe -s http://127.0.0.1:8188/object_info -o .\object_info.json
```

之后 CI 里就能在没有 ComfyUI 的环境下校验"工作流 + 参数绑定"是否仍然成立。
