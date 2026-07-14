# KnowSubtle 第12轮回归认证报告（2026-07-12）

## 结论：全绿，交付链闭合 ✅

| 验证项 | 覆盖 | 结果 | 对象 |
|--------|------|------|------|
| `verify_all.py` | 55 项 API 级契约 | **55/55 PASS** | 真实 exe |
| `e2e_walk.py` | 21 项前端契约端到端 | **21/21 PASS** | 真实 exe |
| `backend_smoke.py` | 37 项后端全路由健康 | **37/37 PASS** | 真实 exe（独立库） |

## 测试对象
- 产物：`Release-Package/Core/KnowSubtle/KnowSubtle.exe`（2026-07-12 重建，含 cffi 2.1.0 扩展）
- 模式：`headless` + `demo`（`METAGPT_STUBBED=1` / `WC_HEADLESS=1`），全新临时库
- 启动方式：同 Bash 命令内后台 `&` 起服 → 命令内 urllib 跑验证（避开跨调用网络隔离）

## 本轮关键修正（测试侧，非应用缺陷）
- **env 路径坑修复**：Git Bash 的 `$PWD` 是 POSIX 风格 `/d/...`，直接传给 Windows 原生 exe 会被解析成 `\d\...`（多一层 `d` 目录），导致 `session._resolve_db_path()` 的 `mkdir(parents=True)` 抛 `WinError 2`、exe 在 import 阶段即崩。
  - 修复：改用 `pwd -W` 取 Windows 绝对路径 `D:/...` 再传入 `LAS_DB_PATH`/`APPDATA`/`LAS_DATA_DIR`，exe 正常启动并通过全部 21 项 e2e。
  - 该歪路径对源码级 `app.py` 冒烟无感（HTTP 测试只查端口起没起、不校验实际落盘路径），属测试脚手架盲区——已补进 MEMORY.md 打包节。
- **cffi 致命坑复核**：重建前发现构建机 cffi 又被污染（2.0.0 缺 `_cffi_backend`），force-reinstall cffi 2.1.0 + cryptography 后，md5 核对 collected `_cffi_backend.cp313-win_amd64.pyd` 与修复源一致（`46b0938c...`），确认真实 LLM HTTPS 路径不会崩溃。

## 已知遗留（非阻塞）
- **③ GET 落库副作用**（achievements / knowledge-graph 的 GET 内写 checkpoint）：用户拍板保持原状，本轮未动。孤儿端点、前端未调用、写入幂等去重，低风险。
- **④ 真实 LLM 端到端**：沙箱无 API Key 不可跑；`_cffi_backend` 已收集，建议用户机首次配 Key 后验证 `/api/chat/agent`。

## 交付状态
- 本地 HEAD = origin/main = `e4bcdc16`，工作区干净，无新增提交（本轮仅验证 + 重建产物，exe 在 `.gitignore` 不入库）。
- GitHub Release **v1.1.0**（Latest）挂载的仍为干净安装包（51.28MB）。
