"""ComfyUI 本地服务客户端库（仅标准库）。

职责：
  * 配置解析（默认值 < 配置文件 < 环境变量 < CLI 参数）
  * 服务发现与健康检查（支持端口自动探测，ComfyUI Desktop 的 portConflict=auto 会换端口）
  * 提交 / 轮询 / 下载 / 取消
  * UI 工作流（nodes+links）→ API 工作流（prompt graph）转换
  * 参数绑定、种子处理、输出收集

CLI 见同目录 comfy.py；本模块可被其他项目直接 import 复用。
"""

from __future__ import annotations

import copy
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

# ---------------------------------------------------------------- 退出码约定
EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_CONNECT = 3
EXIT_WORKFLOW = 4
EXIT_PARAM = 5
EXIT_EXEC = 6
EXIT_TIMEOUT = 7
EXIT_IO = 8

STAGE_EXIT = {
    "config": EXIT_CONFIG,
    "connect": EXIT_CONNECT,
    "workflow": EXIT_WORKFLOW,
    "param": EXIT_PARAM,
    "exec": EXIT_EXEC,
    "timeout": EXIT_TIMEOUT,
    "io": EXIT_IO,
}


class ComfyError(Exception):
    """带阶段标记的异常，CLI 依此决定退出码与提示。"""

    def __init__(self, stage, message, hint=None):
        super().__init__(message)
        self.stage = stage
        self.message = message
        self.hint = hint

    @property
    def exit_code(self):
        return STAGE_EXIT.get(self.stage, EXIT_EXEC)

    def to_dict(self):
        d = {"ok": False, "stage": self.stage, "error": self.message}
        if self.hint:
            d["hint"] = self.hint
        return d


# ---------------------------------------------------------------- 默认配置
SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ComfyUI 代码根目录的兜底值：优先环境变量 COMFYUI_ROOT，其次 config.json 的 comfyui_root。
# 两者都没有时退回当前工作目录（doctor 会明确报出各路径是否存在，不会静默乱猜）。
DEFAULT_COMFY_ROOT = os.environ.get("COMFYUI_ROOT") or os.getcwd()

DEFAULTS = {
    "base_url": "http://127.0.0.1:8188",
    "port_scan": [8188, 8189, 8190, 8191, 8192],
    "comfyui_root": DEFAULT_COMFY_ROOT,
    "workflows_dir": None,          # 缺省 = <comfyui_root>/user/default/workflows
    "output_dir": None,             # 缺省 = <comfyui_root>/output
    "input_dir": None,              # 缺省 = <comfyui_root>/input
    "python": None,                 # 缺省 = <comfyui_root>/../standalone-env/python.exe
    "timeout_submit": 120,
    "timeout_job": 1800,
    "poll_interval": 1.5,
    "http_timeout": 60,
}

ENV_MAP = {
    "COMFY_URL": "base_url",
    "COMFYUI_ROOT": "comfyui_root",
    "COMFY_WORKFLOWS_DIR": "workflows_dir",
    "COMFY_OUTPUT_DIR": "output_dir",
    "COMFY_INPUT_DIR": "input_dir",
}

CONFIG_CANDIDATES = [
    os.environ.get("COMFY_SKILL_CONFIG") or "",
    os.path.join(SKILL_ROOT, "config.json"),
    os.path.join(os.getcwd(), ".comfyui-skill.json"),
]


def _read_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def load_config(overrides=None, config_path=None):
    """按 默认值 < 配置文件 < 环境变量 < overrides 的顺序合并配置。"""
    cfg = dict(DEFAULTS)
    cfg["_sources"] = []

    candidates = ([config_path] if config_path else []) + [p for p in CONFIG_CANDIDATES if p]
    for path in candidates:
        if path and os.path.isfile(path):
            try:
                data = _read_json(path)
            except Exception as exc:  # noqa: BLE001
                raise ComfyError("config", "配置文件无法解析：%s（%s）" % (path, exc))
            if isinstance(data, dict):
                for k, v in data.items():
                    if k.startswith("_") or k == "workflows":
                        continue
                    cfg[k] = v
                cfg["_sources"].append(path)
            break

    for env, key in ENV_MAP.items():
        if os.environ.get(env):
            cfg[key] = os.environ[env]
            cfg["_sources"].append("env:" + env)

    for k, v in (overrides or {}).items():
        if v is not None:
            cfg[k] = v

    # 派生路径
    root = cfg.get("comfyui_root") or DEFAULT_COMFY_ROOT
    cfg["comfyui_root"] = os.path.normpath(root)
    if not cfg.get("workflows_dir"):
        cfg["workflows_dir"] = os.path.join(cfg["comfyui_root"], "user", "default", "workflows")
    if not cfg.get("output_dir"):
        cfg["output_dir"] = os.path.join(cfg["comfyui_root"], "output")
    if not cfg.get("input_dir"):
        cfg["input_dir"] = os.path.join(cfg["comfyui_root"], "input")
    if not cfg.get("python"):
        # ComfyUI Desktop 的实际运行环境是 <root>/.venv（standalone-env 只是引导环境，没有 torch）
        for guess in (os.path.join(cfg["comfyui_root"], ".venv", "Scripts", "python.exe"),
                      os.path.join(cfg["comfyui_root"], ".venv", "bin", "python"),
                      os.path.join(os.path.dirname(cfg["comfyui_root"]), "standalone-env", "python.exe")):
            if os.path.exists(guess):
                cfg["python"] = guess
                break
    cfg.setdefault("client_id", "comfyui-local-skill")
    return cfg


