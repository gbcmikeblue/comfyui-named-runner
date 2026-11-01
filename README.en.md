# ComfyUI Named Runner

**Turn your local ComfyUI into a "call by name → pass params → get files" generation backend.**

A zero-dependency (stdlib-only, Python 3.9+) CLI plus an importable client library. You keep authoring graphs in the ComfyUI UI — you just stop clicking Run, and you stop hand-writing `POST /prompt` graphs.

```powershell
python scripts\comfy.py t2i "rainy Jiangnan alley, watercolor" --width 1536 --height 864 --out .\img
python scripts\comfy.py i2i "repaint as an oil painting" --image .\photo.png --out .\img
python scripts\comfy.py dub "Hello from the local runner." --voice 灵小安 --out .\dub
python scripts\comfy.py run my_t2i -p prompt="a red panda" --out .\out
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
| Every text-to-image graph differs per model | Ships text-to-image and image-to-image aliases on **Qwen Image 2.1** |

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

## Platform support (Windows / macOS / Linux)

Stdlib-only Python, so the runner itself is cross-platform and hard-codes no paths. The real differences are four: **the Python command name, ComfyUI's directory layout, platform-exclusive speech backends, and shell syntax**.

### Capability matrix

| Item | Windows | macOS | Linux |
|---|---|---|---|
| Python command | `python` (or `py -3`) | `python3` | `python3` |
| `t2i` / `i2i` / `dub` / `ming` | ✅ | ✅ | ✅ |
| `tts` (offline SAPI5) | ✅ | ❌ no SAPI5 | ❌ no SAPI5 |
| `examples/*.ps1` | PowerShell 5.1 built in | needs PowerShell 7 (`pwsh`) | needs PowerShell 7 (`pwsh`) |
| Executable bit / shebang | n/a | `chmod +x` | `chmod +x` |
| Path separator | `\` (also accepts `/`) | `/` | `/` |
| `selftest.py` L3 | ✅ | ⏭ SKIP | ⏭ SKIP |

### Requirements

| Item | Windows | macOS | Linux |
|---|---|---|---|
| OS | Windows 10 1809+ / 11 | macOS 12+ (Intel or Apple Silicon) | mainstream glibc distro |
| Python | 3.9+, no third-party packages | system `python3` (Xcode CLT) is enough | `sudo apt install python3 python3-venv` on Debian/Ubuntu |
| ComfyUI | Desktop, or portable `run_nvidia_gpu.bat` | Desktop, or `python3 main.py` | `python3 main.py`, Docker, or systemd |

### Install & configure

```powershell
# Windows
git clone https://github.com/<your-name>/comfyui-named-runner.git D:\tools\comfyui-named-runner
cd D:\tools\comfyui-named-runner
Copy-Item config.example.json config.json; notepad config.json
python scripts\comfy.py doctor
```

```bash
# macOS / Linux
git clone https://github.com/<your-name>/comfyui-named-runner.git ~/tools/comfyui-named-runner
cd ~/tools/comfyui-named-runner
cp config.example.json config.json; $EDITOR config.json
chmod +x scripts/comfy.py scripts/selftest.py
python3 scripts/comfy.py doctor
```

- `config.json`: prefer `/` in paths (works on Windows too). Use `"D:/ComfyUI"` on Windows, `"/Users/me/ComfyUI"` on macOS.
- **`python` is the one field to check manually.** The runner probes `<root>/.venv/Scripts/python.exe`, `<root>/.venv/bin/python`, then `<root>/../standalone-env/python.exe`. Upstream manual installs use **`venv/`** (no dot), which is not probed — set it explicitly if you want `doctor` to check torch locally; leaving it empty is fine.
- Environment variables: `$env:COMFY_URL = "..."` (PowerShell) vs `export COMFY_URL="..."` (bash/zsh).

### Run

| Platform | Start ComfyUI | Run the CLI |
|---|---|---|
| Windows | Desktop Launch, or `run_nvidia_gpu.bat` | `python scripts\comfy.py doctor` |
| macOS | `cd ~/ComfyUI && python3 main.py` | `python3 scripts/comfy.py doctor` |
| Linux | `python3 main.py --listen 127.0.0.1` / systemd / Docker | `python3 scripts/comfy.py doctor` or `./scripts/comfy.py doctor` |

`--out` defaults to `./comfy-out` on every platform. Outputs are fetched over HTTP `/view`, so a ComfyUI running in Docker or on another host works too. Long jobs: `nohup ... &` / `tmux` on Unix, `Start-Process` on Windows.

### Path & shell differences

| Item | Windows | macOS / Linux |
|---|---|---|
| Line continuation | backtick `` ` `` | `\` |
| Quoting | single = literal, double = interpolated | same rule |
| Backslash | not an escape character | escapes inside double quotes — prefer single quotes for paths |
| `~` expansion | not expanded inside strings (use `$env:USERPROFILE`) | expanded |
| Case sensitivity | insensitive | **sensitive** — keep workflow filenames as-is |
| Port check | `netstat -ano \| findstr :8188`, `taskkill /PID <pid> /F` | `lsof -nP -iTCP:8188 -sTCP:LISTEN`, `kill <pid>` |

Always quote `-p` values that contain spaces or CJK: `-p prompt="rainy alley, watercolor"`.

### Cross-platform compatibility notes

- **Line endings.** The repo stores **LF**; whether your working copy becomes CRLF depends on `core.autocrlf` (no `.gitattributes` shipped). Use `git clone` rather than copying folders across platforms. On Unix, `bad interpreter: No such file or directory` or `python3\r` means a CRLF shebang — fix with `sed -i 's/\r$//' scripts/comfy.py` or `git config core.autocrlf input && git checkout -- .`.
- **Encoding.** All JSON/text is UTF-8 (config is read as `utf-8-sig`, so BOM is tolerated). **`.ps1` files must be UTF-8 *with BOM***: Windows PowerShell 5.1 parses BOM-less UTF-8 as ANSI and garbles CJK (the bundled `examples/*.ps1` already carry a BOM). `pwsh` 7 is unaffected. On Windows consoles, `chcp 65001` or `PYTHONIOENCODING=utf-8` fixes garbled output.
- **Permissions.** `chmod +x` on Unix (zip downloads drop the bit — use git). **Do not run as root/sudo**: artifacts become root-owned and the ComfyUI output directory must stay writable. macOS may prompt once in Privacy & Security for the Desktop app.
- **Path length.** Windows has a 260-character default limit; avoid deep OneDrive paths (`D:\tools\...` is safer).

### Platform-specific troubleshooting

| Platform | Symptom | Fix |
|---|---|---|
| Windows | `python` opens the Store | Store stub — use `py -3` or fix `PATH` |
| Windows | `doctor` shows `torch` red | `python` points at `standalone-env` (bootstrap env, no torch); use `<root>/.venv/Scripts/python.exe` |
| Windows | `.ps1` CJK garbled / unterminated string | file lacks a BOM — re-save as UTF-8 with BOM |
| macOS | `python: command not found` | only `python3` exists |
| macOS | `xcrun: invalid active developer path` | `xcode-select --install` |
| macOS | slow / OOM on Apple Silicon | MPS has different memory behaviour — lower `--width/--height` or `--resolution` |
| Linux | `ensurepip is not available` | `sudo apt install python3-venv` |
| Linux | `doctor` can't find `python` | upstream venv is `venv/`, not `.venv/` — set it in `config.json` |
| Linux | Docker ComfyUI unreachable | map the port to loopback (`-p 127.0.0.1:8188:8188`) or set `COMFY_URL` |

## Commands

`doctor` · `wait` · `list` · `describe` · `run` · `t2i` · `i2i` · `tts` · `dub` · `register` · `nodes` · `interrupt`
Global flags (before or after the subcommand): `--json`, `--base-url`, `--config`.

See [docs/cli.md](docs/cli.md) for the full matrix.

## Images

| Alias | Capability | Output size | Notes |
|---|---|---|---|
| `t2i` | text → image | `--width` × `--height` (default 1024²) | ~10–12 GiB VRAM with `int8_convrot` |
| `i2i` | reference image → style transfer / content edit | follows the reference aspect ratio (`--resolution` budget) | edit semantics, not SD-style denoise |

Both use **Qwen Image 2.1** (`TextEncodeQwenImage21` ships with ComfyUI 0.4x):

```powershell
python scripts\comfy.py t2i "rainy Jiangnan alley, watercolor" --width 1536 --height 864 --out .\img
python scripts\comfy.py i2i "repaint as an oil painting, keep the composition" --image .\photo.png --out .\img
```

Details in [docs/image.md](docs/image.md).

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
scripts/    CLI (comfy.py), library (comfy_client.py), self-test, bundled API workflows (image + speech)
docs/       install, CLI, configuration, workflows, images, TTS, HTTP API, architecture, troubleshooting
examples/   Python embedding, batch image / batch dubbing scripts, sample UI workflow
registry.json        alias routing table
config.example.json  config template
SKILL.md             agent-skill definition
```

## Use as an agent skill

Copy or clone the repo into your agent's user-level skill directory (e.g. `~/.codebuddy/skills/comfyui-local`), create `config.json`, and `SKILL.md` lets an AI assistant drive local ComfyUI from any project.

## Compatibility

Tested against ComfyUI **0.43.0** (2211 node classes) over the classic `/prompt` + `/history` API; works on 0.38+. Not supported: UI workflows containing subgraphs, or graphs with uninstalled node classes (rejected with a clear message). Custom nodes that store display labels in widget values misalign during conversion — export API format instead.

> ComfyUI's stock Qwen Image 2.1 templates (`qwen_image_2_1_t2i.json`, `image_qwen_image_2_1_image_edit.json`) rely on subgraphs, so the runner ships hand-written API equivalents as `t2i` / `i2i` — `register` them yourself only if you change the graph.

## License

MIT. Third-party models and nodes keep their own licenses (ComfyUI GPL-3.0, Ming-3.0-tts MIT, Fun-CosyVoice3 Apache-2.0, ...).
