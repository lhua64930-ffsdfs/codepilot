# 安装与本地运行

[返回 README](../README.md) · [演示指南](demo_guide.md) · [可靠性升级](architecture/reliability_upgrade.md)

## 运行方式

| 模式 | 用途 | 需要什么 |
| --- | --- | --- |
| 文档展示 | HR/面试演示、查看真实界面 | Python 环境、Node.js、已安装的项目依赖 |
| 本地轻量演示 | 体验结构化数据、关键词检索和无模型回答 | SQLite；可选配置 LLM |
| 完整检索与分析 | 验证真实模型、语义召回与混合检索 | PostgreSQL、Milvus、Embedding、LLM；可选远程重排 |

CI 使用 Python 3.11 和 Node.js 22，可采用相同版本准备环境。以下命令以 Windows PowerShell 为例，从项目根目录执行。

## 1. 安装依赖

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
Set-Location frontend
npm ci
Set-Location ..
```

已有 `.env` 时保留原配置，不要直接覆盖。配置真实模型时只在本地环境文件填写密钥，不提交到 Git。

## 2A. 只看项目演示

```powershell
.\scripts\start_docs_preview.ps1
```

- 前端：`http://127.0.0.1:3019`
- API：`http://127.0.0.1:8019/docs`
- 数据：`.data/docs-preview/showcase.db`

脚本默认不调用真实 LLM、向量服务或账号同步。页面显示降级状态是这一模式的预期行为。

另一套轻量演示可使用 `.\scripts\start_rag.ps1`，默认前端 3000、API 8000。已有 `LLM_API_KEY` 时，使用 `-UseConfiguredLLM` 启用真实生成；这仍不等于完整向量检索模式。

## 2B. 配置完整服务

在 `.env` 中核对：

| 配置 | 说明 |
| --- | --- |
| `DATABASE_URL` | 对应 PostgreSQL 的连接信息 |
| `MILVUS_ENABLED=true`、`MILVUS_URI` | 本仓库 Compose 映射的是 `http://127.0.0.1:19531` |
| `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL` | OpenAI 兼容模型服务 |
| `EMBEDDING_PROVIDER`、`EMBEDDING_MODEL`、`EMBEDDING_DIMENSIONS` | 三项共同定义向量空间，必须与索引一致 |
| `DEMO_MODE=false` | 启用个人访问令牌，前端显示连接页 |
| `TOKEN_ENCRYPTION_KEY` | 独立配置的 GitHub Token 加密密钥 |

默认本地 Qwen Embedding 需要额外依赖，并在首次使用时下载模型：

```powershell
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-local-embedding.txt
docker compose up -d postgres etcd minio milvus
```

也可以按 `.env.example` 配置远程 Embedding / Rerank。更换向量模型、维度或 provider 后应重建索引，不能混用不同向量空间。

启动后端：

```powershell
Set-Location backend
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m app.manage_users admin --role owner
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

保存命令输出的一次性个人访问令牌。已有同名用户时，这条命令会轮换其令牌；不需要轮换时不要重复执行。

另开终端启动前端：

```powershell
Set-Location frontend
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000"
npm run dev
```

打开 `http://127.0.0.1:3000`，输入访问令牌，再连接授权仓库、同步数据、上传知识文档。API 文档位于 `http://127.0.0.1:8000/docs`。

已有业务库先备份并停止旧后端，再执行迁移。生产环境还必须设置 `APP_ENV=production`、关闭演示身份并配置 webhook 签名；详见 [安全设计](architecture/security.md)。

## 常见问题

- **页面提示后端不可达**：检查 API 进程、`NEXT_PUBLIC_API_BASE_URL` 与 CORS 地址；查看启动日志。
- **页面要求令牌**：这是 `DEMO_MODE=false` 的预期行为。使用管理员命令生成的令牌，不是 GitHub PAT。
- **Milvus 不可用**：核对 Compose 宿主机端口 19531 与 URI，并检查 etcd、对象存储和 Milvus 日志。
- **Embedding contract mismatch**：核对 provider、模型和维度；不要截断或补零混用向量。
- **固定评测集未就绪**：先上传 `docs/datas/evals/codepilot_baseline.md`，待处理完成再选择固定基线。
- **脚本受到本机执行策略限制**：检查本机 PowerShell 配置，或按文档分别启动服务；不要为演示关闭系统安全防护。

## 开发检查

在 `backend`：`python -m pytest app/tests -q`。
在 `frontend`：`npx tsc --noEmit`、`npm run lint -- --max-warnings 0`、`npm run build`。
GitHub Actions 配置见 [ci.yml](../.github/workflows/ci.yml)。
