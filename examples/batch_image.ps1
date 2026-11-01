<#
.SYNOPSIS
    批量出图：文本 → 图像（t2i），或对一个目录里的图逐张做图生图（i2i）。

.DESCRIPTION
    两种模式二选一：
      -PromptFile 每行一个提示词 → 逐条调用 t2i
      -ImageDir   目录内每张 png/jpg → 用同一句改法调用 i2i
    依赖：本机已启动 ComfyUI，且 registry.json 里有 t2i / i2i 别名。
    产物统一落到 -OutDir，文件名前缀为 前缀_序号。

.PARAMETER PromptFile
    文生图模式：UTF-8 文本，每行一个提示词。

.PARAMETER ImageDir
    图生图模式：参考图目录。

.PARAMETER EditPrompt
    图生图模式必填：改法（如「改成水彩画风格，保留构图」）。

.PARAMETER Width / Height
    仅文生图模式有效，默认 1024×1024。

.PARAMETER Resolution
    仅图生图模式有效，参考图缩放预算，默认 1024。

.EXAMPLE
    .\batch_image.ps1 -PromptFile .\prompts.txt -Width 1536 -Height 864

.EXAMPLE
    .\batch_image.ps1 -ImageDir .\素材 -EditPrompt "改成油画风格" -Resolution 1536
#>
[CmdletBinding(DefaultParameterSetName = "T2I")]
param(
    [Parameter(Mandatory = $true, ParameterSetName = "T2I")][string]$PromptFile,
    [Parameter(Mandatory = $true, ParameterSetName = "I2I")][string]$ImageDir,
    [Parameter(Mandatory = $true, ParameterSetName = "I2I")][string]$EditPrompt,
    [Parameter(ParameterSetName = "T2I")][int]$Width = 1024,
    [Parameter(ParameterSetName = "T2I")][int]$Height = 1024,
    [Parameter(ParameterSetName = "I2I")][int]$Resolution = 1024,
    [int]$Steps = 25,
    [int]$Seed = 42,
    [string]$Prefix = "Qwen_image_2.1/batch",
    [string]$OutDir = ".\图",
    [string]$ComfyPy = (Join-Path (Split-Path -Parent $PSScriptRoot) "scripts\comfy.py")
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ComfyPy)) { throw "找不到 CLI：$ComfyPy（用 -ComfyPy 指定）" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# 收集任务：(标题, 参数数组)
$jobs = @()
if ($PSCmdlet.ParameterSetName -eq "T2I") {
    if (-not (Test-Path $PromptFile)) { throw "找不到提示词文件：$PromptFile" }
    $i = 0
    foreach ($line in (Get-Content -Path $PromptFile -Encoding UTF8 |
                       ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" })) {
        $i++
        $jobs += , @($line, @("t2i", $line, "--width", $Width, "--height", $Height))
    }
} else {
    if (-not (Test-Path $ImageDir)) { throw "找不到图片目录：$ImageDir" }
    $i = 0
    foreach ($f in (Get-ChildItem -Path $ImageDir -File |
                    Where-Object { $_.Extension -match '^\.(png|jpg|jpeg|webp)$' })) {
        $i++
        $jobs += , @($f.Name, @("i2i", $EditPrompt, "--image", $f.FullName, "--resolution", $Resolution))
    }
}

if ($jobs.Count -eq 0) { throw "没有可执行的任务" }
Write-Host ("共 {0} 个任务，输出到 {1}" -f $jobs.Count, (Resolve-Path $OutDir)) -ForegroundColor Cyan

$n = 0
$fail = 0
foreach ($job in $jobs) {
    $n++
    $title = $job[0]
    $jobPrefix = "{0}_{1:d3}" -f $Prefix, $n
    Write-Host ("[{0}/{1}] {2}" -f $n, $jobs.Count, $title) -ForegroundColor Gray

    $cliArgs = @($ComfyPy) + $job[1] + @("--steps", $Steps, "--seed", $Seed,
                                         "--prefix", $jobPrefix, "--out", $OutDir, "--json")
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
        $jsonLine = ($text -split "`r?`n" | Where-Object { $_.TrimStart().StartsWith("{") } | Select-Object -Last 1)
        $res = $jsonLine | ConvertFrom-Json
    }

    if (-not $res.ok) {
        $fail++
        Write-Host ("  未取到产物（prompt_id={0}）" -f $res.prompt_id) -ForegroundColor Yellow
        continue
    }

    foreach ($f in $res.files) {
        Write-Host ("  ok {0:N1} KB  {1}" -f ($f.bytes / 1KB), $f.path) -ForegroundColor Green
    }
}

Write-Host ("完成：成功 {0} 个，失败 {1} 个" -f ($jobs.Count - $fail), $fail) -ForegroundColor Cyan
if ($fail -gt 0) { exit 1 }
