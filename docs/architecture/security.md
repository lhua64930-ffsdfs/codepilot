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
- GitHub webhook 使用 HMAC SHA-256 校验；正式配置缺失签名时拒绝处理。
- 前端个人令牌仅保存于当前标签页的 sessionStorage，部署时应使用 HTTPS。

代码入口：[身份与范围](../../backend/app/services/authentication.py)、[权限](../../backend/app/services/permissions.py)、[草稿执行](../../backend/app/api/routes/action_drafts.py)、[工作区访问](../../backend/app/services/workspace_tools.py)。
