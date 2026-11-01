<#
.SYNOPSIS
    批量配音：按"每行一句"的文本文件逐句调用 ComfyUI Named Runner。

.DESCRIPTION
    固定参考音色与 seed，保证整套课件音色一致；产物按 前缀_序号.flac 命名。
    依赖：本机已启动 ComfyUI，且 registry.json 里有 ming（或 ming_clone）别名。

.PARAMETER TextFile
    配音文本，UTF-8，每行一句（建议每句 ≤50 字）。

.PARAMETER Refs
    可选。参考音频路径（10-30s 单人、无 BGM）。给了就走音色克隆。

.PARAMETER RefTextFile
    可选。参考音频的逐字转写文件。

.PARAMETER Prefix
    ComfyUI 输出前缀，也是本地文件前缀，如 ming_tts/lesson02。

.PARAMETER OutDir
    产物目录，默认 .\配音。

.PARAMETER Seed
    随机种子，默认 42。固定它 + 固定参考音频 = 稳定音色。

.EXAMPLE
    .\batch_dub.ps1 -TextFile .\lesson02.txt -Refs .\voice\teacher.wav `
                    -RefTextFile .\voice\teacher.txt -Prefix ming_tts/lesson02
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$TextFile,
    [string]$Refs,
    [string]$RefTextFile,
    [string]$Prefix = "ming_tts/batch",
    [string]$OutDir = ".\配音",
    [int]$Seed = 42,
    [string]$ComfyPy = (Join-Path (Split-Path -Parent $PSScriptRoot) "scripts\comfy.py")
)

$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)

if (-not (Test-Path $TextFile)) { throw "找不到文本文件：$TextFile" }
if ($Refs -and -not (Test-Path $Refs)) { throw "找不到参考音频：$Refs" }
if (-not (Test-Path $ComfyPy)) { throw "找不到 CLI：$ComfyPy（用 -ComfyPy 指定）" }

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$lines = Get-Content -Path $TextFile -Encoding UTF8 |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ -ne "" }

Write-Host ("共 {0} 句，输出到 {1}" -f $lines.Count, (Resolve-Path $OutDir)) -ForegroundColor Cyan

$i = 0
$fail = 0
foreach ($line in $lines) {
    $i++
    $jobPrefix = "{0}_{1:d3}" -f $Prefix, $i
    Write-Host ("[{0}/{1}] {2}" -f $i, $lines.Count, $line) -ForegroundColor Gray

    $cliArgs = @($ComfyPy, "dub", $line, "--seed", $Seed, "--prefix", $jobPrefix,
                 "--out", $OutDir, "--json")
    if ($Refs) { $cliArgs += @("--ref-audio", $Refs) }
    if ($RefTextFile) { $cliArgs += @("--ref-text-file", $RefTextFile) }

    $raw = & python @cliArgs 2>&1
    $code = $LASTEXITCODE
    $text = ($raw | Out-String)
    if ($code -ne 0) {
        $fail++
        Write-Host ("  失败（退出码 {0}）：{1}" -f $code, $text.Trim()) -ForegroundColor Red
        continue
    }

    try {
        $res = $text | ConvertFrom-Json
    } catch {
        # 有些 PowerShell 版本会给 stdout 混入 BOM/前缀，退回按行找 JSON
        $jsonLine = ($text -split "`r?`n" | Where-Object { $_.TrimStart().StartsWith("{") } | Select-Object -Last 1)
        $res = $jsonLine | ConvertFrom-Json
    }

    if (-not $res.ok) {
        $fail++
        Write-Host ("  未取到产物（prompt_id={0}）" -f $res.prompt_id) -ForegroundColor Yellow
        continue
    }

    foreach ($f in $res.files) {
        Write-Host ("  ok {0:N1} KB  {1}" -f (($f.bytes / 1KB)), $f.path) -ForegroundColor Green
    }
}

Write-Host ("完成：成功 {0} 句，失败 {1} 句" -f ($lines.Count - $fail), $fail) -ForegroundColor Cyan
if ($fail -gt 0) { exit 1 }