def registry_path(cfg=None):
    return os.path.join(cfg["_skill_root"] if cfg and cfg.get("_skill_root") else SKILL_ROOT,
                        "registry.json")


def load_registry():
    path = os.path.join(SKILL_ROOT, "registry.json")
    if not os.path.isfile(path):
        return {"workflows": {}}
    try:
        data = _read_json(path)
    except Exception as exc:  # noqa: BLE001
        raise ComfyError("config", "registry.json 解析失败：%s（%s）" % (path, exc))
    data.setdefault("workflows", {})
    return data


def save_registry(reg):
    path = os.path.join(SKILL_ROOT, "registry.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    return path


# ---------------------------------------------------------------- 服务端
class Server:
    def __init__(self, cfg, base_url=None):
        self.cfg = cfg
        self.base_url = (base_url or cfg.get("base_url") or DEFAULTS["base_url"]).rstrip("/")
        self.client_id = cfg.get("client_id") or str(uuid.uuid4())
        self._system_stats = None
        self._object_info = None

    # -- 低层请求 ---------------------------------------------------
    def _request(self, path, data=None, timeout=None, method=None):
        url = path if path.startswith("http") else self.base_url + path
        body = None
        headers = {}
        if data is not None:
            if isinstance(data, (bytes, bytearray)):
                body = bytes(data)
            else:
                body = json.dumps(data).encode("utf-8")
                headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.cfg["http_timeout"]) as resp:
                return resp.read(), resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise ComfyError("exec", "HTTP %s %s：%s" % (exc.code, path.split("?")[0], detail[:600]))
        except urllib.error.URLError as exc:
            raise ComfyError("connect", "无法连接 ComfyUI（%s）：%s" % (self.base_url, exc.reason),
                             hint="确认 ComfyUI Desktop 已启动，或用 `comfy.py doctor` 检查端口。")
        except TimeoutError:
            raise ComfyError("timeout", "请求超时：%s" % path)

    def get_json(self, path, timeout=None):
        raw, _ = self._request(path, timeout=timeout)
        return json.loads(raw.decode("utf-8"))

    def post_json(self, path, payload, timeout=None):
        raw, _ = self._request(path, data=payload, timeout=timeout)
        text = raw.decode("utf-8").strip()
        return json.loads(text) if text else {}

    # -- 发现与健康 -------------------------------------------------
    def system_stats(self, timeout=6):
        if self._system_stats is None:
            self._system_stats = self.get_json("/system_stats", timeout=timeout)
        return self._system_stats

    def resolve(self):
        """检查配置地址；不可达时扫描候选端口（Desktop 会自动换端口）。"""
        errors = []
        try:
            self.system_stats()
            return self.base_url
        except ComfyError as exc:
            errors.append("%s → %s" % (self.base_url, exc.message))
        for port in self.cfg.get("port_scan") or []:
            cand = "http://127.0.0.1:%d" % int(port)
            if cand == self.base_url:
                continue
            probe = Server(self.cfg, cand)
            probe.client_id = self.client_id
            try:
                probe.system_stats()
            except ComfyError:
                continue
            self.base_url = cand
            self._system_stats = probe._system_stats
            return self.base_url
        raise ComfyError("connect", "未找到可用的 ComfyUI 服务。尝试过：%s" % "；".join(errors),
                         hint="启动 ComfyUI Desktop 后重试；或设置环境变量 COMFY_URL=http://127.0.0.1:<port>。")

    # -- 节点与队列 -------------------------------------------------
    def object_info(self, node_class=None):
        if node_class:
            return self.get_json("/object_info/" + urllib.parse.quote(node_class))
        if self._object_info is None:
            self._object_info = self.get_json("/object_info", timeout=120)
        return self._object_info

    def queue(self):
        return self.get_json("/queue")

    def interrupt(self):
        return self.post_json("/interrupt", {})

    def upload_image(self, path, subfolder=""):
        """上传本地图片到 ComfyUI input，返回可用于 LoadImage 的字符串。"""
        return self.upload_file(path, subfolder=subfolder)

    def upload_file(self, path, subfolder=""):
        """上传本地文件（图片/音频/视频）到 ComfyUI input，返回可用于 Load* 节点的名字。

        ComfyUI 的 /upload/image 只是历史命名的通用上传口，音频（LoadAudio 的参考音色）
        同样走这里；返回值为 `subfolder/name` 形式。
        """
        if not os.path.isfile(path):
            raise ComfyError("io", "输入文件不存在：%s" % path)
        with open(path, "rb") as f:
            payload = f.read()
        boundary = "----ComfySkillBoundary%s" % uuid.uuid4().hex
        name = os.path.basename(path)
        parts = []
        for field, value in (("type", "input"), ("subfolder", subfolder or ""),
                             ("overwrite", "true")):
            parts.append(
                ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                 % (boundary, field, value)).encode("utf-8"))
        parts.append(
            ("--%s\r\nContent-Disposition: form-data; name=\"image\"; filename=\"%s\"\r\n"
             "Content-Type: application/octet-stream\r\n\r\n" % (boundary, name)).encode("utf-8"))
        parts.append(payload)
        parts.append(("\r\n--%s--\r\n" % boundary).encode("utf-8"))
        body = b"".join(parts)
        url = self.base_url + "/upload/image"
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary})
        try:
            with urllib.request.urlopen(req, timeout=max(60, self.cfg["http_timeout"])) as resp:
                info = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ComfyError("io", "上传失败 HTTP %s：%s" % (exc.code, exc.read().decode("utf-8", "replace")[:400]))
        except urllib.error.URLError as exc:
            raise ComfyError("connect", "上传失败：%s" % exc.reason)
        sub = info.get("subfolder") or ""
        return (sub + "/" + info["name"]) if sub else info["name"]

    # -- 执行 -------------------------------------------------------
    def submit(self, prompt):
        payload = {"prompt": prompt, "client_id": self.client_id}
        try:
            resp = self.post_json("/prompt", payload, timeout=self.cfg["timeout_submit"])
        except ComfyError as exc:
            raise ComfyError("exec", exc.message,
                             hint="常见原因：节点类未安装、模型文件不存在、必填输入缺失。")
        if resp.get("error"):
            raise ComfyError("exec", "ComfyUI 拒绝执行：%s" % json.dumps(resp.get("error"), ensure_ascii=False)[:600],
                             hint=_node_error_hint(resp.get("node_errors")))
        if resp.get("node_errors"):
            raise ComfyError("exec", "节点校验失败：%s" % json.dumps(resp["node_errors"], ensure_ascii=False)[:900],
                             hint=_node_error_hint(resp["node_errors"]))
        pid = resp.get("prompt_id")
        if not pid:
            raise ComfyError("exec", "提交成功但未返回 prompt_id：%s" % json.dumps(resp, ensure_ascii=False)[:300])
        return pid

    def wait(self, prompt_id, timeout=None, poll=None):
        timeout = timeout or self.cfg["timeout_job"]
        poll = poll or self.cfg["poll_interval"]
        t0 = time.time()
        empty_queue_seen = 0
        while time.time() - t0 < timeout:
            try:
                hist = self.get_json("/history/" + urllib.parse.quote(prompt_id))
            except ComfyError:
                hist = {}
            entry = (hist or {}).get(prompt_id)
            if entry:
                status = entry.get("status") or {}
                if status.get("status_str") == "error" or entry.get("error"):
                    raise ComfyError("exec", "执行失败：%s" % _format_status_error(status))
                return entry
            try:
                q = self.queue()
                busy = bool(q.get("queue_running")) or bool(q.get("queue_pending"))
            except ComfyError:
                busy = True
            if not busy:
                empty_queue_seen += 1
                if empty_queue_seen >= 2:
                    raise ComfyError("exec", "任务既不在队列也不在 history（prompt_id=%s），可能被中断或服务重启。" % prompt_id)
            time.sleep(poll)
        raise ComfyError("timeout", "等待超时（%ss）：prompt_id=%s" % (timeout, prompt_id),
                         hint="任务可能仍在跑：用 `comfy.py run ... --no-wait` 拿 prompt_id，稍后查 /history/{id}。")

    def download(self, fileinfo, dest):
        query = urllib.parse.urlencode({
            "filename": fileinfo["filename"],
            "subfolder": fileinfo.get("subfolder", "") or "",
            "type": fileinfo.get("type", "output") or "output",
        })
        url = self.base_url + "/view?" + query
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        tmp = dest + ".part"
        try:
            with urllib.request.urlopen(url, timeout=max(120, self.cfg["http_timeout"])) as resp:
                with open(tmp, "wb") as f:
                    while True:
                        chunk = resp.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
        except urllib.error.HTTPError as exc:
            raise ComfyError("io", "下载失败 HTTP %s：%s" % (exc.code, fileinfo))
        except urllib.error.URLError as exc:
            raise ComfyError("connect", "下载失败：%s" % exc.reason)
        os.replace(tmp, dest)
        return dest


