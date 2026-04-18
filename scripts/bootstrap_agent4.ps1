<#
.SYNOPSIS
    Agent 4 (RAG & Memory) 一键环境 bootstrap（Windows PowerShell 版）

.DESCRIPTION
    自动完成以下步骤：
      1. 检查 Python 版本 (>= 3.10)
      2. 配置 HuggingFace 镜像与本地模型缓存目录
      3. 安装 requirements.txt 中的依赖
      4. 首次创建 .env（若已存在则保留）
      5. 下载 BGE 模型 + 灌入 assets/seeds 到本地 Chroma
      6. 冒烟校验

    每一步都幂等可重复；失败即停并打印原因。

.PARAMETER Force
    重建 Chroma collection（换模型或种子大改时使用）

.PARAMETER SkipInstall
    跳过 pip install（只想重灌种子时使用）

.PARAMETER NoMirror
    不使用国内镜像（海外网络环境）

.PARAMETER Python
    指定 Python 可执行文件路径。默认使用 $env:AIAD_PYTHON 或系统 python

.EXAMPLE
    .\scripts\bootstrap_agent4.ps1
    首次或日常同步运行

.EXAMPLE
    .\scripts\bootstrap_agent4.ps1 -Force
    强制重建种子库（适合换 embedding 模型后）

.EXAMPLE
    .\scripts\bootstrap_agent4.ps1 -SkipInstall -Force
    依赖没变，只想重灌 Chroma
#>

[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$SkipInstall,
    [switch]$NoMirror,
    [string]$Python
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

# 中文 Windows 默认控制台代码页是 936 (GBK)，而脚本会强制子进程 Python
# 用 UTF-8（PYTHONIOENCODING=utf-8）输出日志与 JSON。两边不一致时 Python
# 的中文日志会被 GBK 错误解码成"鍔犺浇"这类乱码。
# 这里把控制台 I/O 编码切到 UTF-8，保证整条管道统一。
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    [Console]::InputEncoding  = [System.Text.Encoding]::UTF8
    $OutputEncoding           = [System.Text.Encoding]::UTF8
} catch {
    # 极简环境可能没有 System.Console，降级忽略即可；此时中文可能仍有乱码，
    # 但不影响脚本本身的执行结果（exit code 仍然正确）。
}

function Write-Step {
    param([int]$Index, [int]$Total, [string]$Message)
    Write-Host ""
    Write-Host "[$Index/$Total] $Message" -ForegroundColor Cyan
}

function Write-Ok     { param([string]$M) Write-Host "      ✓ $M" -ForegroundColor Green }
function Write-Info   { param([string]$M) Write-Host "      · $M" -ForegroundColor Gray }
function Write-WarnEx { param([string]$M) Write-Host "      ! $M" -ForegroundColor Yellow }

# 执行外部命令（如 python），把 stderr 合并到 stdout 按普通文本打印，
# 避免 PowerShell 5.1 把 Python 的 INFO 日志当作 NativeCommandError 红色报错。
function Invoke-Native {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(ValueFromRemainingArguments)][string[]]$Arguments,
        [string]$FailMessage = "命令执行失败"
    )
    $oldPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $FilePath @Arguments 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) {
                Write-Host $_.Exception.Message
            } else {
                Write-Host $_
            }
        }
        $rc = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $oldPref
    }
    if ($rc -ne 0) { throw "$FailMessage (exit $rc)" }
}

# ---------- 解析 Python ----------
if (-not $Python) {
    if ($env:AIAD_PYTHON) { $Python = $env:AIAD_PYTHON }
    else { $Python = "python" }
}

Write-Host "==========================================" -ForegroundColor Magenta
Write-Host "  Agent 4 (RAG & Memory) Bootstrap" -ForegroundColor Magenta
Write-Host "==========================================" -ForegroundColor Magenta
Write-Info "ProjectRoot = $ProjectRoot"
Write-Info "Python      = $Python"

$TotalSteps = 6

# ---------- Step 1: Python 版本检查 ----------
Write-Step 1 $TotalSteps "检查 Python 版本 (要求 >= 3.10)..."
try {
    $versionOutput = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
} catch {
    Write-Host "      ✗ 找不到 Python 可执行文件: $Python" -ForegroundColor Red
    Write-Host "        请先 conda activate aiad，或用 -Python 参数指定路径" -ForegroundColor Red
    exit 2
}
$parts = $versionOutput.Split(".")
$major = [int]$parts[0]; $minor = [int]$parts[1]
if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
    Write-Host "      ✗ Python 版本过低: $versionOutput (需要 >= 3.10)" -ForegroundColor Red
    exit 2
}
Write-Ok "Python $versionOutput"

