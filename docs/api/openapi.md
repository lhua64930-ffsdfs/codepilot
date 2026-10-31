# API 导览

[返回 README](../../README.md) · [启动指南](../getting_started.md) · [安全设计](../architecture/security.md)

启动 API 后访问 `http://127.0.0.1:8000/docs` 查看当前 OpenAPI 模型，或访问 `/openapi.json` 获取机器可读定义。以下路由表按当前应用的 OpenAPI 生成（2026-10-31）；请求字段、响应模型和参数约束以运行中的定义为准。

## 认证与调用

除健康检查与单独校验签名的 GitHub webhook 外，业务 API 要求身份。
正式请求设置 `Authorization: Bearer <个人访问令牌>`；不要将 GitHub PAT 当作应用访问令牌。
当前身份从请求头读取，OpenAPI 页面未提供统一的 Bearer Authorize 控件；可使用带 Header 的 API 客户端。

```http
GET /api/auth/me
Authorization: Bearer <个人访问令牌>
```

无身份返回 401、角色不允许返回 403、无权访问的仓库或资源返回 404。业务 API 还会验证资源范围。

常见状态：同步返回 `completed` 或 `partial`，部分失败详情在 `errors`；文档和评测可能先返回 `queued`，再轮询对应状态；草稿执行须在人工确认后调用确认接口。

## 身份与后台任务

| 方法 | 路径 | OpenAPI 摘要 |
| --- | --- | --- |
| `GET` | `/api/auth/me` | Auth Identity |
| `GET` | `/api/jobs` | List Jobs |

## 仓库与工程事实

| 方法 | 路径 | OpenAPI 摘要 |
| --- | --- | --- |
| `GET` | `/api/issues/{issue_id}` | Get Issue |
| `POST` | `/api/issues/{issue_id}/analyze` | Analyze Issue |
| `POST` | `/api/issues/{issue_id}/analyze/stream` | Analyze Issue Stream |
| `GET` | `/api/issues/{issue_id}/similar` | Similar Issues |
| `GET` | `/api/pull-requests/{pr_id}` | Get Pull Request |
| `POST` | `/api/pull-requests/{pr_id}/analyze` | Analyze Pull Request |
| `POST` | `/api/pull-requests/{pr_id}/analyze/stream` | Analyze Pull Request Stream |
| `POST` | `/api/pull-requests/{pr_id}/review-checklist` | Review Checklist |
| `POST` | `/api/pull-requests/{pr_id}/snapshot` | Prepare Pull Request Snapshot |
| `POST` | `/api/pull-requests/{pr_id}/worktree` | Prepare Pull Request Worktree |
| `GET` | `/api/repos` | List Repos |
| `POST` | `/api/repos/connect` | Connect Repo |
| `DELETE` | `/api/repos/{repo_id}` | Delete Repo |
| `POST` | `/api/repos/{repo_id}/code-graph/rebuild` | Rebuild Code Graph |
| `GET` | `/api/repos/{repo_id}/code-graph/search` | Search Code Graph |
| `GET` | `/api/repos/{repo_id}/code-symbols` | List Code Symbols |
| `GET` | `/api/repos/{repo_id}/conversations` | Get Conversations |
| `POST` | `/api/repos/{repo_id}/conversations` | Add Conversation |
| `DELETE` | `/api/repos/{repo_id}/conversations/{conversation_id}` | Remove Conversation |
| `GET` | `/api/repos/{repo_id}/issues` | List Issues |
| `POST` | `/api/repos/{repo_id}/pr-snapshots/cleanup` | Cleanup Pull Request Snapshots |
| `GET` | `/api/repos/{repo_id}/pull-requests` | List Pull Requests |
| `POST` | `/api/repos/{repo_id}/select` | Select Repo |
| `POST` | `/api/repos/{repo_id}/sync` | Sync Repo |
| `GET` | `/api/repos/{repo_id}/sync-status` | Sync Status |
| `GET` | `/api/repos/{repo_id}/workflow-runs` | List Workflow Runs |
| `GET` | `/api/workflow-runs/{run_id}` | Get Workflow Run |
| `POST` | `/api/workflow-runs/{run_id}/analyze` | Analyze Workflow Run |
| `POST` | `/api/workflow-runs/{run_id}/analyze/stream` | Analyze Workflow Run Stream |
| `GET` | `/api/workflow-runs/{run_id}/failed-jobs` | Get Failed Jobs |

## 对话、反馈与工作流

| 方法 | 路径 | OpenAPI 摘要 |
| --- | --- | --- |
| `POST` | `/api/chat` | Chat |
| `GET` | `/api/chat/feedback` | List Feedback |
| `POST` | `/api/chat/feedback` | Create Feedback |
| `GET` | `/api/chat/feedback/metrics` | Feedback Metrics |
| `GET` | `/api/chat/feedback/trace/{run_id}` | Feedback Trace |
| `PATCH` | `/api/chat/feedback/{feedback_id}` | Review Feedback |
| `GET` | `/api/chat/history` | Chat History |
| `POST` | `/api/chat/plan` | Chat Plan |
| `POST` | `/api/chat/plan/execute/stream` | Chat Plan Execute Stream |
| `POST` | `/api/chat/recommendations` | Prompt Recommendations |
| `POST` | `/api/chat/stream` | Chat Stream |
| `GET` | `/api/chat/workflow-runs` | List Workflow Runs |

## 知识、记忆与检索