def _node_error_hint(node_errors):
    if not node_errors:
        return None
    hints = []
    for node_id, info in node_errors.items():
        for err in info.get("errors", []) or []:
            hints.append("node %s(%s): %s — %s" % (node_id, info.get("class_type", "?"),
                                                   err.get("message", ""), err.get("details", "")))
    return " / ".join(hints)[:600]


def _format_status_error(status):
    msgs = status.get("messages") or []
    for item in reversed(msgs):
        if isinstance(item, (list, tuple)) and len(item) == 2 and item[0] == "execution_error":
            payload = item[1] or {}
            return "%s: %s（node %s %s）" % (
                payload.get("exception_type", "error"), payload.get("exception_message", ""),
                payload.get("node_id", "?"), payload.get("node_type", ""))
        if isinstance(item, (list, tuple)) and len(item) == 2 and item[0] == "execution_interrupted":
            return "执行被中断"
    return json.dumps(status, ensure_ascii=False)[:600]


# ---------------------------------------------------------------- 工作流格式
UI_ONLY_TYPES = {"Note", "MarkdownNote", "PrimitiveNode", "Reroute",
                 "Reroute (rgthree)", "Bookmark (rgthree)", "Fast Groups Bypasser (rgthree)"}
CONTROL_VALUES = {"fixed", "increment", "decrement", "randomize"}
WIDGET_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO"}


