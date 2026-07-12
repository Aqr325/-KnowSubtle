# KnowSubtle 打包产物端到端冒烟报告（第7轮 · 2026-07-12）

## 结论
打包产物 **KnowSubtle.exe 重建并验证通过，55/55 端到端全绿，可交付**。

## 为何重建
既有 exe 时间戳为 7月9日，不含第5轮后端修复（提交 `735aebc`）。为让交付物代表最新代码，基于最新提交 `1d4d082` 重新构建。

## 本轮修复的真实交付风险（非功能 bug，是打包缺陷）
- **构建机 cffi 扩展损坏**：本机 managed venv 的 cffi 2.0.0 缺 `_cffi_backend` C 扩展。首轮重建的 exe 其 `_internal` 缺失 `_cffi_backend.cp313-win_amd64.pyd`。
- **后果**：demo 模式（无 LLM）不受影响、冒烟仍 55/55 **假绿**；但用户一旦配置真实 API Key 走 LLM HTTPS，`cryptography` 加载失败 → 功能崩溃。
- **修复**：`pip install --force-reinstall --no-deps cffi cryptography`（cffi→2.1.0, cryptography→49.0.0）使扩展可用，重建后 `_cffi_backend` 已被正确收集。

## 验证方法
- **headless + demo**：`METAGPT_STUBBED=1 + WC_HEADLESS=1` 启动真实 exe（仅起服务、不弹窗）
- **目录重定向**：`APPDATA` / `LAS_DATA_DIR` / `LAS_DB_PATH` 指向项目内临时目录，避开沙箱 AppData 拦截与多实例误判
- **端到端**：`verify_all.py <base_url>` 对真实二进制跑 55 项（含 Phase D 完整 AI 流水线：会话创建→completed→全部依赖端点）

## 结果
- 重建后两轮冒烟均 **55/55 ALL PASS**（VERIFY_EXIT 0）
- 新 exe：`Release-Package/Core/KnowSubtle/KnowSubtle.exe`（2026-07-12 12:08，11.3MB）
- frozen 代码路径无崩溃（第5轮担心的 `migrate_json_to_db` frozen 分支已验证健康）
- `grep` 确认 `_internal/_cffi_backend.cp313-win_amd64.pyd` 已打包

## 交付状态
- exe 在 `.gitignore`（不入库），由 NSIS 发布流程生成安装包；本地验证通过即收尾，未提交 git
- **建议**：用户机首次配置真实 API Key 时跑一次 `/api/chat/agent` 做最终确认（沙箱无 Key，未实测真实 HTTPS 路径，但静态收集已就位）

## 同批：第6轮前端运行时加固（已交付）
- F1==F4 逐字节一致；F2/F3 补齐 10 处 XSS 转义与 fetch 错误捕获（提交 `1d4d082`）
- 遗留（低危，待定）：三份 `configAvatar.innerHTML(a.avatar)` 未转义（仅自 XSS）；F3 词库 review POST 无 `.catch`（与 F1 基线一致）
