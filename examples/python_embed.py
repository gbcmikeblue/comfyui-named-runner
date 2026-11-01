#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 Python 项目里内嵌调用 ComfyUI Named Runner。

不需要安装：把仓库的 scripts 目录加进 sys.path 即可。
运行前请先启动 ComfyUI，并确认 registry.json 里有对应别名。

    python examples/python_embed.py ming "你好，世界"

退出码与 CLI 一致：2 config / 3 connect / 4 workflow / 5 param / 6 exec / 7 timeout / 8 io。
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SKILL_ROOT, "scripts"))

import comfy_client as C  # noqa: E402


def render(alias: str, text: str, outdir: str = "./comfy-out") -> list[str]:
    """按别名跑一次工作流，返回落盘产物路径。"""
    cfg = C.load_config()

    # 1) 别名 → (绑定配置, 工作流图)
    ref, graph = C.resolve_workflow(alias, cfg)

    # 2) 连接服务（自动扫描 8188–8192）
    server = C.Server(cfg)
    base = server.resolve()
    print("服务：%s" % base, file=sys.stderr)

    # 3) 统一成 API 格式（API 格式的工作流会原样返回）
    prompt, warnings = C.ui_to_api(graph, server.object_info())
    for w in warnings:
        print("警告：%s" % w, file=sys.stderr)

    # 4) 写参数：显式绑定优先，未绑定的按输入名自动匹配
    applied, _ = C.bind_params(prompt, ref, {"text": text})
    print("参数：%s" % applied, file=sys.stderr)

    # 5) 提交 → 等结果 → 取产物
    pid = server.submit(prompt)
    print("prompt_id：%s" % pid, file=sys.stderr)
    history = server.wait(pid, timeout=cfg["timeout_job"])

    files, texts, warn = C.collect_outputs(history, server, outdir, prefix=alias)
    for w in warn:
        print("警告：%s" % w, file=sys.stderr)

    if texts:
        print("文本产物：%s" % texts, file=sys.stderr)

    return [f["path"] for f in files if f.get("path")]


def main(argv: list[str]) -> int:
    alias = argv[1] if len(argv) > 1 else "ming"
    text = argv[2] if len(argv) > 2 else "示例文本"
    try:
        paths = render(alias, text)
    except C.ComfyError as exc:
        print("[%s] %s" % (exc.stage, exc.message), file=sys.stderr)
        if exc.hint:
            print("  提示：%s" % exc.hint, file=sys.stderr)
        return exc.exit_code

    if not paths:
        print("没有取到产物：检查工作流是否有 Save* 输出节点", file=sys.stderr)
        return 1
    for p in paths:
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