class WorkflowFormatError(ComfyError):
    def __init__(self, message, hint=None):
        super().__init__("workflow", message, hint)


def is_api_format(data):
    if not isinstance(data, dict) or "nodes" in data:
        return False
    if not data:
        return False
    sample = next(iter(data.values()))
    return isinstance(sample, dict) and "class_type" in sample


def _is_widget(kind, opts):
    if opts.get("forceInput"):
        return False
    if isinstance(kind, list):
        return True
    if not isinstance(kind, str):
        return False
    up = kind.upper()
    if up in WIDGET_TYPES:
        return True
    # 新版核心节点用 COMFY_DYNAMICCOMBO_V3 / *_COMBO 之类标记组件（如 SaveAudioAdvanced.format）
    return up.startswith("COMFY_") or "COMBO" in up


def _suspicious(kind, value):
    """组件值与该输入声明的类型/候选明显不符时返回 True（用于发现 UI→API 错位）。"""
    if isinstance(kind, list):
        return value is not None and value not in kind
    if kind == "INT":
        return not isinstance(value, int) or isinstance(value, bool)
    if kind == "FLOAT":
        return not isinstance(value, (int, float)) or isinstance(value, bool)
    if kind == "STRING":
        return not isinstance(value, str)
    if kind == "BOOLEAN":
        return not isinstance(value, bool)
    return False


def widget_specs(node_info):
    """按前端顺序返回 [(name, kind, opts), ...]。"""
    specs = []
    sections = node_info.get("input") or {}
    for section in ("required", "optional"):
        for name, spec in (sections.get(section) or {}).items():
            if not isinstance(spec, (list, tuple)) or not spec:
                continue
            kind = spec[0]
            opts = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
            if _is_widget(kind, opts):
                specs.append((name, kind, opts))
    return specs