| 方法 | 路径 | OpenAPI 摘要 |
| --- | --- | --- |
| `GET` | `/api/rag/models` | Get Model Catalog |
| `GET` | `/api/rag/repositories` | List Rag Repositories |
| `GET` | `/api/rag/repositories/{repo_id}` | Get Rag Repository |
| `PATCH` | `/api/rag/repositories/{repo_id}/config` | Update Rag Config |
| `GET` | `/api/rag/repositories/{repo_id}/documents` | List Documents |
| `POST` | `/api/rag/repositories/{repo_id}/documents` | Upload Document |
| `DELETE` | `/api/rag/repositories/{repo_id}/documents/{document_id}` | Delete Document |
| `GET` | `/api/rag/repositories/{repo_id}/documents/{document_id}/chunks` | List Document Chunks |
| `POST` | `/api/rag/repositories/{repo_id}/documents/{document_id}/retry` | Retry Document |
| `POST` | `/api/rag/repositories/{repo_id}/retrieval-tests` | Run Retrieval Test |
| `GET` | `/api/rag/repositories/{repo_id}/retrieval-tests` | List Retrieval Tests |
| `POST` | `/api/rag/{repo_id}/ask` | Ask Rag |
| `POST` | `/api/rag/{repo_id}/reindex` | Reindex Rag |
| `POST` | `/api/rag/{repo_id}/search` | Search Rag |
| `GET` | `/api/rag/{repo_id}/status` | Get Rag Status |
| `GET` | `/api/repos/{repo_id}/knowledge` | List Knowledge |
| `GET` | `/api/repos/{repo_id}/knowledge/graph` | Get Knowledge Graph |
| `POST` | `/api/repos/{repo_id}/knowledge/graph/rebuild` | Rebuild Knowledge Graph Route |
| `POST` | `/api/repos/{repo_id}/knowledge/notes` | Create Memory Note |
| `POST` | `/api/repos/{repo_id}/knowledge/upload` | Upload Knowledge File |
| `DELETE` | `/api/repos/{repo_id}/knowledge/{source_id}` | Delete Knowledge Item |
| `POST` | `/api/repos/{repo_id}/memory-index/scan` | Start Memory Index Scan |
| `POST` | `/api/repos/{repo_id}/memory-index/snooze` | Snooze Memory Index |
| `GET` | `/api/repos/{repo_id}/memory-index/state` | Get Memory Index State |
| `GET` | `/api/repos/{repo_id}/memory/candidates` | Get Memory Candidates |
| `POST` | `/api/repos/{repo_id}/memory/candidates/{candidate_id}/approve` | Approve Candidate |
| `POST` | `/api/repos/{repo_id}/memory/candidates/{candidate_id}/reject` | Reject Candidate |
| `GET` | `/api/repos/{repo_id}/memory/recall-events` | Get Recall Events |
| `GET` | `/api/repos/{repo_id}/memory/search` | Search Memory |
| `GET` | `/api/repos/{repo_id}/memory/status` | Get Memory Status |
| `GET` | `/api/repos/{repo_id}/team-members` | List Team Members |
| `POST` | `/api/repos/{repo_id}/team-members` | Create Team Member |
| `DELETE` | `/api/repos/{repo_id}/team-members/{member_id}` | Delete Team Member |
| `POST` | `/api/search` | Semantic Search |

## 草稿、报告与评测

| 方法 | 路径 | OpenAPI 摘要 |
| --- | --- | --- |
| `POST` | `/api/action-drafts` | Create Action Draft |
| `GET` | `/api/action-drafts` | List Action Drafts |
| `GET` | `/api/action-drafts/audit-logs` | List Audit Logs |
| `GET` | `/api/action-drafts/{draft_id}` | Get Action Draft |
| `POST` | `/api/action-drafts/{draft_id}/cancel` | Cancel Action Draft |
| `POST` | `/api/action-drafts/{draft_id}/confirm` | Confirm Action Draft |
| `GET` | `/api/evals` | List Evals |
| `GET` | `/api/evals/compare` | Compare Evals |
| `POST` | `/api/evals/rag/run` | Run Rag Eval |
| `POST` | `/api/evals/run` | Run Eval |
| `GET` | `/api/evals/suites` | Get Eval Suites |
| `GET` | `/api/evals/{eval_id}` | Get Eval |
| `POST` | `/api/evals/{eval_id}/issue-draft` | Create Eval Issue Draft |
| `POST` | `/api/evals/{eval_id}/rescore` | Rescore Eval |
| `POST` | `/api/reports/repo-health` | Repo Health |
| `POST` | `/api/reports/weekly` | Weekly Report |
| `GET` | `/api/workspaces` | List Workspaces |
| `POST` | `/api/workspaces` | Create Workspace |
| `POST` | `/api/workspaces/multi-repo-report` | Multi Repo Report |

## 技能、图谱与 webhook

| 方法 | 路径 | OpenAPI 摘要 |
| --- | --- | --- |
| `GET` | `/api/skills` | List Skills |
| `GET` | `/api/skills/mcp-status` | Get Mcp Status |
| `GET` | `/api/skills/{skill_name}` | Get Skill |
| `POST` | `/api/webhooks/github` | Github Webhook |

## 运行边界

`/health` 用于进程健康检查。owner 可通过 `/api/jobs` 查看任务状态和重试次数；队列记录只提供运维视图，不能作为模型质量分数。

GitHub webhook 使用 HMAC 签名校验。草稿确认会产生外部写入；查看或生成草稿不等于已执行。`send_report` 当前只记录本地状态，未接入真实外部消息渠道。
