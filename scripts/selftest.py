#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""comfyui-local skill 自检。

分三层，任何一层失败都会给出明确原因：
  L1 离线结构检查：registry / 工作流文件 / 配置路径 / CLI 冒烟
  L2 离线转换检查：用合成 object_info 把 TTS 的 UI 工作流转成 API 图，校验参数绑定
  L3 本机 TTS 引擎检查：直接调用 SAPI 脚本生成 wav，验证离线可发声

  --live  额外检查：连接已手动启动的 ComfyUI，比对真实 object_info 并执行一次 TTS

用法：
    python scripts/selftest.py
    python scripts/selftest.py --live
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comfy_client as C  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
COMFY = os.path.join(SKILL, "scripts", "comfy.py")

RESULTS = []


def check(name, fn):
    try:
        detail = fn()
        RESULTS.append((True, name, detail or ""))
        return True
    except Exception as exc:  # noqa: BLE001
        RESULTS.append((False, name, "%s: %s" % (type(exc).__name__, exc)))
        return False


# ---------------------------------------------------------------- L2 用的合成 schema
def synthetic_schema():
    """按 ComfyUI /object_info 的真实结构描述本 skill 依赖的两个节点。"""
    return {
        "LocalTTS_SAPI": {
            "input": {
                "required": {
                    "text": ["STRING", {"multiline": True}],
                    "voice": [["auto", "Microsoft Huihui Desktop"], {}],
                    "rate": ["INT", {"default": 0, "min": -10, "max": 10}],
                    "volume": ["INT", {"default": 100, "min": 0, "max": 100}],
                }
            },
            "output": ["AUDIO"],
            "output_name": ["audio"],
            "name": "LocalTTS_SAPI",
            "category": "audio/tts",
            "output_node": False,
        },
        "SaveAudioAdvanced": {
            "input": {
                "required": {
                    "audio": ["AUDIO", {}],
                    "filename_prefix": ["STRING", {"default": "audio/ComfyUI"}],
                    # 0.38+ 核心节点用动态下拉标记，容易被误判成连线输入（真实踩过的坑）
                    "format": ["COMFY_DYNAMICCOMBO_V3", {
                        "options": [{"key": "flac", "inputs": {"required": {}}},
                                    {"key": "mp3", "inputs": {"required": {}}},
                                    {"key": "opus", "inputs": {"required": {}}}]
                    }],
                }
            },
            "output": ["AUDIO"],
            "output_name": ["audio"],
            "name": "SaveAudioAdvanced",
            "category": "audio",
            "output_node": True,
        },
        # 转换器还需容忍 seed + control_after_generate 这类常见形态
        "ImageScale": {
            "input": {"required": {
                "image": ["IMAGE", {}],
                "upscale_method": [["nearest-exact", "bilinear"], {}],
                "width": ["INT", {}],
                "height": ["INT", {}],
                "crop": [["disabled", "center"], {}],
            }},
            "output": ["IMAGE"], "name": "ImageScale", "category": "image/upscaling",
        },
        "KSampler": {
            "input": {
                "required": {
                    "model": ["MODEL", {}],
                    "seed": ["INT", {"default": 0, "control_after_generate": True}],
                    "steps": ["INT", {"default": 20}],
                    "cfg": ["FLOAT", {"default": 8.0}],
                    "sampler_name": [["euler", "dpmpp_2m"], {}],
                    "scheduler": [["normal", "simple"], {}],
                    "positive": ["CONDITIONING", {}],
                    "negative": ["CONDITIONING", {}],
                    "latent_image": ["LATENT", {}],
                    "denoise": ["FLOAT", {"default": 1.0}],
                }
            },
            "output": ["LATENT"], "name": "KSampler", "category": "sampling",
        },
        "CheckpointLoaderSimple": {
            "input": {"required": {"ckpt_name": [["a.safetensors"], {}]}},
            "output": ["MODEL", "CLIP", "VAE"], "name": "CheckpointLoaderSimple", "category": "loaders",
        },
        "CLIPTextEncode": {
            "input": {"required": {"text": ["STRING", {"multiline": True}],
                                   "clip": ["CLIP", {}]}},
            "output": ["CONDITIONING"], "name": "CLIPTextEncode", "category": "conditioning",
        },
        "EmptyLatentImage": {
            "input": {"required": {"width": ["INT", {}], "height": ["INT", {}], "batch_size": ["INT", {}]}},
            "output": ["LATENT"], "name": "EmptyLatentImage", "category": "latent",
        },
        "VAEDecode": {
            "input": {"required": {"samples": ["LATENT", {}], "vae": ["VAE", {}]}},
            "output": ["IMAGE"], "name": "VAEDecode", "category": "latent",
        },
        "SaveImage": {
            "input": {"required": {"images": ["IMAGE", {}], "filename_prefix": ["STRING", {}]}},
            "output": [], "name": "SaveImage", "category": "image", "output_node": True,
        },
        "Reroute": {"input": {"required": {}}, "output": ["*"], "name": "Reroute", "category": "utils"},
    }