def ui_to_api(data, object_info, strict=True):
    """把 UI 格式工作流（nodes + links）转换成 API prompt graph。

    返回 (prompt, warnings)。prompt 形如 {"7": {"class_type": ..., "inputs": {...}}}。
    """
    if is_api_format(data):
        return copy.deepcopy(data), []

    if not isinstance(data, dict) or "nodes" not in data:
        raise WorkflowFormatError("无法识别的工作流格式：既不是 UI 格式（含 nodes/links），也不是 API 格式。")

    warnings = []
    nodes = {n["id"]: n for n in data.get("nodes", [])}
    links = {}
    for link in data.get("links", []) or []:
        if isinstance(link, (list, tuple)) and len(link) >= 5:
            links[link[0]] = link
        elif isinstance(link, dict) and "id" in link:
            links[link["id"]] = [link["id"], link.get("origin_id"), link.get("origin_slot"),
                                 link.get("target_id"), link.get("target_slot"), link.get("type")]

    # 子图 / 组节点：v0.38 的 definitions.subgraphs 需要展开，这里明确报错
    defs = data.get("definitions") or {}
    if defs.get("subgraphs"):
        raise WorkflowFormatError(
            "工作流包含子图（subgraph），当前转换器不支持自动展开。",
            hint="在 ComfyUI 界面里右键子图 → 展开（Unpack），或先导出 API 格式（工作流菜单 → Export (API)）后再登记。")
    unknown = [n for n in nodes.values()
               if n.get("type") not in object_info and n.get("type") not in UI_ONLY_TYPES
               and not str(n.get("type", "")).strip().isdigit()]
    if unknown:
        names = sorted({n.get("type") for n in unknown})
        raise WorkflowFormatError(
            "以下节点类未安装或无法识别：%s" % ", ".join(names),
            hint="先装好对应自定义节点并重启 ComfyUI，或在 GUI 里删除这些节点后另存。")

    bypassed = {nid for nid, n in nodes.items() if n.get("mode") == 4}
    muted = {nid for nid, n in nodes.items() if n.get("mode") == 2}
    reroutes = {nid for nid, n in nodes.items() if n.get("type") == "Reroute"}

    def resolve_source(link_id, depth=0):
        if link_id is None:
            return None
        if depth > 64:
            raise WorkflowFormatError("工作流链接存在环（link_id=%s）" % link_id)
        link = links.get(link_id)
        if not link:
            return None
        src_id, src_slot = link[1], link[2]
        src = nodes.get(src_id)
        if src is None:
            return None
        if src_id in muted:
            return None
        if src_id in reroutes:
            ins = src.get("inputs") or []
            return resolve_source(ins[0].get("link"), depth + 1) if ins else None
        if src_id in bypassed:
            out_type = None
            outs = src.get("outputs") or []
            if src_slot < len(outs):
                out_type = outs[src_slot].get("type")
            for inp in src.get("inputs") or []:
                if inp.get("link") is None:
                    continue
                if out_type in (None, "*") or inp.get("type") == out_type:
                    return resolve_source(inp["link"], depth + 1)
            return None
        return [str(src_id), src_slot]

    prompt = {}
    for nid, node in nodes.items():
        ntype = node.get("type")
        if nid in muted or nid in reroutes or ntype in UI_ONLY_TYPES or ntype == "Reroute":
            continue
        if nid in bypassed:
            continue
        info = object_info.get(ntype)
        if not info:
            warnings.append("跳过未知节点 %s(%s)" % (nid, ntype))
            continue

        specs = widget_specs(info)
        values = node.get("widgets_values")
        conn = {}
        for inp in node.get("inputs") or []:
            if inp.get("link") is not None and inp.get("name"):
                conn[inp["name"]] = inp["link"]

        inputs = {}
        if isinstance(values, dict):
            for name, _kind, _opts in specs:
                if name in values:
                    inputs[name] = values[name]
        elif isinstance(values, list):
            i = 0
            for name, kind, opts in specs:
                if i >= len(values):
                    break
                # seed 类节点会多出一个“生成后控制”值
                extra = 0
                if opts.get("control_after_generate"):
                    extra = 1
                elif name in ("seed", "noise_seed") and i + 1 < len(values) \
                        and isinstance(values[i + 1], str) and values[i + 1] in CONTROL_VALUES:
                    extra = 1
                value = values[i]
                if name not in conn:
                    inputs[name] = value
                    if _suspicious(kind, value):
                        if isinstance(kind, list):
                            warnings.append(
                                "节点 %s(%s) 的 %s=%r 不在候选列表（模型/文件可能不存在，"
                                "或自定义 JS 控件导致控件错位）" % (nid, ntype, name, value))
                        else:
                            warnings.append(
                                "节点 %s(%s) 的 %s=%r 类型与该输入不符，疑似自定义 JS 控件导致错位；"
                                "建议把该工作流在 GUI 里 Export (API) 后登记 API 格式"
                                % (nid, ntype, name, value))
                i += 1 + extra

        for name, link_id in conn.items():
            src = resolve_source(link_id)
            if src is None:
                continue
            inputs[name] = src
            # 兼容控件名与输入名不一致的情况（极少见）
            if name not in inputs:
                inputs[name] = src

        entry = {"class_type": ntype, "inputs": inputs}
        title = node.get("title")
        if title:
            entry["_meta"] = {"title": title}
        prompt[str(nid)] = entry

    if not prompt:
        raise WorkflowFormatError("转换后没有任何可执行节点（可能全部被静音/旁通）。")

    for nid, entry in prompt.items():
        info = object_info.get(entry["class_type"])
        if not info:
            continue
        required = (info.get("input") or {}).get("required") or {}
        for name in required:
            if name not in entry["inputs"]:
                opts = required[name][1] if len(required[name]) > 1 and isinstance(required[name][1], dict) else {}
                if _is_widget(required[name][0], opts):
                    warnings.append("节点 %s(%s) 缺少输入 %s，将由服务端报错"
                                    % (nid, entry["class_type"], name))
    return prompt, warnings


