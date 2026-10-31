# 安全设计与执行边界

[返回 README](../../README.md) · [令牌配置与升级](reliability_upgrade.md)

## 身份与仓库权限

正式访问使用个人令牌，数据库只保存随机令牌的 SHA-256 摘要。它与用于调用 GitHub 的 PAT 是两种不同凭据。

| 角色 | 主要权限 |
| --- | --- |
| owner | 全局管理员，可连接仓库、管理配置和执行授权操作 |
| maintainer | 在授权仓库内读取、分析、同步、创建及批准草稿 |
| developer | 在授权仓库内读取、分析和创建草稿 |
| viewer | 在授权仓库内读取 |

非管理员由仓库成员关系限定数据范围。请求级权限检查与 ORM 查询范围共同覆盖列表、按 ID 读取、关联资源及更新/删除；无权访问的资源返回 404。聊天创建草稿及反馈记录实际访问者。

免登录演示身份仅在 `APP_ENV=development` 且 `DEMO_MODE=true` 时启用。生产环境拒绝演示身份、默认加密密钥和未配置 webhook 签名。

## 外部动作先审批

1. Agent 生成 `pending_confirmation` 草稿，保留目标、内容和风险信息。
2. 用户审查内容，具备 `draft:approve` 权限才能确认。
3. 执行接口用数据库条件更新抢占 `executing` 状态，提交后才调用外部服务。
4. 成功写入执行结果和审计；网络结果不明标记 `unknown`。
5. `unknown` 或长期停留 `executing` 的草稿需要先到 GitHub 核对，不能自动重试。

支持的动作以 [草稿执行代码](../../backend/app/api/routes/action_drafts.py) 为准，包括评论、创建/关闭 Issue 和添加标签等。`send_report` 当前只记录本地状态，未接入真实外部发送渠道。

## 凭据、工作区和 webhook

- GitHub Token 持久化使用 Fernet 加密，密钥从环境配置读取；生产必须设置独立密钥。
- 工作区工具限制路径范围并跳过特定敏感配置文件与目录。这里只描述已实现的过滤，不能把它视为完整的恶意仓库沙箱。
- 可选的 [CI 复现沙盒](../ci_sandbox.md) 在独立、禁网且有资源限制的 Docker 容器中执行 pytest；不挂载宿主工作区，不注入后端凭据。它与现有只读源码工具是独立的执行路径。
- GitHub webhook 使用 HMAC SHA-256 校验；正式配置缺失签名时拒绝处理。
- 前端个人令牌仅保存于当前标签页的 sessionStorage，部署时应使用 HTTPS。

代码入口：[身份与范围](../../backend/app/services/authentication.py)、[权限](../../backend/app/services/permissions.py)、[草稿执行](../../backend/app/api/routes/action_drafts.py)、[工作区访问](../../backend/app/services/workspace_tools.py)。

## 依赖来源与剩余风险（2026-10-31）

本轮修复升级 FastAPI/Starlette、加密、文件解析、LangChain/LangGraph 和测试组件。新增的 20 个 Python wheel 均从官方文件域获取，下载前查询官方 PyPI 已知漏洞元数据，逐个核对官方 SHA-256 后扫描、离线安装；`pip check` 通过。前端使用官方 npm registry，45 个原镜像源条目与官方 integrity 值一致后归一为官方地址，并用 `npm ci --ignore-scripts` 重建依赖。归档哈希一致不代表发布者代码没有恶意行为，未提供全面安全保证。

PostCSS 高危告警已通过固定修复版本消除。后续将 minimatch 匹配引擎固定到官方 11.0.1，使用私有本地适配层兼容旧 lint 插件的可调用 API 和 `makeRe().test()`；TypeScript 的现代调用直接使用 11.0.1。未保留旧匹配算法，也未排除审计条目，npm 审计为 0 项。适配层只实现已验证的 lint 用法，不是旧版正则编译器的通用替代。升级插件后应评估移除适配层。

Ragas 0.4.3 的多模态文件/URL 处理和 diskcache 5.6.3 的 pickle 解码仍没有公告确认的上游修复版。项目现采用[可审查的本地源码补丁](../../backend/security_patches/README.md)：Cache 默认使用 JSON，拒绝 pickle 的写入和解码；Ragas 的 Collections 和旧版图片辅助函数不再访问外部 URL 或本地文件，保留有大小限制的内联图片。补丁按官方原始源码哈希和固定版本应用，未知源码拒绝修改，应用启动与评测使用前验证补丁哈希。包版本号未改动，所以版本扫描器仍可能报告两项上游告警；应按补丁和攻击回归测试判断本项目的代码状态，不能宣称官方已经修复或全环境没有漏洞。

Docker 镜像的层漏洞、发布者签名，以及现有本机 PostgreSQL 二进制的历史来源尚未完成核验。部署配置仍包含第三方 `pgsty/silo` 镜像；本轮没有启动 Docker 或恢复项目服务，也没有在未验证数据兼容性的情况下替换存储镜像。恢复部署前应完成这些检查。Defender 的项目扫描未查询到指向项目目录的威胁记录，但不能由此断言机器或所有历史下载绝对安全。
