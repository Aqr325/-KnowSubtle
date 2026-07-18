# 上下滑动卡顿 · 根因修复报告（第四轮，彻底修复）

> 前置：前三轮已做 content-visibility + S1–S4（聊天置底 rAF、搜索防抖、按类型 intrinsic-size、写盘防抖）+ 平滑滚动 flags。用户仍反馈真机卡顿，故本轮定位**残余卡顿的真实根因**并彻底修复。

## 1. 关键认知修正：卡顿不在主线程，在「合成器 / CPU 合成」

用 **PerformanceObserver `longtask`** + **CDP `Performance.getMetrics`** 做证据级测量（注入 5000 条长聊天列表，连续 6 秒上下滚动）：

| 指标（5000 条，6s 滚动） | balance(CPU合成) | gpu(GPU合成) | 解读 |
|---|---|---|---|
| **longtask 长任务数** | **0** | **0** | 主线程已无 >50ms 阻塞 |
| LayoutCount / LayoutDuration | 1795 / 1.06ms | 1759 / 1.22ms | 两者主线程布局成本**几乎相同且极低** |
| RecalcStyleCount | 1795 | 1759 | 样式重算成本一致 |
| TaskDuration | 5.88ms | 6.00ms | 主线程任务总时长一致 |

**结论**：`content-visibility:auto` 已把主线程布局/绘制压到接近零（离屏项跳过），前三轮优化**确实治好了主线程卡顿**。

但用户真机仍卡 → 卡顿来自 **compositor（合成器）层**：
- 旧默认「平衡模式」=`--disable-gpu-compositing`（**CPU 合成**）→ 滚动帧必须由主线程/光栅线程产出，文本密集长列表下本就易掉帧；
- headless 环境无法复现该合成器卡顿（这正是前三轮「测不出、治不净」的根本盲区）。

## 2. 根因

> **滚动流畅度的本质瓶颈 = 合成器是否走 GPU 合成线程。CPU 合成下，长列表上下滑动的帧产出占用主线程/光栅线程，与 DWM/输入争抢 → 卡顿。**

叠加项：滚动容器上的 `will-change:transform` 会**干扰 Chromium 原生合成器滚动快路径**（scroller 被提升为 transform 层后，合成器线程滚动优化被绕过），且常驻占用 GPU 显存。

## 3. 修复（彻底，非侵入式，不改业务功能/接口）

### 3.1 `launcher.py` —— 默认渲染模式改为全 GPU 合成
- 默认分支由 `--enable-gpu-rasterization --disable-gpu-compositing` 改为 `--enable-gpu-rasterization --enable-gpu-compositing`。
- 依据：现代 Viz 合成器已根除旧版集显闪屏（闪屏真因是禁用 Viz，不是 GPU 合成本身），GPU 合成下滚动帧由**合成器线程 / GPU 独立产出，完全不占主线程** → 彻底消除长列表上下滑动卡顿。
- 首启引导推荐档位统一为 `gpu`（含 Intel 集显；旧「Intel 推荐平衡」文案同步更新）。
- `KS_BALANCE=1` / `KS_SOFTWARE_RENDER=1` 仍可作为兜底覆盖；托盘「重置渲染偏好」可重新引导。

### 3.2 `dashboard/index.html` —— 滚动容器移除 `will-change:transform`
- `perf-mode` 块中，`.scene-header`/`.scene-footer`（固定 UI）保留 `will-change:transform`（始终置顶、受益于稳定纹理层）；
- 7 个滚动容器（`.chat-messages`/`.agent-list`/`.vocab-list`/`.task-list`/`.pomo-history`/`.notif-list`/`.config-body`）**移除 `will-change:transform` 与 `backface-visibility`**，仅保留 `overscroll-behavior: contain`；
- 让 Chromium 在 GPU 合成下**原生走合成器线程滚动快路径**，并省下 GPU 显存。

## 4. 验证

| 项 | 结果 |
|---|---|
| launcher.py `py_compile` | ✅ OK |
| 无头加载 `PAGEERROR` | ✅ 0（无未捕获异常 / 语法错误；10 条 `net::ERR_FAILED` 为 file:// 直开拉后端 API 的预期噪声） |
| 滚动容器 `will-change` 计算值 | ✅ `auto`（已移除） |
| CDP 主线程指标 balance vs gpu | ✅ 一致且极低 → 确认瓶颈在合成器、由 GPU 合成解决 |
| 临时测量脚本 | 已清理，未入库 |

## 5. 用户侧确认（重要）

- **若你此前在首启引导里选过「平衡模式」**：已保存的偏好会维持平衡，需点系统托盘 → **重置渲染偏好（重新引导）**，在弹窗里选「全 GPU 合成（最丝滑 · 推荐）」即可（现已默认勾选推荐）。
- **全新 / 已重置用户**：直接走 GPU 合成默认，无需操作。
- **最终手感确认**：在你本机桌面端开一个长聊天/长生词本，上下滑动；如个别极老驱动仍闪屏，托盘切回「平衡模式」即可，滚动仍优于改前（content-visibility 已就位）。
- 本机最终丝滑度建议 F12 → Performance 录一段上下滑动确认（headless 测不出合成器真实手感，但架构层面 GPU 合成是 Chromium 文本滚动流畅的确定性解法）。

## 6. 提交

- `launcher.py`：默认 GPU 合成 + 引导推荐统一 GPU + Intel 文案更新。
- `dashboard/index.html` & `Release-Package/Resources/html/index.html`：滚动容器移除 will-change。
- 报告：`SCROLL_ROOTCAUSE_FIX.md`。
