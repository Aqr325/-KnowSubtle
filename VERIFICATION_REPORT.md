# WordCosmos 全功能验证报告（2026-07-09）

## 结论
**源码与打包 exe 两套环境，均 54/54 项 PASS，0 失败。** 所有功能（演示端点 / 词库 CRUD / 目标 CRUD / 完整 AI 流水线及依赖会话端点）在模拟真实使用下均可用。

## 本轮修复的 3 个真实产品 Bug
| # | 现象 | 根因 | 修复 |
|---|------|------|------|
| 1 | `PUT /api/vocab/{id}` 仅传 `{mastered}`（前端“标记掌握”）→ **422** | `VocabEntry` 要求 `word` 必填 | 新增全可选 `VocabUpdateEntry` 模型，PUT 改用之 |
| 2 | `GET /api/report-card` → **500** `LearningGoal has no attribute 'created_at'` | schema 的 `LearningGoal` 缺 `created_at` | `schema.py` 补 `created_at` 字段 |
| 3 | demo 下 `POST /api/tasks/1/1/toggle` → **404**，且 report-card 又报 `LearningPath has no attribute 'estimated_hours'` | `_build_demo_context` 的 `LearningPath` 无 `modules` | orchestrator 填 3 个 `LearningModule`；`total_hours` 改从 `modules` 求和 |

## 验证方法
- 脚本 `verify_all.py`（仅标准库 `urllib`，54 项），分 Phase A/B/C/D 覆盖：
  - **A** 演示端点（health/planets/progress/tasks/achievements/mistakes/knowledge-graph/memory-curve/suggestions/chat/agent/tutor/vocab/stats/dashboard + 3 个 HTML 页面）
  - **B** 词库 CRUD（添加/按学科过滤/标记掌握/复习/去重/跨学科/删除）
  - **C** 每日目标 CRUD（设定目标 + 进度累加）
  - **D** 完整 AI 流水线（建目标→等完成→依赖会话端点：planets/progress/tasks toggle/achievements/knowledge-graph/chat/agent/exercises/report-card）

## 关键验证点
- **C goals/today(after)** → `pomodoros_done:2, words_learned:10, minutes_studied:25`（此前“56”为旧进程脏数据+多实例假象，本次干净单实例复验已消除）。
- **D pipeline** → `phase=completed`（demo 模式 ~0s 完成）。
- **exe 冒烟** → health 200、无 frozen 分支崩溃；同一套 54 项直击打包二进制全部 PASS。

## 交付
- 提交 `b25364ab` 推送 origin/main（app.py / orchestrator.py / schema.py / verify_all.py）。
- 重建 `Release-Package/Core/main/main.exe`（含本轮修复）。
- 测试产物已清理，无残留进程。

## 教训
- harness 沙箱会剥离含路径的 `LAS_DATA_DIR` 环境变量（simple 值如 `METAGPT_STUBBED` 可过）；验证时 `rm -rf .learning_memory` 保证全新 DB 即可。
- 打包后必须用「headless 拉起真实 exe + 探测端口 + 验证 API」做端到端冒烟，pytest 覆盖不到 frozen 分支。
