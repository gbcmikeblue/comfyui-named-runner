#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ComfyUI 命名工作流执行器 —— 命令行入口（仅标准库，Python 3.9+）。

子命令：
  doctor          体检：服务、端口、路径、节点、registry、torch
  wait            等待用户手动启动的 ComfyUI 就绪（本工具不启动/不重启服务）
  list            列出已登记别名 + 可发现的工作流
  describe        查看某个工作流的节点、参数与产物
  run             按名称执行工作流（转换 UI→API、绑定参数、等结果、下载产物）
  tts             便捷文生语音（TTS 工作流的封装）
  dub             拟真人配音 / 音色克隆（Ming-3.0-tts 0.5B）
  register        把已有工作流登记成别名
  nodes           查询已安装节点类
  interrupt       中断当前执行

统一约定：成功退出码 0；失败退出码见 comfy_client.STAGE_EXIT，并在 stderr 输出结构化错误。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comfy_client as C  # noqa: E402


def _utf8_stdout():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass


def _print(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _fail(exc, as_json):
    if as_json:
        print(json.dumps(exc.to_dict(), ensure_ascii=False), file=sys.stderr)
    else:
        print("[%s] %s" % (exc.stage, exc.message), file=sys.stderr)
        if exc.hint:
            print("  提示：%s" % exc.hint, file=sys.stderr)
    return exc.exit_code


# ------------------------------------------------------------------ doctor
def _check_local_torch(python):
    """检查 ComfyUI 所在运行环境能否 import torch（服务起不来的最常见原因）。"""
    creation = 0x08000000 if os.name == "nt" else 0
    try:
        proc = subprocess.run(
            [python, "-c", "import torch,sys;sys.stdout.write(torch.__version__)"],
            capture_output=True, text=True, timeout=180, creationflags=creation)
    except Exception as exc:  # noqa: BLE001
        return None, "无法调用 python：%s" % exc
    if proc.returncode == 0 and proc.stdout.strip():
        return True, proc.stdout.strip()
    err = (proc.stderr or "").strip().splitlines()
    return False, (err[-1][:200] if err else "import torch 失败")


def cmd_doctor(args, cfg):
    checks = []

    def add(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    add("skill_root", os.path.isdir(C.SKILL_ROOT), C.SKILL_ROOT)
    add("workflows_dir", os.path.isdir(cfg["workflows_dir"]), cfg["workflows_dir"])
    add("output_dir", os.path.isdir(cfg["output_dir"]), cfg["output_dir"])
    add("comfyui_root", os.path.isdir(cfg["comfyui_root"]), cfg["comfyui_root"])
    if cfg.get("python"):
        add("python", os.path.isfile(cfg["python"]), cfg["python"])

    server = C.Server(cfg, args.base_url)
    info = {"base_url": None, "comfyui_version": None, "python": None, "torch": None, "device": None}
    try:
        base = server.resolve()
        info["base_url"] = base
        stats = server.system_stats()
        sysinfo = stats.get("system") or {}
        info["comfyui_version"] = sysinfo.get("comfyui_version")
        info["python"] = sysinfo.get("python_version", "").split()[0] if sysinfo.get("python_version") else None
        info["torch"] = sysinfo.get("pytorch_version")
        devs = stats.get("devices") or []
        if devs:
            d = devs[0]
            info["device"] = "%s (%s MB free / %s MB total)" % (
                d.get("name"), d.get("vram_free"), d.get("vram_total"))
        add("server", True, base)
    except C.ComfyError as exc:
        add("server", False, exc.message)
        checks.append({"check": "hint", "ok": False,
                       "detail": "本 skill 不启动服务：请在 ComfyUI Desktop 点 Launch（或手动运行 main.py 且不覆盖 user/output 目录），"
                                 "再用 `comfy.py wait` 等它就绪。"})

    # torch 预检：服务已在跑就以服务端为准；服务没起时本地 import 失败基本就是起不来的原因
    if cfg.get("python") and os.path.isfile(cfg["python"]):
        ok_torch, torch_detail = _check_local_torch(cfg["python"])
        if ok_torch is not None:
            if info.get("torch"):
                add("torch", True, "服务端 %s（本地 import：%s）"
                    % (info["torch"], "正常" if ok_torch else "失败，Desktop 可能用 PYTHONPATH 注入 torch"))
            else:
                add("torch", ok_torch, torch_detail)
                if not ok_torch:
                    checks.append({"check": "hint", "ok": False,
                                   "detail": "ComfyUI 运行环境里 import torch 失败，服务多半起不来；先修复 torch 栈再手动启动。"})

    tts_node_ok = None
    if info["base_url"]:
        try:
            oi = server.object_info()
            # 配音主链路（Ming-3.0-tts）必须有；SAPI 与 CosyVoice3 为可选后端
            for cls, required in (("MingLoadModel", True), ("MingGenerate", True),
                                  ("LocalTTS_SAPI", False), ("CosyVoiceEngineNode", False)):
                hit = cls in oi
                if required and not hit:
                    add("node:" + cls, False, "未加载，装好自定义节点后需重启 ComfyUI")
                elif hit:
                    add("node:" + cls, True, "已加载")
                else:
                    add("node:" + cls + "(可选)", True, "未安装，对应别名不可用")
            ming = ((oi.get("MingLoadModel") or {}).get("input") or {}).get("required") or {}
            opts = ((ming.get("model") or [None, {}])[1] or {}).get("options") or []
            has_05b = any(str(o).startswith("Ming-3.0-tts-0.5b") for o in opts)
            add("ming_model", has_05b,
                ("可选模型：%s" % ", ".join(opts)) if opts else
                "未发现 Ming 权重，放到 <models>/checkpoints/Ming-3.0-tts-0.5b/model.safetensors")
            add("node_count", True, str(len(oi)))
        except C.ComfyError as exc:
            add("object_info", False, exc.message)

    try:
        reg = C.load_registry()
        add("registry", True, "%d 个别名：%s" % (len(reg["workflows"]), ", ".join(reg["workflows"]) or "无"))
    except C.ComfyError as exc:
        add("registry", False, exc.message)

    found = C.discover_workflows(cfg)
    add("workflow_files", True, "%d 个 UI/API 工作流" % len(found))

    ok = all(c["ok"] for c in checks)
    result = {"ok": ok, "config": {k: v for k, v in cfg.items() if not k.startswith("_")},
              "runtime": info, "checks": checks}

    if args.write_config:
        path = os.path.join(C.SKILL_ROOT, "config.json")
        payload = {k: v for k, v in cfg.items() if not k.startswith("_")}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        result["config_written"] = path

    if args.json:
        _print(result)
    else:
        print("ComfyUI 体检")
        for c in checks:
            print("  %s %-22s %s" % ("OK  " if c["ok"] else "FAIL", c["check"], c["detail"]))
        if info["comfyui_version"]:
            print("\n服务：%s ｜ ComfyUI %s ｜ torch %s ｜ %s"
                  % (info["base_url"], info["comfyui_version"], info["torch"], info["device"]))
        print("工作流目录：%s" % cfg["workflows_dir"])
        if args.write_config:
            print("已写入配置：%s" % result["config_written"])
    return C.EXIT_OK if ok else C.EXIT_CONNECT


# ------------------------------------------------------------------ wait
def cmd_wait(args, cfg):
    """等待用户手动启动的 ComfyUI 就绪（本 skill 不启动服务）。"""
    server = C.Server(cfg, args.base_url)
    deadline = time.time() + args.timeout
    last = ""
    while time.time() < deadline:
        try:
            base = server.resolve()
            stats = server.system_stats()
            ver = (stats.get("system") or {}).get("comfyui_version")
            print("服务就绪：%s ｜ ComfyUI %s" % (base, ver))
            return C.EXIT_OK
        except C.ComfyError as exc:
            last = exc.message
        time.sleep(args.interval)
    raise C.ComfyError("timeout", "等待 ComfyUI 就绪超时（%ss）：%s" % (args.timeout, last),
                       hint="请在 ComfyUI Desktop 里点 Launch 或手动运行 main.py，然后重试；启动较慢时可加大 --timeout。")


# ------------------------------------------------------------------ list
def cmd_list(args, cfg):
    reg = C.load_registry()
    entries = reg.get("workflows") or {}
    rows = []
    for alias, item in entries.items():
        rows.append({"alias": alias, "title": item.get("title"), "source": item.get("source"),
                     "registered": True, "exists": _source_exists(item.get("source"), cfg),
                     "params": sorted((item.get("params") or {}).keys())})
    if args.all or args.filter:
        registered_sources = {str((v or {}).get("source")) for v in entries.values()}
        for w in C.discover_workflows(cfg):
            if w["stem"] in entries or ("user:" + w["rel"]) in registered_sources:
                continue
            rows.append({"alias": w["stem"], "title": None, "source": "user:" + w["rel"],
                         "registered": False, "exists": True, "params": [],
                         "format": "api" if w["api"] else "ui"})
    if args.filter:
        f = args.filter.lower()
        rows = [r for r in rows if f in json.dumps(r, ensure_ascii=False).lower()]
    if args.json:
        _print({"ok": True, "count": len(rows), "workflows": rows})
    else:
        if not rows:
            print("没有可用的工作流（加 --all 扫描 %s）" % cfg["workflows_dir"])
        for r in rows:
            flag = "已登记" if r["registered"] else "未登记"
            miss = "" if r["exists"] else "  [文件缺失]"
            print("%-42s %-6s %s%s" % (r["alias"], flag, r["source"], miss))
            if r["title"]:
                print("    %s" % r["title"])
            if r["params"]:
                print("    参数：%s" % ", ".join(r["params"]))
    return C.EXIT_OK


def _source_exists(source, cfg):
    try:
        C.load_workflow_source(source, cfg)
        return True
    except C.ComfyError:
        return False


# ------------------------------------------------------------------ describe
def cmd_describe(args, cfg):
    ref, data = C.resolve_workflow(args.name, cfg)
    oi, _base, _server = _prepare(args, cfg)
    prompt, warnings = C.ui_to_api(data, oi)
    out = {
        "ok": True,
        "alias": ref.get("alias"),
        "title": ref.get("title"),
        "source": ref.get("source"),
        "path": ref.get("path"),
        "format": "api" if C.is_api_format(data) else "ui",
        "node_count": len(prompt),
        "declared_params": ref.get("params") or {},
        "defaults": ref.get("defaults") or {},
        "nodes": C.summarize_prompt(prompt),
        "warnings": warnings,
    }
    if args.json:
        _print(out)
    else:
        print("别名：%s ｜ %s ｜ 节点 %d 个" % (out["alias"], out["format"].upper(), out["node_count"]))
        print("来源：%s" % out["source"])
        if out["declared_params"]:
            print("已登记参数：")
            for k, v in out["declared_params"].items():
                print("  %-18s → node %s . %s" % (k, v.get("node") or v.get("node_title") or v.get("node_class"),
                                                 v.get("input")))
        print("节点：")
        for n in out["nodes"]:
            print("  [%s] %-32s %s" % (n["id"], n["class_type"], n["title"] or ""))
            for k, v in n["inputs"].items():
                print("        %-24s %s" % (k, v if not isinstance(v, (dict, list)) else json.dumps(v, ensure_ascii=False)[:80]))
        if warnings:
            print("警告：%s" % "；".join(warnings))
    return C.EXIT_OK


# ------------------------------------------------------------------ run
def _prepare(args, cfg):
    """返回 (object_info, base_url, server)。指定 --schema 时离线工作，server 为 None。"""
    schema = getattr(args, "schema", None)
    if schema:
        try:
            with open(schema, "r", encoding="utf-8-sig") as f:
                return json.load(f), "(离线 schema: %s)" % schema, None
        except Exception as exc:  # noqa: BLE001
            raise C.ComfyError("config", "读取 schema 失败：%s（%s）" % (schema, exc))
    server = C.Server(cfg, args.base_url)
    base = server.resolve()
    return server.object_info(), base, server


def _run_workflow(args, cfg, name, params, outdir, title=None):
    ref, data = C.resolve_workflow(name, cfg)
    oi, base, server = _prepare(args, cfg)
    prompt, warnings = C.ui_to_api(data, oi)

    if getattr(args, "input_image", None):
        if server is None:
            raise C.ComfyError("param", "离线 schema 模式不能上传输入图，请连接服务后重试")
        uploaded = server.upload_file(args.input_image)
        params.setdefault("image", uploaded)
        warnings.append("已上传输入图：%s" % uploaded)

    if getattr(args, "input_audio", None):
        if server is None:
            raise C.ComfyError("param", "离线 schema 模式不能上传参考音频，请连接服务后重试")
        uploaded = server.upload_file(args.input_audio)
        params.setdefault("audio", uploaded)
        warnings.append("已上传参考音频：%s" % uploaded)

    applied, w2 = C.bind_params(prompt, ref, params, seed=args.seed)
    warnings += w2

    if args.dry_run:
        result = {"ok": True, "dry_run": True, "workflow": ref.get("alias"), "base_url": base,
                  "applied": applied, "warnings": warnings, "prompt": prompt}
        if args.json:
            _print(result)
        else:
            print("API 工作流（未提交）：")
            print(json.dumps(prompt, ensure_ascii=False, indent=2))
            if applied:
                print("\n参数：%s" % json.dumps(applied, ensure_ascii=False))
        return C.EXIT_OK

    if server is None:
        raise C.ComfyError("config", "离线 schema 模式只能配合 --dry-run 使用")

    t0 = time.time()
    pid = server.submit(prompt)
    if args.no_wait:
        result = {"ok": True, "workflow": ref.get("alias"), "prompt_id": pid, "base_url": base,
                  "submitted": True, "applied": applied, "warnings": warnings}
        _print(result) if args.json else print("已提交：prompt_id=%s（未等待）" % pid)
        return C.EXIT_OK

    history = server.wait(pid, timeout=args.timeout)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    prefix = "%s-%s-%s" % (ref.get("alias") or "wf", stamp, pid[:8])
    files, texts, w3 = C.collect_outputs(history, server, outdir, prefix, want_download=not args.no_download)
    warnings += w3

    result = {
        "ok": bool(files) or bool(texts),
        "workflow": ref.get("alias") or name,
        "title": title or ref.get("title"),
        "base_url": base,
        "prompt_id": pid,
        "elapsed_sec": round(time.time() - t0, 2),
        "output_dir": os.path.abspath(outdir),
        "applied": applied,
        "files": files,
        "text_outputs": texts,
        "warnings": warnings,
    }
    if args.json:
        _print(result)
    else:
        print("完成：%s ｜ %.1fs ｜ prompt_id=%s" % (result["workflow"], result["elapsed_sec"], pid))
        for f in files:
            print("  产物 %-8s %s (%.1f KB)" % (f["kind"], f["path"] or f.get("filename"), (f.get("bytes") or 0) / 1024))
        for k, v in texts.items():
            print("  文本[%s]：%s" % (k, v[:200]))
        if warnings:
            print("  警告：%s" % "；".join(warnings))
        if not files and not texts:
            print("  未获取到产物：检查工作流是否有 Save* 输出节点。")
    return C.EXIT_OK


def cmd_run(args, cfg):
    params = C.parse_kv(args.set)
    outdir = args.out or os.path.join(os.getcwd(), "comfy-out")
    return _run_workflow(args, cfg, args.name, params, outdir)


# ------------------------------------------------------------------ tts
def cmd_tts(args, cfg):
    text = args.text
    if args.text_file:
        with open(args.text_file, "r", encoding="utf-8-sig") as f:
            text = f.read()
    if not text or not text.strip():
        raise C.ComfyError("param", "缺少要合成的文本（位置参数 TEXT 或 --text-file）")

    params = {"text": text}
    if args.voice:
        params["voice"] = args.voice
    if args.rate is not None:
        params["rate"] = args.rate
    if args.volume is not None:
        params["volume"] = args.volume
    if args.prefix:
        params["filename_prefix"] = args.prefix

    args.set = ["%s=%s" % (k, v) for k, v in params.items()]
    args.input_image = None
    args.dry_run = getattr(args, "dry_run", False)
    args.no_wait = getattr(args, "no_wait", False)
    args.no_download = getattr(args, "no_download", False)
    args.seed = None
    outdir = args.out or os.path.join(os.getcwd(), "comfy-out")
    return _run_workflow(args, cfg, args.workflow, C.parse_kv(args.set), outdir, title="文生语音")


# ------------------------------------------------------------------ dub
def cmd_dub(args, cfg):
    """拟真人配音：Ming-3.0-tts 0.5B（内置音色 / 真人音色克隆）。"""
    text = args.text
    if args.text_file:
        with open(args.text_file, "r", encoding="utf-8-sig") as f:
            text = f.read()
    if not text or not text.strip():
        raise C.ComfyError("param", "缺少要配音的文本（位置参数 TEXT 或 --text-file）")

    ref_text = args.ref_text
    if args.ref_text_file:
        with open(args.ref_text_file, "r", encoding="utf-8-sig") as f:
            ref_text = f.read().strip()

    workflow = args.workflow
    if not workflow:
        workflow = "ming_clone" if args.ref_audio else "ming"

    params = {"text": text}
    if args.voice:
        params["voice"] = args.voice
    if ref_text:
        params["reference_text"] = ref_text
    if args.language:
        params["language"] = args.language
    if args.model:
        params["model"] = args.model
    if args.prefix:
        params["filename_prefix"] = args.prefix
    if args.cfg is not None:
        params["cfg"] = args.cfg
    if args.flow_steps is not None:
        params["flow_steps"] = args.flow_steps
    if args.max_steps is not None:
        params["max_steps"] = args.max_steps
    if args.temperature is not None:
        params["temperature"] = args.temperature

    args.set = ["%s=%s" % (k, v) for k, v in params.items()]
    args.input_image = None
    args.input_audio = args.ref_audio
    args.dry_run = getattr(args, "dry_run", False)
    args.no_wait = getattr(args, "no_wait", False)
    args.no_download = getattr(args, "no_download", False)
    outdir = args.out or os.path.join(os.getcwd(), "comfy-out")
    return _run_workflow(args, cfg, workflow, C.parse_kv(args.set), outdir, title="拟真人配音")


# ------------------------------------------------------------------ register
def cmd_register(args, cfg):
    reg = C.load_registry()
    data, path = C.load_workflow_source(args.source, cfg)
    detected, warnings = [], []
    try:
        server = C.Server(cfg, args.base_url)
        server.resolve()
        prompt, warnings = C.ui_to_api(data, server.object_info())
        detected = sorted({k for n in prompt.values() for k in (n.get("inputs") or {})})
    except C.ComfyError as exc:
        warnings.append("未能推断可用输入（%s），仍会登记" % exc.message)

    entry = {
        "title": args.title or "",
        "source": args.source,
        "params": {},
        "defaults": {},
    }
    for raw in args.param or []:
        name, _, bind = raw.partition("=")
        if "@" not in bind and "." not in bind:
            raise C.ComfyError("param", "参数绑定格式：name=<node_id>.<input> 或 name=<node>@<title>.<input>")
        if "@" in bind:
            node, _, inp = bind.partition("@")
            title, _, inp2 = inp.rpartition(".")
            entry["params"][name] = {"node_title": title, "input": inp2}
        else:
            node, _, inp = bind.rpartition(".")
            entry["params"][name] = {"node": node, "input": inp}
    for raw in args.default or []:
        k, _, v = raw.partition("=")
        entry["defaults"][k] = C._coerce(v)

    reg["workflows"][args.alias] = entry
    written = C.save_registry(reg)
    result = {"ok": True, "alias": args.alias, "registry": written, "entry": entry,
              "auto_detectable_inputs": detected, "warnings": warnings}
    if args.json:
        _print(result)
    else:
        print("已登记 %s → %s" % (args.alias, args.source))
        if detected:
            print("可自动绑定输入：%s" % ", ".join(detected[:30]))
        if warnings:
            print("警告：%s" % "；".join(warnings))
        print("建议：给关键参数显式绑定，例如 --param text=1.text")
    return C.EXIT_OK


# ------------------------------------------------------------------ nodes
def cmd_nodes(args, cfg):
    server = C.Server(cfg, args.base_url)
    server.resolve()
    oi = server.object_info()
    rows = []
    for cls, info in oi.items():
        name = (info.get("name") or cls) or cls
        cat = info.get("category") or ""
        q = (args.query or "").lower()
        if q and q not in cls.lower() and q not in name.lower() and q not in cat.lower():
            continue
        rows.append({"class_type": cls, "display_name": name, "category": cat,
                     "outputs": info.get("output") or []})
    rows.sort(key=lambda r: (r["category"], r["class_type"]))
    if args.json:
        _print({"ok": True, "count": len(rows), "nodes": rows})
    else:
        for r in rows:
            print("%-40s %-28s %s" % (r["class_type"], r["display_name"][:28], r["category"]))
        print("共 %d 个节点类" % len(rows))
    return C.EXIT_OK


def cmd_interrupt(args, cfg):
    server = C.Server(cfg, args.base_url)
    server.resolve()
    server.interrupt()
    print("已发送中断请求")
    return C.EXIT_OK


# ------------------------------------------------------------------ main
def build_parser():
    ap = argparse.ArgumentParser(prog="comfy.py", description="ComfyUI 本地工作流调用工具")
    ap.add_argument("--config", default=None, help="指定 config.json 路径")
    ap.add_argument("--base-url", default=None, help="覆盖服务地址，如 http://127.0.0.1:8188")
    ap.add_argument("--json", action="store_true", help="输出 JSON（便于其他程序解析）")

    # 让 --json/--config/--base-url 既能写在子命令前，也能写在子命令后
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=argparse.SUPPRESS)
    common.add_argument("--base-url", default=argparse.SUPPRESS)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS)

    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="体检", parents=[common])
    d.add_argument("--write-config", action="store_true", help="把当前生效配置写入 skill 的 config.json")
    d.set_defaults(fn=cmd_doctor)

    w = sub.add_parser("wait", help="等待手动启动的 ComfyUI 就绪（不启动服务）", parents=[common])
    w.add_argument("--timeout", type=int, default=180)
    w.add_argument("--interval", type=float, default=3.0)
    w.set_defaults(fn=cmd_wait)

    l = sub.add_parser("list", help="列出工作流", parents=[common])
    l.add_argument("--all", action="store_true", help="同时扫描 workflows_dir 下的未登记工作流")
    l.add_argument("--filter", help="关键词过滤")
    l.set_defaults(fn=cmd_list)

    de = sub.add_parser("describe", help="查看工作流结构", parents=[common])
    de.add_argument("name", help="别名 / 文件名 / 路径")
    de.add_argument("--schema", help="离线核对：用保存的 object_info JSON 代替实时查询")
    de.set_defaults(fn=cmd_describe)

    r = sub.add_parser("run", help="执行工作流", parents=[common])
    r.add_argument("name", help="别名 / 文件名 / 路径")
    r.add_argument("-p", "--set", action="append", metavar="KEY=VALUE", help="参数，可重复")
    r.add_argument("--seed", type=int, help="覆盖所有 seed/noise_seed")
    r.add_argument("--input-image", help="上传本地图片并绑定到 image 输入")
    r.add_argument("--input-audio", help="上传本地音频并绑定到 audio 输入（LoadAudio 参考音色）")
    r.add_argument("--out", help="产物目录（默认 ./comfy-out）")
    r.add_argument("--timeout", type=int, default=None, help="等待上限秒数")
    r.add_argument("--dry-run", action="store_true", help="只打印 API 工作流，不提交")
    r.add_argument("--no-wait", action="store_true", help="提交后立即返回 prompt_id")
    r.add_argument("--no-download", action="store_true", help="只返回远端文件名，不下载")
    r.add_argument("--schema", help="离线核对：用保存的 object_info JSON 代替实时查询（仅配合 --dry-run）")
    r.set_defaults(fn=cmd_run)

    t = sub.add_parser("tts", help="文本转语音", parents=[common])
    t.add_argument("text", nargs="?", help="要合成的文本")
    t.add_argument("--text-file", help="从 UTF-8 文本文件读取")
    t.add_argument("--workflow", default="tts", help="TTS 工作流别名（默认 tts）")
    t.add_argument("--voice", help="SAPI 语音名，如 Microsoft Huihui Desktop；默认 auto（优先 zh-CN）")
    t.add_argument("--rate", type=int, help="-10..10 语速")
    t.add_argument("--volume", type=int, help="0..100 音量")
    t.add_argument("--prefix", help="ComfyUI 输出前缀，默认 audio/tts")
    t.add_argument("--out", help="产物目录（默认 ./comfy-out）")
    t.add_argument("--timeout", type=int, default=600)
    t.add_argument("--dry-run", action="store_true")
    t.add_argument("--no-wait", action="store_true")
    t.add_argument("--no-download", action="store_true")
    t.set_defaults(fn=cmd_tts)

    d = sub.add_parser("dub", help="拟真人配音（Ming-3.0-tts 0.5B）", parents=[common])
    d.add_argument("text", nargs="?", help="要配音的文本")
    d.add_argument("--text-file", help="从 UTF-8 文本文件读取配音文本")
    d.add_argument("--workflow", default=None,
                   help="工作流别名：ming（内置音色）或 ming_clone（音色克隆）；不写时按是否给 --ref-audio 自动选")
    d.add_argument("--voice", help="内置音色名（如 灵小安 / 灵朵儿 / 花小呗），仅 ming 有效")
    d.add_argument("--language", help="输出语言 Chinese/English/...，仅 ming_clone 有效（默认 Chinese）")
    d.add_argument("--ref-audio", help="参考音色音频（真人样本，10-30s），给了就走音色克隆（ming_clone）")
    d.add_argument("--ref-text", help="参考音频的逐字转写（不是要合成的新句子）")
    d.add_argument("--ref-text-file", help="从文件读取参考音频的逐字转写")
    d.add_argument("--model", help="模型目录：Ming-3.0-tts-0.5b（默认）或 Ming-3.0-tts-0.5b-int8-convrot")
    d.add_argument("--cfg", type=float, help="引导强度（默认 2.0）")
    d.add_argument("--flow-steps", type=int, help="每块 flow 求解步数（默认 10）")
    d.add_argument("--max-steps", type=int, help="每段最大音频块数（约 80ms/块，默认 250≈20s）")
    d.add_argument("--temperature", type=float, help="额外随机噪声，0 最稳（默认 0）")
    d.add_argument("--seed", type=int, help="随机种子（默认 42）")
    d.add_argument("--prefix", help="ComfyUI 输出前缀，默认 ming_tts/dub")
    d.add_argument("--out", help="产物目录（默认 ./comfy-out）")
    d.add_argument("--timeout", type=int, default=1800)
    d.add_argument("--dry-run", action="store_true")
    d.add_argument("--no-wait", action="store_true")
    d.add_argument("--no-download", action="store_true")
    d.set_defaults(fn=cmd_dub, input_image=None, input_audio=None)

    g = sub.add_parser("register", help="登记工作流别名", parents=[common])
    g.add_argument("alias")
    g.add_argument("--source", required=True, help="user:<相对路径> / api:<相对路径> / file:<绝对路径>")
    g.add_argument("--title", help="中文说明")
    g.add_argument("--param", action="append", metavar="NAME=NODE.INPUT",
                   help="显式参数绑定，可重复；也可 NAME=NODE@标题.INPUT")
    g.add_argument("--default", action="append", metavar="NAME=VALUE", help="默认参数值，可重复")
    g.set_defaults(fn=cmd_register)

    n = sub.add_parser("nodes", help="查询已安装节点类", parents=[common])
    n.add_argument("query", nargs="?")
    n.set_defaults(fn=cmd_nodes)

    i = sub.add_parser("interrupt", help="中断当前执行", parents=[common])
    i.set_defaults(fn=cmd_interrupt)
    return ap


def main(argv=None):
    _utf8_stdout()
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.cmd == "run" and args.timeout is None:
        args.timeout = None
    try:
        cfg = C.load_config(config_path=args.config)
        if args.cmd == "run" and not args.timeout:
            args.timeout = cfg["timeout_job"]
        return args.fn(args, cfg)
    except C.ComfyError as exc:
        return _fail(exc, getattr(args, "json", False))
    except KeyboardInterrupt:
        print("已取消", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