def sampler_ui_workflow():
    """带旁通(mode=4)、静音(mode=2)、Reroute、seed 控制值的 UI 工作流，用来压力测试转换器。"""
    return {
        "nodes": [
            {"id": 1, "type": "CheckpointLoaderSimple", "mode": 0, "inputs": [],
             "outputs": [{"name": "MODEL", "type": "MODEL", "links": [1]},
                         {"name": "CLIP", "type": "CLIP", "links": [2]},
                         {"name": "VAE", "type": "VAE", "links": [3]}],
             "widgets_values": ["a.safetensors"]},
            {"id": 2, "type": "CLIPTextEncode", "mode": 0,
             "inputs": [{"name": "clip", "type": "CLIP", "link": 2}],
             "outputs": [{"name": "CONDITIONING", "type": "CONDITIONING", "links": [4]}],
             "title": "正向提示词", "widgets_values": ["一只猫"]},
            {"id": 3, "type": "CLIPTextEncode", "mode": 0,
             "inputs": [{"name": "clip", "type": "CLIP", "link": 2}],
             "outputs": [{"name": "CONDITIONING", "type": "CONDITIONING", "links": [5]}],
             "widgets_values": ["负向"]},
            {"id": 10, "type": "CLIPTextEncode", "mode": 2,
             "inputs": [{"name": "clip", "type": "CLIP", "link": 2}],
             "outputs": [{"name": "CONDITIONING", "type": "CONDITIONING", "links": None}],
             "widgets_values": ["被静音的节点"]},
            {"id": 4, "type": "Reroute", "mode": 0,
             "inputs": [{"name": "", "type": "*", "link": 4}],
             "outputs": [{"name": "", "type": "CONDITIONING", "links": [6]}]},
            {"id": 5, "type": "KSampler", "mode": 0,
             "inputs": [{"name": "model", "type": "MODEL", "link": 1},
                        {"name": "positive", "type": "CONDITIONING", "link": 6},
                        {"name": "negative", "type": "CONDITIONING", "link": 5},
                        {"name": "latent_image", "type": "LATENT", "link": 7}],
             "outputs": [{"name": "LATENT", "type": "LATENT", "links": [8]}],
             "widgets_values": [12345, "randomize", 20, 8.0, "euler", "normal", 1.0]},
            {"id": 6, "type": "EmptyLatentImage", "mode": 0, "inputs": [],
             "outputs": [{"name": "LATENT", "type": "LATENT", "links": [7]}],
             "widgets_values": [1024, 1024, 1]},
            {"id": 7, "type": "VAEDecode", "mode": 0,
             "inputs": [{"name": "samples", "type": "LATENT", "link": 8},
                        {"name": "vae", "type": "VAE", "link": 3}],
             "outputs": [{"name": "IMAGE", "type": "IMAGE", "links": [9]}]},
            {"id": 9, "type": "ImageScale", "mode": 4,
             "inputs": [{"name": "image", "type": "IMAGE", "link": 9}],
             "outputs": [{"name": "IMAGE", "type": "IMAGE", "links": [10]}],
             "widgets_values": ["nearest-exact", 1024, 1024, "disabled"]},
            {"id": 8, "type": "SaveImage", "mode": 0,
             "inputs": [{"name": "images", "type": "IMAGE", "link": 10}],
             "outputs": [], "widgets_values": ["test"]},
        ],
        "links": [
            [1, 1, 0, 5, 0, "MODEL"],
            [2, 1, 1, 2, 0, "CLIP"],
            [3, 1, 2, 7, 1, "VAE"],
            [4, 2, 0, 4, 0, "CONDITIONING"],
            [5, 3, 0, 5, 2, "CONDITIONING"],
            [6, 4, 0, 5, 1, "CONDITIONING"],
            [7, 6, 0, 5, 3, "LATENT"],
            [8, 5, 0, 7, 0, "LATENT"],
            [9, 7, 0, 9, 0, "IMAGE"],
            [10, 9, 0, 8, 0, "IMAGE"],
        ],
        "version": 0.4,
    }