# ---------------------------------------------------------------- 工作流查找
def _iter_workflow_files(root):
    if not os.path.isdir(root):
        return
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            if fn.lower().endswith(".json"):
                yield os.path.join(dirpath, fn)


def _rel(root, path):
    try:
        return os.path.relpath(path, root).replace("\\", "/")
    except ValueError:
        return path


def load_workflow_source(source, cfg):
    """解析 source 说明符，返回 (data, 说明文本)。

    source 形式：
      user:<相对 workflows_dir 的路径>   例：user:tts_zh_sapi.json
      api:<相对 skill/scripts/workflows> 例：api:tts_sapi.json
      file:<绝对或相对路径>
      <裸路径/裸名称>                    按文件路径或已登记别名处理
    """
    if not source:
        raise ComfyError("config", "工作流 source 为空")
    kind, _, rest = source.partition(":")
    if _ and kind in ("user", "api", "file"):
        if kind == "user":
            path = os.path.join(cfg["workflows_dir"], rest.replace("/", os.sep))
        elif kind == "api":
            path = os.path.join(SKILL_ROOT, "scripts", "workflows", rest.replace("/", os.sep))
        else:
            path = rest
    else:
        path = source
    if not os.path.isfile(path):
        raise ComfyError("workflow", "工作流文件不存在：%s（source=%s）" % (path, source),
                         hint="用 `comfy.py list` 查看已登记与可发现的工作流。")
    try:
        data = _read_json(path)
    except Exception as exc:  # noqa: BLE001
        raise ComfyError("workflow", "工作流 JSON 解析失败：%s（%s）" % (path, exc))
    return data, path


def discover_workflows(cfg):
    """扫描 workflows_dir，返回 [{stem, rel, path, api(bool)}]。"""
    out = []
    for path in _iter_workflow_files(cfg["workflows_dir"]):
        try:
            data = _read_json(path)
        except Exception:  # noqa: BLE001
            continue
        out.append({
            "stem": os.path.splitext(os.path.basename(path))[0],
            "rel": _rel(cfg["workflows_dir"], path),
            "path": path,
            "api": is_api_format(data),
        })
    return sorted(out, key=lambda x: x["rel"].lower())


def resolve_workflow(name, cfg, registry=None):
    """按别名 / 文件名 / 路径 找到工作流，返回 (ref_dict, data)。

    ref_dict 至少包含: alias, title, source, params, defaults, path
    """
    registry = registry if registry is not None else load_registry()
    entries = registry.get("workflows") or {}

    key = None
    if name in entries:
        key = name
    else:
        low = name.lower()
        for k in entries:
            if k.lower() == low:
                key = k
                break
    if key:
        ref = dict(entries[key])
        ref["alias"] = key
        data, path = load_workflow_source(ref["source"], cfg)
        ref["path"] = path
        return ref, data

    # 直接给路径
    if os.path.isfile(name):
        data, path = load_workflow_source(name, cfg)
        return {"alias": os.path.splitext(os.path.basename(name))[0], "title": None,
                "source": name, "params": {}, "defaults": {}, "path": path}, data

    found = discover_workflows(cfg)
    exact = [w for w in found if w["stem"] == name or w["rel"] == name.replace("\\", "/")]
    if not exact:
        low = name.lower()
        exact = [w for w in found if w["stem"].lower() == low or w["rel"].lower() == low]
    if len(exact) == 1:
        w = exact[0]
        data = _read_json(w["path"])
        return {"alias": w["stem"], "title": None, "source": "user:" + w["rel"],
                "params": {}, "defaults": {}, "path": w["path"]}, data

    partial = [w for w in found if name.lower() in w["rel"].lower()]
    if len(exact) > 1 or len(partial) > 1:
        names = "、".join(w["rel"] for w in (exact or partial)[:12])
        raise ComfyError("workflow", "工作流名称不唯一：%s（候选：%s）" % (name, names))
    if partial:
        w = partial[0]
        data = _read_json(w["path"])
        return {"alias": w["stem"], "title": None, "source": "user:" + w["rel"],
                "params": {}, "defaults": {}, "path": w["path"]}, data

    raise ComfyError("workflow", "找不到工作流：%s" % name,
                     hint="`comfy.py list --all` 查看可发现的工作流；或用 register 登记别名。")


