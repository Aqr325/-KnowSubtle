# PR 描述：完善注册登录鉴权（单设备登录吊销 / 退出所有设备 / chat·config 强制带 token）

> 对应提交：`a7127b5`（已推送 `origin/main`）
> 验证：源码级 `verify_live2.py` 18/18 通过；冻结 exe `test_exe.py` 18/18 通过

## 背景与目标

原有账号系统仅做了基础注册/登录，存在三个缺口：

1. **未实现单设备登录**：同一用户多端同时登录，旧 token 仍有效。
2. **缺少"退出所有设备"**：改密/丢设备后无法一键吊销全部会话。
3. **`/api/chat/agent` 与 `/api/config/llm` 未强制鉴权**：无 token 时返回 400（LLM 未配置守卫），而非 401，数据隔离不生效。

## 改动清单

### `learning_agent_system/database/repo.py`（打包进 exe）
- `create_token`：登录成功时调用 `revoke_other_tokens`，实现**单设备登录**（吊销同用户其余 token）。
- 新增 `revoke_other_tokens` / `revoke_all_user_tokens` / `update_last_login` / `update_profile` / `change_password`。
- `get_user_by_token`：严格过滤 `is_revoked == False and expires_at > now()`。

### `app.py`（打包进 exe）
- 端点：`POST /api/auth/register`（用户名 3–32 / 邮箱格式校验）、`POST /api/auth/login`（置 `last_login` + 单设备吊销）、`GET /api/auth/me`（可选鉴权）、`GET/PUT /api/auth/profile`（须登录）、`POST /api/auth/change-password`（须登录）、`POST /api/auth/logout-all`（须登录，吊销全部）。
- **`/api/chat/agent` 与 `/api/config/llm`（GET/POST）改为 `Depends(_require_user)`**：无 token → 401；鉴权通过但 LLM 未配置 → 400（守卫仍生效）。
- 将 `_get_current_user` / `_require_user` 前置到 config/chat 端点之前（Python 默认参数在定义时求值，避免 `NameError`）。
- 中间件 `user_scope_middleware`：解析 `Authorization: Bearer` → `request.state.user_id` + contextvar。

### `learning_agent_system/database/session.py`（打包进 exe）
- SQLite 改用 `StaticPool`（避免连接池快照在并发请求下读取陈旧对象）。

### `dashboard/index.html` + `Release-Package/Resources/html/index.html`
- 新增 `authFetch`（注入 `localStorage['wc_auth_token']` 的 Bearer）。
- `callBackendChat` / `saveLLMConfig` 改用 `authFetch` 携带 token。
- 注册增加邮箱格式校验；资料编辑 / 改密 / 退出所有设备模态（`#profileModal`）。

### `config/config.json`
- 端口改为 `8753`（与 app / launcher / dashboard 统一）。

### 测试
- 新增 `verify_live2.py`（源码 uvicorn 子进程，18 项）与 `test_exe.py`（冻结 exe 子进程，18 项）。
- `.github/workflows/verify.yml`：ubuntu 任务在 push/PR 时跑 `verify_all.py`(54 项) + `verify_live2.py`；Windows 任务（手动 / `v*` tag）构建 exe 并跑 `test_exe.py`。同时修正原 CI 轮询端口 8000→8753 并补 `pyyaml`/`httpx` 依赖。

## 验证结果（18/18 each）

| 场景 | 期望 | 结果 |
|------|------|------|
| register | 200 | ✅ |
| 单设备登录：login2 后旧 token 访问 profile | 401 | ✅ |
| 单设备登录：新 token 访问 profile | 200 | ✅ |
| 退出所有设备：logout-all 后两 token | 均 401 | ✅ |
| 改密无 token | 401 | ✅ |
| chat 无 token | 401 | ✅ |
| config(GET/POST) 无 token | 401 | ✅ |
| 有 token 但 LLM 未配置 | 400（守卫生效） | ✅ |

## 注意 / 易错点

- **`/api/auth/me` 是可选鉴权**：失效 token 返回 `200 {"authenticated": false}`，**不是 401**。强制 401 仅限 `profile`/`change-password`/`logout-all`/`chat`/`config`。
- **stale server 假阳性**：改完代码务必重启服务再验证；旧 uvicorn 进程会让"已吊销 token 仍有效"的假象出现（本次排查曾因此误判为缓存/连接池问题，实为旧进程）。
- 冻结 exe 的 `LAS_DB_PATH` 必须是原生 Windows 路径（`D:\...` 或 `os.path.abspath` 推导），POSIX `/d/...` 会让 `mkdir` 崩溃。

## 回滚

如需回滚，直接 `git revert a7127b5` 即可；`Release-Package/Core/` 下的 exe 不入库，回滚后需重新构建。