# ---------------------------------------------------------------- 各层检查
def l1_offline(cfg):
    def _registry():
        reg = C.load_registry()
        assert "tts" in reg["workflows"], "registry 里没有 tts 别名"
        for alias in ("ming", "ming_clone"):
            assert alias in reg["workflows"], "registry 里没有 %s 别名" % alias
        return "别名：%s" % ", ".join(reg["workflows"])

    def _dub_sources():
        out = []
        for alias in ("ming", "ming_clone"):
            ref, data = C.resolve_workflow(alias, cfg)
            assert C.is_api_format(data), "%s 不是 API 格式" % alias
            assert ref["source"].startswith("api:"), ref["source"]
            out.append("%s(%d 节点)" % (alias, len(data)))
        return "，".join(out)

    def _image_sources():
        out = []
        for alias in ("t2i", "i2i"):
            ref, data = C.resolve_workflow(alias, cfg)
            assert C.is_api_format(data), "%s 不是 API 格式" % alias
            assert ref["source"].startswith("api:"), ref["source"]
            out.append("%s(%d 节点)" % (alias, len(data)))
        return "，".join(out)

    def _workflows():
        ref, data = C.resolve_workflow("tts", cfg)
        assert ref["source"].startswith("user:"), ref["source"]
        return ref["path"]

    def _paths():
        assert os.path.isdir(cfg["workflows_dir"]), cfg["workflows_dir"]
        assert os.path.isfile(os.path.join(cfg["workflows_dir"], "tts_zh_sapi.json"))
        return cfg["workflows_dir"]

    def _cli_list():
        out = _run_cli(["list", "--json", "--all"])
        data = json.loads(out)
        assert data["ok"], data
        assert any(r["alias"] == "tts" for r in data["workflows"])
        return "%d 条工作流" % data["count"]

    def _discover():
        found = C.discover_workflows(cfg)
        assert found, "workflows_dir 下没有可发现的工作流"
        return "%d 个工作流（含已登记）" % len(found)

    ok = True
    for name, fn in (("registry", _registry), ("resolve tts", _workflows),
                     ("配音工作流", _dub_sources), ("图像工作流", _image_sources),
                     ("paths", _paths), ("cli list", _cli_list), ("discover", _discover)):
        ok = check("L1 " + name, fn) and ok
    return ok


