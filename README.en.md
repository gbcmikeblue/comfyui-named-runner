# ComfyUI Named Runner

**Turn your local ComfyUI into a "call by name → pass params → get files" generation backend.**

A zero-dependency (stdlib-only, Python 3.9+) CLI plus an importable client library. You keep authoring graphs in the ComfyUI UI — you just stop clicking Run, and you stop hand-writing `POST /prompt` graphs.

```powershell
python scripts\comfy.py dub "Hello from the local runner." --voice 灵小安 --out .\dub
python scripts\comfy.py run my_t2i -p prompt="rainy Jiangnan alley, watercolor" --out .\out
```

> 中文文档见 [README.md](README.md)。

## Why

| Pain | What this does |
|---|---|
| Graph saved by the UI is `nodes` + `links`; the API wants `{"id": {"class_type": ...}}` | Built-in **UI → API converter** driven by `/object_info` (widgets, links, bypass/mute, Reroute) |
| Renaming or re-saving a workflow breaks node ids in scripts | Call by **alias + parameter name**; node ids live only in `registry.json` |
| Port changes / machine changes break automation | Port scan 8188–8192, `doctor` health check, per-stage exit codes |
| Output is human-only | Every command supports `--json` (structured stdout/stderr) |
| Trying TTS needs a 5 GB stack | Ships a dubbing chain on a 0.5B model plus an offline SAPI fallback |

**Boundary:** this tool never starts, restarts, or stops ComfyUI. You launch the server; the runner only discovers, connects, submits, and collects.

## Features

- Call workflows by **alias / filename / path** (three-level resolution, never guesses).
- Accepts both **UI format** and **Export (API)** workflows.
- Deterministic param binding: explicit binding (node id / node title / node class + input name) wins; otherwise match by input name, and **fail loudly with candidates** on ambiguity.
- Collects every output key ComfyUI produces (`images`, `audio`, `gifs`, `videos`, `text`).
- Offline validation: `--dry-run` + `--schema <saved object_info.json>`.
- Embeddable: `comfy_client.py` exposes `load_config` / `Server` / `ui_to_api` / `bind_params`.
- Diagnosable: `doctor` checks server, port, node classes, model weights, torch, registry.
- 7 failure stages × dedicated exit codes (2–8), no silent retries.

## Quick start

```powershell
git clone https://github.com/<your-name>/comfyui-named-runner.git
cd comfyui-named-runner
Copy-Item config.example.json config.json    # set comfyui_root to your install
python scripts\comfy.py doctor
python scripts\comfy.py list --all
python scripts\comfy.py register my_t2i --source user:my_workflow_api.json --param prompt=27.text
python scripts\comfy.py run my_t2i -p prompt="a red panda" --out .\out --json
```

Config precedence: **defaults < `config.json` < environment variables < CLI flags**.
Environment overrides: `COMFY_URL`, `COMFYUI_ROOT`, `COMFY_WORKFLOWS_DIR`, `COMFY_OUTPUT_DIR`, `COMFY_INPUT_DIR`, `COMFY_SKILL_CONFIG`.

## Commands

`doctor` · `wait` · `list` · `describe` · `run` · `tts` · `dub` · `register` · `nodes` · `interrupt`
Global flags (before or after the subcommand): `--json`, `--base-url`, `--config`.

See [docs/cli.md](docs/cli.md) for the full matrix.

## Speech

| Alias | Engine | Notes |
|---|---|---|
| `ming` | Ming-3.0-tts 0.5B, built-in voices | Natural Chinese dubbing, ~2.5–2.8 GiB VRAM |
| `ming_clone` | Ming-3.0-tts, zero-shot clone | 10–30 s reference audio + verbatim transcript |
| `tts` | Windows SAPI5 | Offline, zero VRAM, instant; placeholder/debug quality |
| `cosyvoice3` | CosyVoice3 via TTS Audio Suite | Multi-lingual / dialect / multi-speaker / SRT |

Details in [docs/tts.md](docs/tts.md).

## Exit codes

`0` ok · `2` config · `3` connect · `4` workflow · `5` param · `6` exec · `7` timeout · `8` io

## Layout

```
scripts/    CLI (comfy.py), library (comfy_client.py), self-test, bundled API workflows
docs/       install, CLI, configuration, workflows, TTS, HTTP API, architecture, troubleshooting
examples/   Python embedding, batch dubbing script, sample UI workflow
registry.json        alias routing table
config.example.json  config template
SKILL.md             agent-skill definition
```

## Use as an agent skill

Copy or clone the repo into your agent's user-level skill directory (e.g. `~/.codebuddy/skills/comfyui-local`), create `config.json`, and `SKILL.md` lets an AI assistant drive local ComfyUI from any project.

## Compatibility

Tested against ComfyUI **0.43.0** (2211 node classes) over the classic `/prompt` + `/history` API; works on 0.38+. Not supported: UI workflows containing subgraphs, or graphs with uninstalled node classes (rejected with a clear message). Custom nodes that store display labels in widget values misalign during conversion — export API format instead.

## License

MIT. Third-party models and nodes keep their own licenses (ComfyUI GPL-3.0, Ming-3.0-tts MIT, Fun-CosyVoice3 Apache-2.0, ...).