# ---------------------------------------------------------------- 参数绑定
def _coerce(value, declared=None):
    if not isinstance(value, str):
        return value
    t = (declared or "").lower()
    if t in ("int", "integer"):
        return int(value)
    if t in ("float", "number"):
        return float(value)
    if t in ("bool", "boolean"):
        return value.strip().lower() in ("1", "true", "yes", "on")
    if t in ("str", "string"):
        return value
    if t == "json":
        return json.loads(value)
    s = value.strip()
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    if re.fullmatch(r"-?\d+", s):
        try:
            return int(s)
        except ValueError:
            return value
    if re.fullmatch(r"-?\d+\.\d+", s):
        try:
            return float(s)
        except ValueError:
            return value
    if s[:1] in "[{" and s[-1:] in "]}":
        try:
            return json.loads(s)
        except ValueError:
            return value
    return value


def _nodes_with_input(prompt, input_name):
    return [nid for nid, node in prompt.items()
            if input_name in (node.get("inputs") or {})
            or input_name in ((node.get("_meta") or {}).get("inputs") or [])]


def _match_node(prompt, spec):
    node = spec.get("node")
    if node is not None:
        sid = str(node)
        if sid not in prompt:
            raise ComfyError("param", "参数绑定的节点 id 不存在：%s" % sid,
                             hint="用 `comfy.py describe <工作流>` 查看节点 id。")
        return sid
    title = spec.get("node_title")
    if title:
        hits = [nid for nid, n in prompt.items()
                if title in ((n.get("_meta") or {}).get("title") or "")]
        if len(hits) == 1:
            return hits[0]
        if not hits:
            raise ComfyError("param", "找不到标题含“%s”的节点" % title)
        raise ComfyError("param", "标题含“%s”的节点有多个：%s" % (title, ", ".join(hits)))
    cls = spec.get("node_class")
    if cls:
        hits = [nid for nid, n in prompt.items() if n.get("class_type") == cls]
        if len(hits) == 1:
            return hits[0]
        if not hits:
            raise ComfyError("param", "找不到节点类 %s" % cls)
        raise ComfyError("param", "节点类 %s 有多个实例：%s，请改用 node id" % (cls, ", ".join(hits)))
    return None


def _has_input(inputs, path):
    """匹配参数路径：先按原样匹配（ComfyUI 的 v3 节点会用 `task.voice` 这类带点键名），
    再回退到字典型输入里的嵌套路径。"""
    if path in inputs:
        return True
    head, _, tail = path.partition(".")
    if not tail:
        return False
    box = inputs.get(head)
    return isinstance(box, dict) and _has_input(box, tail)


def _set_input(inputs, path, value):
    if path in inputs:
        inputs[path] = value
        return True
    head, _, tail = path.partition(".")
    if not tail:
        return False
    box = inputs.get(head)
    if isinstance(box, dict):
        return _set_input(box, tail, value)
    return False