def l2_convert(cfg):
    schema = synthetic_schema()

    def _tts_convert():
        ref, data = C.resolve_workflow("tts", cfg)
        prompt, warnings = C.ui_to_api(data, schema)
        assert set(prompt) == {"1", "2"}, prompt
        assert prompt["1"]["class_type"] == "LocalTTS_SAPI"
        assert prompt["1"]["inputs"]["text"].startswith("你好")
        assert prompt["2"]["inputs"]["audio"] == ["1", 0], prompt["2"]["inputs"]
        assert prompt["2"]["inputs"]["format"] == "flac"
        assert not warnings, warnings
        return "2 节点，audio 连线正确"

    def _tts_bind():
        ref, data = C.resolve_workflow("tts", cfg)
        prompt, _ = C.ui_to_api(data, schema)
        applied, warnings = C.bind_params(prompt, ref, {"text": "测试文本", "rate": "3"})
        assert prompt["1"]["inputs"]["text"] == "测试文本"
        assert prompt["1"]["inputs"]["rate"] == 3, prompt["1"]["inputs"]
        assert prompt["1"]["inputs"]["voice"] == "auto"
        assert not warnings, warnings
        return json.dumps(applied, ensure_ascii=False)[:80]

    def _tts_bad_param():
        ref, data = C.resolve_workflow("tts", cfg)
        prompt, _ = C.ui_to_api(data, schema)
        try:
            C.bind_params(prompt, ref, {"nope": 1})
        except C.ComfyError as exc:
            assert exc.stage == "param", exc.stage
            return "未知名参数被拦截，退出码 %d" % exc.exit_code
        raise AssertionError("未知参数没有报错")

    def _convert_hard():
        prompt, warnings = C.ui_to_api(sampler_ui_workflow(), schema)
        # 静音节点 10 与旁通节点 9 被移除；Reroute(4) 被穿透
        assert "10" not in prompt, prompt.keys()
        assert "9" not in prompt and "4" not in prompt, prompt.keys()
        assert prompt["5"]["inputs"]["positive"] == ["2", 0], prompt["5"]["inputs"]["positive"]
        # 旁通 ImageScale 后 IMAGE 直连上游 VAEDecode(7)
        assert prompt["8"]["inputs"]["images"] == ["7", 0], prompt["8"]["inputs"]["images"]
        # seed 之后的 "randomize" 控制值不能吃掉 steps
        assert prompt["5"]["inputs"]["seed"] == 12345
        assert prompt["5"]["inputs"]["steps"] == 20, prompt["5"]["inputs"]
        assert prompt["5"]["inputs"]["sampler_name"] == "euler"
        assert warnings == [], warnings
        return "静音/旁通/Reroute/seed 控制值均正确处理"

    def _cli_dry_run():
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(schema, f, ensure_ascii=False)
            path = f.name
        try:
            out = _run_cli(["run", "tts", "--dry-run", "--schema", path, "--json",
                            "-p", "text=命令行文本", "-p", "volume=80"])
            data = json.loads(out)
            assert data["ok"], data
            assert data["prompt"]["1"]["inputs"]["text"] == "命令行文本"
            assert data["prompt"]["1"]["inputs"]["volume"] == 80
            return "CLI 转换 + 绑定 OK"
        finally:
            os.unlink(path)

    def _cli_describe():
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(schema, f, ensure_ascii=False)
            path = f.name
        try:
            data = json.loads(_run_cli(["describe", "tts", "--schema", path, "--json"]))
            assert data["ok"] and data["node_count"] == 2
            assert set(data["declared_params"]) == {"text", "voice", "rate", "volume", "filename_prefix"}
            return "describe 输出 %d 节点" % data["node_count"]
        finally:
            os.unlink(path)

    def _ming_bind():
        ref, data = C.resolve_workflow("ming", cfg)
        prompt, _ = C.ui_to_api(data, {})
        assert prompt["2"]["inputs"]["task"] == "ip", prompt["2"]["inputs"]
        applied, warnings = C.bind_params(prompt, ref, {"text": "自检文本", "voice": "灵朵儿", "seed": "7"})
        # Ming 的 DynamicCombo 子输入在 API 里是扁平点号键
        assert prompt["2"]["inputs"]["task.voice"] == "灵朵儿", prompt["2"]["inputs"]
        assert prompt["2"]["inputs"]["seed"] == 7
        assert not warnings, warnings
        return json.dumps(applied["voice"], ensure_ascii=False)

    def _ming_clone_bind():
        ref, data = C.resolve_workflow("ming_clone", cfg)
        prompt, _ = C.ui_to_api(data, {})
        applied, warnings = C.bind_params(prompt, ref, {
            "text": "要合成的新句子", "reference_text": "参考音频的原话", "audio": "ref.wav"})
        assert prompt["3"]["inputs"]["task.reference_text"] == "参考音频的原话", prompt["3"]["inputs"]
        assert prompt["3"]["inputs"]["task.language"] == "Chinese"
        assert prompt["1"]["inputs"]["audio"] == "ref.wav"
        assert prompt["3"]["inputs"]["task.reference_audio"] == ["1", 0]
        assert not warnings, warnings
        return "点号键 + 音频连线 OK"

    def _t2i_bind():
        ref, data = C.resolve_workflow("t2i", cfg)
        prompt, _ = C.ui_to_api(data, {})
        applied, warnings = C.bind_params(prompt, ref, {
            "prompt": "自检文生图", "width": "512", "height": "384",
            "seed": "7", "steps": "12"})
        assert prompt["4"]["inputs"]["prompt"] == "自检文生图", prompt["4"]["inputs"]
        assert prompt["5"]["inputs"]["width"] == 512, prompt["5"]["inputs"]
        assert prompt["5"]["inputs"]["height"] == 384
        assert prompt["6"]["inputs"]["seed"] == 7
        assert prompt["6"]["inputs"]["steps"] == 12
        # SaveImageAdvanced 的动态下拉子输入在 API 里是扁平点号键
        assert prompt["8"]["inputs"]["format.bit_depth"] == "8-bit", prompt["8"]["inputs"]
        assert not warnings, warnings
        return "prompt/尺寸/seed/点号键 OK"

    def _i2i_bind():
        ref, data = C.resolve_workflow("i2i", cfg)
        prompt, _ = C.ui_to_api(data, {})
        applied, warnings = C.bind_params(prompt, ref, {"prompt": "改成水彩", "image": "photo.png"})
        assert prompt["4"]["inputs"]["image"] == "photo.png", prompt["4"]["inputs"]
        # 参考图连线到 TextEncode 的 autogrow 输入（扁平点号键）
        assert prompt["5"]["inputs"]["images.image_1"] == ["4", 0], prompt["5"]["inputs"]
        # 采样 latent 取自参考图尺寸，而不是另一张空画布
        assert prompt["6"]["inputs"]["latent_image"] == ["5", 2], prompt["6"]["inputs"]
        assert not warnings, warnings
        return "参考图上传位 + 参考图 latent OK"

    ok = True
    for name, fn in (("tts 转换", _tts_convert), ("参数绑定", _tts_bind),
                     ("未知参数报错", _tts_bad_param), ("复杂图转换", _convert_hard),
                     ("CLI dry-run", _cli_dry_run), ("CLI describe", _cli_describe),
                     ("Ming 内置音色绑定", _ming_bind), ("Ming 克隆绑定", _ming_clone_bind),
                     ("Qwen 文生图绑定", _t2i_bind), ("Qwen 图生图绑定", _i2i_bind)):
        ok = check("L2 " + name, fn) and ok
    return ok


