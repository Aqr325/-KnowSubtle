# KnowSubtle 上线就绪报告（Go-Live Readiness）

**日期**：2026-07-12
**范围**：基于第 12 轮回归（55/55 + 21/21 + 37/37 全绿）之上，针对"即将上线"做的三路独立审计：
- 后端架构可用性审查（backend-audit）
- 上线前安全最终复核（sec-audit）
- 文档与终端用户配置就绪度（doc-audit）

> 全部为**只读审查**，未改动任何代码/文件。结论均附 文件:行号 证据。

---

## 综合结论

**有条件就绪（Conditionally Ready）—— 不可直接在"真实 AI 产品"定位下上线。**

三路审计一致确认：当前打包产物（`KnowSubtle.exe` + NSIS 安装包）的**后端 AI 流水线在交付物里是永久 demo 占位**（不读任何 Key）；唯一能跑真实大模型的，是前端齿轮 ⚙ 配置里的**浏览器直连**用户自有 LLM，且受 **CORS 拦截** + **Key 明文 localStorage** 双重限制。安全基线（2026-07-08 加固）基本仍有效，但存在 3 项上线前应修的安全问题（P1/P3-1）。

---

## 一、已验证就绪 / 健康项

| 项 | 状态 | 证据 |
|---|---|---|
| 三套验证全绿（针对真实 exe，demo 模式） | ✅ | verify_all 55/55、e2e_walk 21/21、backend_smoke 37/37 |
| 路径穿越白名单 `_validate_session_id()` | ✅ 仍有效 | `orchestrator.py:556-559` 正则排除 `/` `\` |
| BOM 编码 `utf-8-sig` | ✅ 仍有效 | `repo.py:629/655/688/713` |
| goal 描述 500 字限制 | ✅ 仍有效 | `app.py:750-751` |
| F1 内 XSS `escHtml` 覆盖 | ✅ 仍有效 | 词库/任务/成就/建议/agent/气泡/配置/词云/复习/番茄 均转义 |
| 发布前端 F4 == F1 字节一致 | ✅ | 均为 184607 字节 |
| 后端 Key 不泄露前端 | ✅ | app.py 无 `/api/config`/`/api/set-key`、无记录 Key 的日志 |
| 默认绑定 127.0.0.1（本地单用户） | ✅ | `launcher.py:124`，攻击面受限 |

---

## 二、必须由你拍板：产品上线定位

这是上线前最根本的决策，决定后续是"轻量收口"还是"一轮实质开发"。

### 选项 A：离线演示版（= 当前实际状态）
- 现状：demo 开箱即用；真实 AI 仅前端齿轮直连（CORS + 明文 Key 局限）。
- 上线前**轻量收口**即可：UI 标注"离线演示、AI 为占位" + 补《真实模式配置指南》+ 统一版本号 + 修误导文档（见第四节）。

### 选项 B：真·AI 产品
- 现状不满足。后端真实模式在 exe 中是**死代码**（`app.py:11` 强制 stub → `stub.py:23` 写死 `METAGPT_STUBBED=1`；`build/build_exe.py` `--exclude-module metagpt`）。
- 需一轮开发：env 开关控制 stub + 构建收集真实 metagpt + 后端 Key 注入通道 + 前端改走后端 `/api/chat/agent` 转发（解 CORS + Key 明文）。**非发布前小修**。

> ⚠️ 若选 B 但只"设了 Key 就当真 AI"，实际仍是占位回复，会造成严重的用户预期错配——务必在定位上想清楚。

---

## 三、上线前必须修的安全项（与定位无关，建议无论 A/B 都修）

| 编号 | 问题 | 位置 | 修复 | 严重度 |
|---|---|---|---|---|
| **S1** | CORS `allow_origins` 含 `"null"`，恶意本地网页可跨源读取 localhost API | `app.py:100-110` | 删除 `"null"` | P1 |
| **S2** | 无认证下 `/api/sessions` 列出全部会话、可枚举读取他人 PII（session_id 可预测 `session_YYYYMMDD_HHMMSS`） | `app.py:782` / `app.py:795` | 删除"列出全部会话"端点或加轻量令牌；session_id 改 `secrets.token_hex` | P1 |
| **S3** | `profile.html` 的 bio→toast 经 `innerHTML` 未转义（存储型 XSS） | `profile.html:984→1017` | `showToast` 用 `textContent` 或对 message 调 `escHtml` | P3（但一行修复，建议一并做） |

> 前提：生产启动器默认绑定 `127.0.0.1`。**若被改为 `0.0.0.0`，S1/S2 升为 P0**。

---

## 四、选 A（离线演示版）时的发布前清单

1. **UI 明确标注**：关于页/启动页写明"当前为离线演示版，AI 回复为占位内容"。
2. **补《真实模式配置指南》**：讲前端齿轮 ⚙ 配置入口 + 说明"仅前端对话走真实 LLM、需支持浏览器 CORS 的端点、Key 存浏览器本地"。
3. **统一版本号**：`install.nsi`(1.1.0) / `RELEASE_PACKAGE_REPORT`(v2.1.0) / `用户手册.md`(v3.0.0) 三处打架 → 对外统一为 **1.1.0**。
4. **修误导文档**：`RELEASE_PACKAGE_REPORT.md` 六.1 称"config.json/环境变量可启用真实 MetaGPT"——事实相反（config.json 仅含 app_name/port/host，打包版无法启用真实 metagpt），必须删除或更正。
5. **安全 S1/S2/S3** 一并修。

---

## 五、选 B（真·AI 产品）时的开发项（非小修）

| 项 | 内容 |
|---|---|
| 后端真实模式可达 | `app.py` 用 env 开关（如 `KNOWSUBTLE_REAL=1`）控制是否 import stub；`build_exe.py` 改为收集真实 metagpt |
| 后端 Key 通道 | 新增带鉴权的 `/api/config/llm` 端点持久化 Key；或原生窗口系统级设置面板 |
| 前端转发 | 聊天请求改发后端 `/api/chat/agent`，由后端带 Key 转发（解 CORS + Key 不进浏览器） |
| 失败模式健壮化 | `create_session` 启动前 `is_configured` 预检；`run_full_pipeline` 各阶段 try/except，错误状态前端可感知 |

---

## 六、其他建议（P2/P3，记录即可，不阻塞上线）

- **P2-1** Key 明文存 localStorage（`index.html:3736/3738/3755`）→ 改后端代理或 OS 密钥库；配置表单用 `password` 且不回填明文。
- **P2-2** CSP `script-src 'self' 'unsafe-inline'`（`app.py:123`）→ 改 nonce-based，移除 `'unsafe-inline'`。
- **P3-2** 无速率限制 + 无认证 → 对敏感端点加简单速率限制，防 LLM 费用放大/DoS。
- **P3-3** `session.py:181` 用 f-string 拼 SQL 索引标识符（来自内部 metadata，实际不可利用，但不符合参数化最佳实践）。
- **P2 启动期 env 默认值散落多份且变量名混用**（`OPENAI_API_KEY` vs `LLM_API_KEY`）→ 统一单一配置来源。

---

## 七、上线前必做清单（汇总）

- [ ] **决策产品定位（A 演示版 / B 真 AI 产品）** ← 阻塞项，需你拍板
- [ ] 修 S1：CORS 删 `"null"`（app.py:105）
- [ ] 修 S2：会话枚举端点加认证或移除（app.py:782/795）
- [ ] 修 S3：profile.html bio→toast XSS（984→1017）
- [ ] 若选 A：补 UI 标注 + 《真实模式配置指南》+ 统一版本号 + 修误导文档
- [ ] 若选 B：按第五节排期开发（非发布前小修）
- [ ] 重新打包并跑三套验证回归（55/21/37）

---

*审计团队：backend-audit（后端架构）、sec-audit（安全工程）、doc-audit（技术文档）。主理人综合。*