def bind_params(prompt, ref, params, seed=None):
    """把参数写入 prompt，返回 (applied_dict, warnings)。

    参数查找顺序：
      1. registry 里该工作流的 params 绑定（node / node_title / node_class + input）
      2. 自动绑定：图里只有一处同名输入时直接写入
      3. 都没有 → ComfyError(param)，列出可用输入

    `input` 支持点号路径，用于字典型输入（如 Ming TTS 的 `task.voice`、
    `task.reference_text`、`task.language`）。
    """
    applied, warnings = {}, []
    spec_map = (ref.get("params") or {})
    defaults = dict(ref.get("defaults") or {})
    unknown_defaults = {k: v for k, v in defaults.items() if k not in params}
    merged = dict(unknown_defaults)
    merged.update(params or {})

    for key, raw in merged.items():
        spec = spec_map.get(key) or {}
        input_name = spec.get("input") or key
        target = _match_node(prompt, spec) if spec else None
        if target is None:
            hits = [nid for nid, n in prompt.items() if _has_input(n.get("inputs") or {}, input_name)]
            if len(hits) > 1:
                raise ComfyError("param", "参数 %s 在多个节点上存在（%s），请在 registry 里显式绑定"
                                 % (key, ", ".join(hits)))
            if not hits:
                avail = sorted({k for n in prompt.values() for k in (n.get("inputs") or {})})
                raise ComfyError("param", "参数 %s 在工作流里找不到对应输入" % key,
                                 hint="可用输入：%s" % ", ".join(avail[:40]))
            target = hits[0]
        value = _coerce(raw, spec.get("type"))
        if not _set_input(prompt[target]["inputs"], input_name, value):
            raise ComfyError("param", "参数 %s 无法写入 %s.%s（该路径不存在或不是字典）"
                             % (key, target, input_name))
        applied[key] = {"node": target, "input": input_name, "value": value}

    if seed is not None:
        seed_hits = 0
        for nid, node in prompt.items():
            for key in ("seed", "noise_seed"):
                if key in (node.get("inputs") or {}):
                    node["inputs"][key] = int(seed)
                    applied["seed"] = {"node": nid, "input": key, "value": int(seed)}
                    seed_hits += 1
        if not seed_hits:
            warnings.append("工作流没有 seed/noise_seed 输入，--seed 被忽略")

    return applied, warnings


# ---------------------------------------------------------------- 输出收集
FILE_KEYS = ("images", "audio", "gifs", "videos", "3d", "files", "video", "audio_files")
TEXT_KEYS = ("text", "string", "strings", "texts")


def collect_outputs(history, server, outdir, prefix, want_download=True):
    """遍历 history.outputs，下载文件型产物、落盘文本型产物。"""
    files, texts, warnings = [], {}, []
    os.makedirs(outdir, exist_ok=True)
    for node_id, node_out in (history.get("outputs") or {}).items():
        if not isinstance(node_out, dict):
            continue
        for key in FILE_KEYS:
            items = node_out.get(key) or []
            if isinstance(items, dict):
                items = [items]
            for idx, item in enumerate(items):
                if not isinstance(item, dict) or not item.get("filename"):
                    continue
                ext = os.path.splitext(item["filename"])[1] or ".bin"
                dest = os.path.join(outdir, "%s_%s_%s_%d%s" % (prefix, node_id, key, idx, ext))
                if want_download:
                    try:
                        server.download(item, dest)
                    except ComfyError as exc:
                        warnings.append("下载 %s 失败：%s" % (item["filename"], exc.message))
                        continue
                    files.append({
                        "path": os.path.abspath(dest),
                        "kind": key,
                        "node": node_id,
                        "source": item["filename"],
                        "bytes": os.path.getsize(dest),
                    })
                else:
                    files.append({"path": None, "kind": key, "node": node_id,
                                  "source": item["filename"], "filename": item["filename"],
                                  "subfolder": item.get("subfolder", ""), "type": item.get("type", "output")})
        for key in TEXT_KEYS:
            val = node_out.get(key)
            if isinstance(val, list) and val and all(isinstance(v, str) for v in val):
                texts[str(node_id)] = "\n".join(val)
            elif isinstance(val, str):
                texts[str(node_id)] = val
    if texts and want_download:
        path = os.path.join(outdir, "%s_text.json" % prefix)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(texts, f, ensure_ascii=False, indent=2)
        files.append({"path": os.path.abspath(path), "kind": "text", "node": None,
                      "source": "aggregated", "bytes": os.path.getsize(path)})
    return files, texts, warnings


# ---------------------------------------------------------------- 汇总信息
def summarize_prompt(prompt):
    """给 describe 用的节点清单。"""
    rows = []
    for nid, node in prompt.items():
        inputs = {}
        for k, v in (node.get("inputs") or {}).items():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                inputs[k] = "<- %s.%s" % (v[0], v[1])
            else:
                inputs[k] = v
        rows.append({
            "id": nid,
            "class_type": node.get("class_type"),
            "title": (node.get("_meta") or {}).get("title"),
            "inputs": inputs,
        })
    return rows


def parse_kv(pairs):
    """解析 -p key=value 列表。"""
    out = {}
    for raw in pairs or []:
        if "=" not in raw:
            raise ComfyError("param", "参数格式应为 key=value：%s" % raw)
        k, _, v = raw.partition("=")
        out[k.strip()] = v
    return out