def l3_tts(cfg):
    if os.name != "nt":
        # SAPI5 与 powershell.exe 只在 Windows 存在；其余平台的语音能力走 ming / cosyvoice3
        RESULTS.append((True, "L3 本机 TTS",
                        "跳过：Windows SAPI 专属（当前平台 %s）" % sys.platform))
        return True

    node_dir = os.path.join(cfg["comfyui_root"], "custom_nodes", "ComfyUI-LocalTTS-SAPI")
    ps1 = os.path.join(node_dir, "sapi_tts.ps1")

    def _files():
        assert os.path.isfile(ps1), ps1
        assert os.path.isfile(os.path.join(node_dir, "__init__.py"))
        return node_dir

    def _synth():
        with tempfile.TemporaryDirectory() as tmp:
            txt = os.path.join(tmp, "in.txt")
            wav = os.path.join(tmp, "out.wav")
            with open(txt, "w", encoding="utf-8") as f:
                f.write("自检：这是一段本机离线语音合成测试。")
            creation = 0x08000000 if os.name == "nt" else 0
            proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive",
                                   "-ExecutionPolicy", "Bypass", "-File", ps1,
                                   "-TextFile", txt, "-OutFile", wav, "-Voice", "auto",
                                   "-Rate", "0", "-Volume", "100", "-SampleRate", "16000"],
                                  capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=180, creationflags=creation)
            assert proc.returncode == 0, (proc.stderr or proc.stdout)[:400]
            assert os.path.getsize(wav) > 2000, "wav 太小"
            with wave.open(wav, "rb") as w:
                dur = w.getnframes() / float(w.getframerate())
                rate = w.getframerate()
            assert dur > 0.5, "时长异常：%.2fs" % dur
            return "%.2fs / %dHz / %.1fKB" % (dur, rate, os.path.getsize(wav) / 1024.0)

    ok = True
    for name, fn in (("节点文件", _files), ("SAPI 合成", _synth)):
        ok = check("L3 " + name, fn) and ok
    return ok


