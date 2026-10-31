# CI 失败复现沙盒

[返回 README](../README.md)

在独立 Linux Docker 容器中运行失败提交的 pytest，将实际日志、退出码和状态作为后续 CI 分析证据。入口在研发工作台的「CI → 分析当前 CI」弹窗和独立 `/ci` 页面。

## 启用

需要 Docker Linux Engine，以及后端可调用的 `docker`、`git`。在项目根目录构建：

```powershell
docker build -t codepilot-ci-python:local sandbox/python
```

默认镜像只有 Python 3.12 和 pytest 8.3.5。项目依赖须由管理员在可信的镜像构建过程中预装，例如复制经审查的 requirements 文件并安装。请求不能指定镜像、安装脚本或环境变量。修改镜像后重新构建，通过 `CI_SANDBOX_IMAGE` 配置批准的标签或摘要。

在根目录 `.env` 设置：

```dotenv
CI_SANDBOX_ENABLED=true
CI_SANDBOX_IMAGE=codepilot-ci-python:local
CI_SANDBOX_TIMEOUT_SECONDS=120
CI_SANDBOX_MEMORY_MB=512
CI_SANDBOX_CPUS=1
```

更新数据库并重启后端：

```powershell
cd backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

迁移 `0002_ci_sandbox` 为 CI 记录增加 `head_sha`，保留原数据。旧记录需要重新同步，才能获取失败提交 SHA。

## 使用

1. 同步仓库源码与 CI 记录，选择失败的运行。
2. 在复现面板填写仓库内的工作目录，如 `backend`；可选填写单个测试文件或用例。
3. 点击「在沙盒中复现失败」，查看提交 SHA、实际命令、退出码和日志。
4. 完成后点击「重新分析」，CI Agent 会引用最新的实际执行证据。

任务和结果持久化，重开面板可查看最近 20 次记录。API：

```http
POST /api/workflow-runs/{run_id}/reproductions
Content-Type: application/json
Authorization: Bearer <个人访问令牌>

{"command":["python","-m","pytest","-q","app/tests/test_api.py"],"working_directory":"backend"}
```

返回 HTTP 202 和任务记录，通过 `GET /api/workflow-runs/{run_id}/reproductions` 轮询。创建需要 `agent:run` 权限，读取与执行遵守仓库范围，并记录操作人审计。同一 CI 不重复提交未完成任务；每个执行进程同时只运行一个容器，忙碌时返回阻塞结果。

## 执行边界

- 首版仅支持 `python -m pytest` 的参数数组，不执行日志中的 Shell 文本，不自动安装依赖或重放整个 GitHub Actions workflow。
- 从本地 Git 对象库导出失败提交的完整 SHA，不使用当前工作树，不切分支、不联网取源码。浅克隆中缺少该提交时明确阻塞；管理员获取对应提交后可重试。子模块、LFS 大文件和外部服务不自动准备。
- 快照最多 32 MiB、3000 个普通文件。跳过链接、设备、`.git`、常见敏感配置和私钥，未提交变更和未跟踪文件不进入快照。过滤不保证识别所有曾被提交的秘密，仓库仍需做好凭据治理。
- 不挂载宿主目录或 Docker Socket，不注入后端环境变量、数据库密码、GitHub Token。容器禁网、非 root、根文件系统只读，移除 capabilities 并禁止提权。
- 默认 1 CPU、512 MiB 内存、64 进程，内存与 swap 上限相等；工作区为 128 MiB tmpfs，临时目录为 32 MiB tmpfs；仅保留前 64 KiB 输出，关闭 Docker 日志持久化。
- 超时由容器执行器和宿主调用共同约束；结束后清理容器。后台服务崩溃后，恢复任务清理同名容器并标记中断，不自动重放已开始的测试。Docker 不可用时，管理员需检查残留的 `codepilot.ci-sandbox=true` 容器。
- 配置硬上限为 600 秒、2048 MiB、2 CPU。并发限制按进程生效，多实例部署需专门执行节点和集中配额。Docker 共享内核；公开运行不可信代码的多租户服务应增加独立执行节点或更强虚拟化隔离。

`passed` 仅表示所选测试在该镜像中通过，不代表原 CI 恢复；`failed` 表示命令失败，也可能因缺依赖或环境不一致。应核对实际错误与原 CI 是否一致，才能认定复现成功。超时、阻塞和中断均不能视为已复现。复现结果不会自动取消原 CI 的合并阻塞，也不向 GitHub 写入内容。

## 验证

普通回归无需 Docker。构建镜像后可运行真实容器检查：

```powershell
cd backend
$env:CODEPILOT_SANDBOX_INTEGRATION="1"
$env:LLM_API_KEY=""
.\.venv\Scripts\python.exe -m pytest app/tests/test_ci_sandbox.py -q
```

集成检查覆盖非 root、只读根目录、禁网、不注入凭据、不修改宿主工作树、断言失败、超时、输出截断和容器清理。实现参考：[Docker 运行参数](https://docs.docker.com/reference/cli/docker/container/run/)、[资源约束](https://docs.docker.com/engine/containers/resource_constraints/)。
