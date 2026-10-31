param(
    [int]$BackendPort = 8019,
    [int]$FrontendPort = 3019
)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendDirectory = Join-Path $projectRoot "backend"
$frontendDirectory = Join-Path $projectRoot "frontend"
$previewDirectory = Join-Path $projectRoot ".data/docs-preview"
New-Item -ItemType Directory -Path $previewDirectory -Force | Out-Null
$pythonPath = Join-Path $backendDirectory ".venv/Scripts/python.exe"
$env:DATABASE_URL = "sqlite:///" + (Join-Path $previewDirectory "showcase.db").Replace("\", "/")
$env:APP_ENV = "development"
$env:DEMO_MODE = "true"
$env:AUTO_SYNC_ENABLED = "false"
$env:MILVUS_ENABLED = "false"
$env:EMBEDDING_PROVIDER = "deterministic"
$env:EMBEDDING_MODEL = "deterministic-demo"
$env:EMBEDDING_DIMENSIONS = "128"
$env:LLM_API_KEY = ""
$env:RAG_LLM_ENABLED = "false"
$env:RAGAS_ENABLED = "false"
$env:GITHUB_TOKEN = ""
$env:FEISHU_FEEDBACK_WEBHOOK_URL = ""
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:$BackendPort"
$env:PYTHONPATH = $backendDirectory
Push-Location $backendDirectory
try {
    & $pythonPath -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "预览库迁移失败" }
    & $pythonPath (Join-Path $PSScriptRoot "seed_showcase.py")
    if ($LASTEXITCODE -ne 0) { throw "演示数据初始化失败" }
}
finally { Pop-Location }
$backend = Start-Process -FilePath $pythonPath -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$BackendPort") -WorkingDirectory $backendDirectory -RedirectStandardOutput (Join-Path $previewDirectory "backend.out.log") -RedirectStandardError (Join-Path $previewDirectory "backend.err.log") -WindowStyle Hidden -PassThru
$nextCli = Join-Path $frontendDirectory "node_modules/next/dist/bin/next"
$frontend = Start-Process -FilePath "node.exe" -ArgumentList @("`"$nextCli`"", "dev", "--hostname", "127.0.0.1", "--port", "$FrontendPort") -WorkingDirectory $frontendDirectory -RedirectStandardOutput (Join-Path $previewDirectory "frontend.out.log") -RedirectStandardError (Join-Path $previewDirectory "frontend.err.log") -WindowStyle Hidden -PassThru
@{ backend = $backend.Id; frontend = $frontend.Id } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $previewDirectory "processes.json") -Encoding UTF8
Write-Output "文档预览：http://127.0.0.1:$FrontendPort；API：http://127.0.0.1:$BackendPort；PID：$($backend.Id), $($frontend.Id)"
Write-Output "独立 SQLite 演示数据；无模型、无真实 GitHub 同步；用于界面截图，不能证明向量召回或模型评分。"