def l4_live(cfg, base_url=None):
    server = C.Server(cfg, base_url)
    try:
        base = server.resolve()
    except C.ComfyError as exc:
        check("L4 连接服务", lambda: (_ for _ in ()).throw(AssertionError(exc.message)))
        return False

    def _connect():
        stats = server.system_stats()
        return "%s ｜ ComfyUI %s" % (base, (stats.get("system") or {}).get("comfyui_version"))

    def _node_present():
        oi = server.object_info()
        assert "LocalTTS_SAPI" in oi, "LocalTTS_SAPI 未加载"
        return "共 %d 个节点类" % len(oi)

    def _schema_drift():
        oi = server.object_info("LocalTTS_SAPI")
        real = set((oi["LocalTTS_SAPI"]["input"].get("required") or {}))
        fake = set(synthetic_schema()["LocalTTS_SAPI"]["input"]["required"])
        assert real == fake, "节点输入与合成 schema 不一致：%s vs %s" % (sorted(real), sorted(fake))
        return "输入一致：%s" % ", ".join(sorted(real))

    def _run_tts():
        with tempfile.TemporaryDirectory() as tmp:
            out = _run_cli(["tts", "联调测试：ComfyUI 文生语音。", "--out", tmp, "--json"],
                           base_url=base)
            data = json.loads(out)
            assert data["ok"], data
            files = [f for f in data["files"] if f["kind"] == "audio"]
            assert files, data["files"]
            assert files[0]["bytes"] > 2000
            return "%s (%.1fKB, %.1fs)" % (os.path.basename(files[0]["path"]),
                                           files[0]["bytes"] / 1024.0, data["elapsed_sec"])

    def _ming_nodes():
        oi = server.object_info()
        for cls in ("MingLoadModel", "MingGenerate"):
            assert cls in oi, "%s 未加载（装完自定义节点需重启 ComfyUI）" % cls
        opts = ((oi["MingLoadModel"]["input"]["required"].get("model") or [None, {}])[1] or {}).get("options") or []
        assert any(str(o).startswith("Ming-3.0-tts-0.5b") for o in opts), "模型目录未就位：%s" % opts
        return "Ming 节点已加载，模型 %s" % ", ".join(opts[:2])

    def _run_dub():
        with tempfile.TemporaryDirectory() as tmp:
            out = _run_cli(["dub", "自检配音：小小的船。", "--out", tmp, "--json"], base_url=base)
            data = json.loads(out)
            assert data["ok"], data
            files = [f for f in data["files"] if f["kind"] == "audio"]
            assert files and files[0]["bytes"] > 5000, data["files"]
            return "%s (%.1fKB, %.1fs)" % (os.path.basename(files[0]["path"]),
                                           files[0]["bytes"] / 1024.0, data["elapsed_sec"])

    def _qwen_nodes():
        oi = server.object_info()
        assert "TextEncodeQwenImage21" in oi, "TextEncodeQwenImage21 未加载（需 ComfyUI 0.4x+）"
        cands = [c for c in ((oi["UNETLoader"]["input"]["required"].get("unet_name") or [None])[0] or [])
                 if "qwen_image_2.1" in str(c)]
        assert cands, "未发现 qwen_image_2.1 扩散模型权重"
        vaes = [c for c in ((oi["VAELoader"]["input"]["required"].get("vae_name") or [None])[0] or [])
                if "qwen_image_2.1_vae" in str(c)]
        assert vaes, "未发现 qwen_image_2.1 VAE"
        return "模型 %s ｜ VAE %s" % (", ".join(cands[:2]), ", ".join(vaes[:1]))

    def _run_t2i():
        with tempfile.TemporaryDirectory() as tmp:
            out = _run_cli(["t2i", "自检文生图：一只橘猫坐在窗台上", "--width", "256",
                            "--height", "256", "--steps", "4", "--out", tmp, "--json"], base_url=base)
            data = json.loads(out)
            assert data["ok"], data
            files = [f for f in data["files"] if f["kind"] in ("images", "image")]
            assert files and files[0]["bytes"] > 1000, data["files"]
            return "%s (%.1fKB, %.1fs)" % (os.path.basename(files[0]["path"]),
                                           files[0]["bytes"] / 1024.0, data["elapsed_sec"])

    def _run_i2i():
        with tempfile.TemporaryDirectory() as tmp:
            first = json.loads(_run_cli(["t2i", "自检图生图的输入底图：窗台上的橘猫", "--width", "256",
                                         "--height", "256", "--steps", "4", "--out", tmp, "--json"],
                                        base_url=base))
            assert first["ok"], first
            src = [f for f in first["files"] if f["kind"] in ("images", "image")][0]["path"]
            second = json.loads(_run_cli(["i2i", "改成铅笔素描风格", "--image", src,
                                          "--resolution", "256", "--steps", "4",
                                          "--out", tmp, "--json"], base_url=base))
            assert second["ok"], second
            files = [f for f in second["files"] if f["kind"] in ("images", "image")]
            assert files and files[0]["bytes"] > 1000, second["files"]
            return "%s (%.1fKB, %.1fs)" % (os.path.basename(files[0]["path"]),
                                           files[0]["bytes"] / 1024.0, second["elapsed_sec"])

    def _nodes_total():
        oi = server.object_info()
        assert oi, "object_info 为空"
        return "共 %d 个节点类" % len(oi)

    plan = [("连接服务", _connect)]
    if os.name == "nt":
        plan += [("TTS 节点", _node_present), ("schema 一致", _schema_drift), ("执行 TTS", _run_tts)]
    else:
        plan += [("节点总览", _nodes_total)]
        RESULTS.append((True, "L4 TTS 链路",
                        "跳过：Windows SAPI 专属（当前平台 %s）" % sys.platform))
    plan += [("Ming 节点", _ming_nodes), ("执行配音", _run_dub),
             ("Qwen 节点", _qwen_nodes), ("执行文生图", _run_t2i),
             ("执行图生图", _run_i2i)]

    ok = True
    for name, fn in plan:
        ok = check("L4 " + name, fn) and ok
    return ok


