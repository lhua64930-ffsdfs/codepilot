# 可靠性升级说明

## 升级已有环境

1. 停止旧版后端，备份关系数据库和上传目录。
2. 在 `backend` 目录执行 `python -m alembic upgrade head`，再启动后端。
3. `scripts/start_rag.ps1` 已加入显式迁移步骤。

应用启动只检查版本并启动服务，不再自动 ALTER/DROP 字段或删除历史代码向量。
基线迁移支持现有演示库和空库，只增加缺失表、列和索引；保留旧 `documents.embedding` 字段和数据。
后续数据库变更应创建新的 Alembic revision，不能修改已经部署的基线。基线降级必须从备份恢复。

## 身份与仓库权限

本地演示免登录仅在 `APP_ENV=development` 且 `DEMO_MODE=true` 时启用。
正式环境设置 `APP_ENV=production`、`DEMO_MODE=false`、独立的 `TOKEN_ENCRYPTION_KEY` 和 `GITHUB_WEBHOOK_SECRET`。
生产启动会拒绝演示身份、默认加密密钥和未配置的 webhook 签名。

在 `backend` 使用管理员命令创建身份或轮换令牌：

```text
python -m app.manage_users admin --role owner
python -m app.manage_users alice --role developer --repo <仓库UUID>
python -m app.manage_users reviewer --role viewer --repo <仓库UUID>
python -m app.manage_users alice --revoke
```

命令只输出一次个人访问令牌，数据库仅保存其 SHA-256 摘要。
重复指定用户名称会轮换令牌，并用本次 `--repo` 参数替换其仓库授权。
前端连接页可输入令牌；只在当前标签页的 sessionStorage 保存。API 使用 `Authorization: Bearer <令牌>`。
请通过 HTTPS 部署前端与 API。

owner 是全局管理员；其他角色通过仓库成员关系限制数据范围。viewer 只读，developer 可分析和创建草稿，maintainer 可同步及批准草稿。
连接仓库、删除数据、配置设置和后台任务管理需要 owner。审批与反馈记录真实访问者。
列表、按 ID 读取、关联数据和 ORM 更新/删除都应用仓库过滤；无权访问的资源返回 404。
非管理员的 Agent 请求必须指定仓库，不能使用项目根目录作为无仓库工作区。

## 同步与外部写操作

PR 文件、评论只有在远端成功返回后才替换，成功返回空列表会清空旧记录；失败则保留旧数据。
API 的 `status=partial` 和 `errors` 表明部分失败。仓库记录持久保存最近一次状态，`last_sync_at` 只记录最近完整成功时间。
同仓库的同步在单进程中互斥；PostgreSQL 使用 advisory lock 进一步覆盖多个 API 实例。SQLite 仅适合单实例演示。

草稿通过数据库条件更新抢占 `pending_confirmation -> executing`，提交抢占后才调用 GitHub。
并发确认/取消不能再次触发写操作。网络结果不明标为 `unknown`；执行中断可能保留 `executing`。
这两种状态都不允许自动重试，管理员必须先在 GitHub 核对，避免重复评论或创建 Issue。

## 持久化后台任务

文档处理、项目索引、代码分析、webhook 同步和评测请求写入 `background_jobs`。
API 内置轮询工作器；可由多个实例竞争领取，通过原子状态更新和租约避免正常情况下重复领取。
租约 120 秒，每 40 秒续约；重启后等待旧租约到期恢复。异常任务最多重试三次，间隔递增。
这是至少执行一次的队列，重建任务必须保持幂等。GitHub 外部写操作不进入队列。
旧版本已经停在进行中、但没有持久化参数的评测需要重新提交；不能凭空恢复原请求。
owner 可通过 `GET /api/jobs` 查看最近任务、尝试次数和失败原因。已记录的评测质量失败不会被当成基础设施故障自动重跑。

## 固定评测与检查

上传 `docs/datas/evals/codepilot_baseline.md` 到当前仓库知识库，待索引完成后运行
`devflow-real-project-rag-baseline`。配套 `rag_cases.json` 包含 10 个人工维护的工程策略、缺少答案、过期状态与显式工具调用案例。
真实 ChatAgent/Judge 需要配置模型；单元测试、数据集装载检查通过不能替代真实模型评分。
跨仓库隔离、网络失败保留、并发防重、租约恢复、迁移无损及检索查询次数由独立回归测试覆盖。

GitHub Actions 检查后端测试、空库迁移、前端类型、零警告 Lint 和生产构建。
CI 默认不使用线上模型、GitHub Token 或私有知识库，不把模拟结果宣称为真实 RAGAS 分数。

## 代码与界面

工作区路径与文本读取抽到 `workspace_tools.py`，Agent 工具参数和状态抽到 `runtime_types.py`，前端工作区类型抽到 `workspace-types.ts`。
稳定回调读取最近提交的状态，避免 Hooks 依赖遗漏与无意义重复执行；检索父块扩展按命中来源批量读取。
项目加载失败展示错误和重试入口，部分同步失败有明确提示；草稿展示执行中和待核对状态。
