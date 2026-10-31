param(
    [string]$DataDirectory,
    [string]$PostgresBinDirectory
)
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendDirectory = Join-Path $projectRoot "backend"
$pythonPath = Join-Path $backendDirectory ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) { throw "请先安装 backend/.venv。" }
if (-not $DataDirectory) { $DataDirectory = Join-Path $projectRoot ".data/pgdata" }
$DataDirectory = (Resolve-Path -LiteralPath $DataDirectory).Path
if (-not (Test-Path -LiteralPath (Join-Path $DataDirectory "PG_VERSION"))) {
    throw "没有找到已有 PostgreSQL 数据目录。本脚本不会初始化或覆盖数据库；可配置 -DataDirectory 或使用 docker compose up -d postgres。"
}
if ($PostgresBinDirectory) {
    $pgCtl = Join-Path $PostgresBinDirectory "pg_ctl.exe"
} else {
    $pgCommand = Get-Command pg_ctl.exe -ErrorAction SilentlyContinue
    if (-not $pgCommand) { throw "未找到 pg_ctl.exe，请通过 -PostgresBinDirectory 指定 PostgreSQL bin 目录。" }
    $pgCtl = $pgCommand.Source
}
$clusterVersion = (Get-Content -LiteralPath (Join-Path $DataDirectory "PG_VERSION") -Raw).Trim()
$binaryVersion = & $pgCtl --version
if ($LASTEXITCODE -ne 0 -or $binaryVersion -notmatch "\b$([regex]::Escape($clusterVersion))\.") {
    throw "pg_ctl 主版本与数据目录 $clusterVersion 不一致，请选择对应版本的 PostgreSQL。"
}
Push-Location $backendDirectory
try {
    $targetJson = & $pythonPath -m app.db.doctor --describe
    if ($LASTEXITCODE -ne 0) { throw "无法读取数据库配置。" }
    $target = $targetJson | ConvertFrom-Json
    if ($target.driver -notlike "postgresql*" -or $target.host -notin @("localhost", "127.0.0.1")) {
        throw "DATABASE_URL 不是本机 PostgreSQL 配置；请核对 .env。本脚本不启动远程数据库。"
    }
    $logDirectory = Join-Path $projectRoot ".data"
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    & $pgCtl status -D $DataDirectory
    if ($LASTEXITCODE -ne 0) {
        $portNumber = [int]$target.port
        if ($portNumber -lt 1 -or $portNumber -gt 65535) { throw "数据库端口配置无效。" }
        & $pgCtl start -D $DataDirectory -l (Join-Path $logDirectory "pg.log") -o "-h 127.0.0.1 -p $portNumber" -w -t 20
        if ($LASTEXITCODE -ne 0) { throw "PostgreSQL 启动失败，请检查 .data/pg.log；也请确认端口未被其他实例占用。" }
    }
    # Check both credentials and schema; never silently fall back to SQLite.
    & $pythonPath -m app.db.doctor --migrate
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL 连接或迁移失败，请按检查结果处理。" }
    Write-Host "PostgreSQL 已就绪：$($target.host):$($target.port)/$($target.database)"
}
finally { Pop-Location }