# ---------------------------------------------------------------- 工具
def _run_cli(args, base_url=None):
    cmd = [sys.executable, COMFY] + list(args)
    if base_url:
        cmd += ["--base-url", base_url]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise AssertionError("CLI 退出码 %d：%s" % (proc.returncode, (proc.stderr or proc.stdout)[:600]))
    return proc.stdout


def main():
    ap = argparse.ArgumentParser(description="comfyui-local skill 自检")
    ap.add_argument("--live", action="store_true", help="额外连接已启动的 ComfyUI 做联调")
    ap.add_argument("--base-url")
    args = ap.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    cfg = C.load_config()
    t0 = time.time()
    ok = l1_offline(cfg)
    ok = l2_convert(cfg) and ok
    ok = l3_tts(cfg) and ok
    if args.live:
        ok = l4_live(cfg, args.base_url) and ok

    print("comfyui-local 自检 %s（%.1fs）" % ("通过" if ok else "失败", time.time() - t0))
    for good, name, detail in RESULTS:
        tag = "SKIP" if detail.startswith("跳过") else ("PASS" if good else "FAIL")
        print("  %s %-24s %s" % (tag, name, detail))
    if not args.live:
        print("\n提示：服务启动后用 `python scripts/selftest.py --live` 做真实联调。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