# ---------- Step 2: HF 镜像 + 模型缓存目录 ----------
Write-Step 2 $TotalSteps "配置 HuggingFace 镜像与模型缓存..."
$ModelCacheDir = Join-Path $ProjectRoot ".model_cache"
New-Item -ItemType Directory -Force -Path $ModelCacheDir | Out-Null
$env:HF_HOME = $ModelCacheDir
if ($NoMirror) {
    Write-Info "已跳过国内镜像 (NoMirror 模式)"
    $PipIndex = @()
} else {
    $env:HF_ENDPOINT = "https://hf-mirror.com"
    Write-Info "HF_ENDPOINT = https://hf-mirror.com"
    $PipIndex = @("-i", "https://pypi.tuna.tsinghua.edu.cn/simple")
}
# 强制子进程 Python 也走 UTF-8，避免 cli probe 打印中文 JSON 时踩 GBK 编码
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
Write-Ok "HF_HOME     = $ModelCacheDir"

# ---------- Step 3: 安装依赖 ----------
Write-Step 3 $TotalSteps "安装 Python 依赖..."
if ($SkipInstall) {
    Write-Info "已跳过 (SkipInstall 模式)"
} else {
    Invoke-Native -FilePath $Python -Arguments (@("-m", "pip", "install", "--upgrade", "pip") + $PipIndex) -FailMessage "pip upgrade 失败"
    Invoke-Native -FilePath $Python -Arguments (@("-m", "pip", "install", "-r", (Join-Path $ProjectRoot "requirements.txt")) + $PipIndex) -FailMessage "pip install requirements.txt 失败"
    Write-Ok "依赖安装完成"
}

# ---------- Step 4: 准备 .env ----------
Write-Step 4 $TotalSteps "准备 .env 文件..."
$EnvPath = Join-Path $ProjectRoot ".env"
$EnvExample = Join-Path $ProjectRoot ".env.example"
if (Test-Path $EnvPath) {
    Write-Ok ".env 已存在，保留不覆盖"
    Write-Info "如果需要新增 AGENT4_* 配置，请手动对比 .env.example"
} else {
    if (-not (Test-Path $EnvExample)) {
        throw ".env.example 不存在，无法自动生成 .env"
    }
    Copy-Item $EnvExample $EnvPath
    Write-Ok "已从 .env.example 生成 .env"
    Write-WarnEx "请编辑 .env，把 MEDIACRAWLER_PYTHON_EXE 改成你自己的路径"
}

# ---------- Step 5: 下载模型 + 灌种子 ----------
Write-Step 5 $TotalSteps "下载 BGE 模型 + 灌入 assets/seeds 到 Chroma..."
Write-Info "首次执行会从 HuggingFace 下载 BAAI/bge-small-zh-v1.5 (~95MB)"
Push-Location $ProjectRoot
try {
    $initArgs = @("-m", "app.services.memory.cli", "init")
    if ($Force) { $initArgs += "--force" }
    Invoke-Native -FilePath $Python -Arguments $initArgs -FailMessage "cli init 失败"
    Write-Ok "种子灌库完成"
} finally {
    Pop-Location
}

# ---------- Step 6: 冒烟校验 ----------
Write-Step 6 $TotalSteps "冒烟校验..."
Push-Location $ProjectRoot
try {
    Invoke-Native -FilePath $Python -Arguments @("-m", "app.services.memory.cli", "status") -FailMessage "cli status 失败"

    $ProbeFixture = "tests/memory/fixtures/mock_global_state_beach.json"
    if (Test-Path (Join-Path $ProjectRoot $ProbeFixture)) {
        Write-Info "运行 probe 冒烟 (海边场景)..."
        try {
            Invoke-Native -FilePath $Python -Arguments @("-m", "app.services.memory.cli", "probe", $ProbeFixture) -FailMessage "probe 返回非 0"
            Write-Ok "probe OK"
        } catch {
            Write-WarnEx "probe 返回非 0 状态，但不致命: $($_.Exception.Message)"
        }
    }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "  ✅ Agent 4 环境就绪" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "下一步你可以："
Write-Host "  · 跑单元测试     : pytest tests/memory -v"
Write-Host "  · 查看 collection : $Python -m app.services.memory.cli status"
Write-Host "  · 端到端冒烟     : $Python -m app.services.memory.cli probe tests/memory/fixtures/mock_global_state_beach.json"
Write-Host ""
