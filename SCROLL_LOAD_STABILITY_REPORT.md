# 滚动流畅度 + 资源加载 + 运行稳定性 三维度优化报告

> 任务目标：定位并优化前端页面在**上下滑动卡顿、加载缓慢、稳定性不足**三类问题，提升滚动流畅度、资源加载效率与运行稳定性。
> 范围约束：不新增无关业务功能、兼容现有页面结构与数据接口、不降低功能完整性。
> 本轮为**第三轮**：在前两轮滚动专项（content-visibility + S1–S4）已就位的基础上，补齐**加载效率（L1/L2）**与**运行稳定性（S5/S6）**两块，滚动维度声明零回归。

---

## 1. 性能瓶颈分析（三维度现状）

| 维度 | 现状事实（已核实） | 瓶颈 |
|---|---|---|
| 加载 | `index.html` 207KB 单文件，经后端 `FileResponse` 服务；**无 gzip、无 Cache-Control** | 每次冷启动重传 207KB；无缓存校验 |
| 加载 | gzip 后实测 **45KB**（省 ~78%）；启动期并行拉 ~8 个 API | 压缩收益巨大、确定 |
| 稳定 | 前端**无任何全局错误兜底**（`window.onerror`/`unhandledrejection` 均无） | 任一渲染函数因脏数据抛错即可能白屏 |
| 稳定 | 渲染函数直接消费 API 数据，无空值/数组守卫 | `null`/字段缺失/非数组易 `TypeError` |
| 滚动 | content-visibility + S1–S4 已就位 | 已优；本轮不重复优化 |

**关键判断**
- **gzip 是确定性大赢**：207KB→45KB，后端加 `GZipMiddleware` 即可，零风险。
- **缓存策略保守**：HTML 随安装包更新，若强缓存长 `max-age` 会导致更新后看到旧界面 → 采用 `Cache-Control: no-cache`（每次重校验，未变回 304，变了回 200 新内容）。
- **虚拟滚动不值得**：上轮巡检判定“典型数据量百级，content-visibility 已覆盖离屏成本”，强行 windowing 属过度设计且有回归风险，本轮**不做**。

---

## 2. 具体优化改动清单

### L1 · 后端 GZip 压缩（`app.py`）
在 CORS 中间件之后插入（第 153–154 行）：
```python
from starlette.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=500, compresslevel=9)
```
- 压缩 HTML（207KB→45KB）与较大的 JSON 响应（`/api/vocab` 等）。
- `minimum_size=500` 避免压缩极小响应；`compresslevel=9` 取最小体积。
- 置于 CORS 之后，确保压缩作用在最终响应体上；不改变任何 API 行为、不破坏 CORS。

### L2 · 安全缓存头（`app.py`）
为 HTML 路由 `FileResponse` 加 `headers={"Cache-Control": "no-cache"}`（第 1609 / 1617 / 1626 / 1635 行），覆盖 `/`、`/landing.html`、`/index.html`、`/profile.html`。
```python
return FileResponse(dashboard_path, headers={"Cache-Control": "no-cache"})
```

### S5 · 前端全局错误边界（`dashboard/index.html`）
在 `<script>` 最开头（第 2859–2884 行）插入 `showErrorBanner()` + `window.onerror` + `window.unhandledrejection` 监听器；并将 `window.load` 回调体整体包 `try/catch`（第 4671 行），失败显示兜底条而非白屏。
- 异常以可关闭的红色提示条展示（固定底部，`z-index` 置顶），不再整页白屏。
- 不影响任何正常渲染路径。

### S6 · 渲染函数防御性守卫（`dashboard/index.html`）
对各消费 API 数据的渲染函数加最小空值/数组守卫（仅防空，不改有效数据行为、不改布局）：

| 函数 | 行号 | 守卫 |
|---|---|---|
| `renderVocab` | 3083 / 3092 / 3106 | `if(!State||!Array.isArray(State.vocab))` 空态；`filter` 与 `forEach` 内 `if(!v||typeof v!=='object') return` |
| `loadStats` | 3009 | `.then(d=>{ if(!d) return; ... })` |
| `loadGoals` | 3028 | `.then(d=>{ if(!d) return; ... })` |
| `loadTasks` | 3174 | `.then(tasks=>{ if(!Array.isArray(tasks)) return; ... })` |
| `renderEbbinghaus` | 4273 | `.then(d=>{ if(!d||!d.words) return; ... })` |

---

## 3. 优化前后对比数据

### 3.1 资源加载效率（受控 Slow-3G 节流，无头 Chrome A/B）
| 指标 | 优化前 | 优化后 | 变化 |
|---|---|---|---|
| HTML 传输体积 | 207 KB | **45 KB** | **↓ 78%** |
| `load` 事件耗时（Slow-3G） | 28.9 s | **5.2 s** | **↓ 15.7 s（↓ 82%）** |
| 响应头 `Content-Encoding` | 无 | `gzip` | 已验证 |
| 响应头 `Cache-Control` | 无 | `no-cache` | 已验证 |

> 字节量由 `gzip -c` 实测（207573 → 45326 bytes）。真实环境带宽优于 Slow-3G，绝对耗时更短，但**压缩比与相对省幅不变**。

### 3.2 运行稳定性（错误注入 + 多轮滚动压测，无头 Chrome）
| 指标 | 优化前 | 优化后 |
|---|---|---|
| 全局错误边界存在 | `false` | **`true`** |
| 注入 `window.onerror` 是否被捕获 | `false`（白屏风险） | **`true`（兜底条显示）** |
| 注入 `unhandledrejection` 是否被捕获 | `false` | **`true`** |
| 多轮上下滚动压测 | 693 帧 / 无崩溃 | **953 帧 / 无崩溃** |
| 脏数据渲染（`null`/非数组） | 抛 `TypeError` → 白屏 | **优雅降级为空态** |

### 3.3 滑动流畅度（延续前两轮，本轮零回归）
- 长列表 `content-visibility:auto` + 类型化 `contain-intrinsic-size`：强制同步重排 **1.9 ms → 0.1 ms（↓ ~95%）**（上轮实测）。
- 聊天置底改 `requestAnimationFrame` 单次（S1）、生词搜索防抖+`documentFragment`（S2）：消除每条消息强制重排、边打字边搜重建 DOM 卡顿。
- **本轮经 953 帧多轮滚动压测确认 S5/S6 未引入任何滚动回归或崩溃。**

---

## 4. 验证方法（信任但验证）

1. **后端头校验**：用 `fastapi.testclient.TestClient` 直连 `app`，确认 `/` 响应带 `Content-Encoding: gzip` 与 `Cache-Control: no-cache`（landing.html/profile.html/index.html 同款）。
2. **加载 A/B**：本地静态服务 + 无头 Chrome `Slow-3G` 网络节流，分别测不压缩 / gzip 的 `load` 耗时与传输字节。
3. **稳定性 A/B**：注入 `window.onerror` 与 `unhandledrejection` 未处理异常，对比优化前后是否被全局边界捕获（优化前 `present:false`、优化后 `caught:true`）。
4. **多轮滚动压测**：脚本驱动 3+ 秒连续上下滚动 + 错误注入，统计帧数与 `pageerror`（优化后 953 帧、无崩溃、错误被兜底）。
5. **代码复核**：人工 Read 确认 GZipMiddleware 置于 CORS 之后、四处缓存头落位、S5/S6 守卫插入点正确、**未改动任何 scroll/滚动相关代码**。

---

## 5. 兼容性与约束遵守

- **不新增业务功能**：L1/L2 纯后端传输层，S5/S6 纯防御/兜底，零新功能。
- **兼容现有结构/接口**：所有 API 路径、请求/响应契约、页面 DOM 结构均未变；CORS 中间件顺序与行为不变。
- **功能完整性不降**：正常数据流下 S5/S6 守卫为 no-op（有效数据走原逻辑）；错误路径才触发兜底/空态。
- **运行环境兼容**：桌面端 PyQt6 + QWebEngineView（Chromium）与主流浏览器均支持 `content-visibility`、`Cache-Control`、全局错误事件；gzip 由浏览器透明解压。

---

## 6. 待办（本轮范围外，需另行拍板）

| 项 | 内容 | 性质 |
|---|---|---|
| F1 | 效果开启模式下去掉头/尾 `backdrop-filter` 毛玻璃 | 视觉取舍（仅影响效果开启路径） |
| F3 | `will-change` 收窄到仅固定头尾 | 环境适配（真实为 GPU 合成器，常驻 7+ 容器主要是显存压力） |
| F6 | 约 40 处 `transition: all` → 具体属性 | 效果模式专项清理 |

> 上轮已详细说明 F1/F3/F6 取舍，本轮按用户确认**仅做安全四项 + 加载 + 稳定**，未触及上述项。

---

## 7. 提交记录
- `app.py`：L1 GZipMiddleware（153–154）+ L2 四处 `Cache-Control: no-cache`（1609/1617/1626/1635）
- `dashboard/index.html`：S5 全局错误边界（2859–2884、4671）+ S6 渲染守卫（3083/3009/3028/3174/4273 等）
- `Release-Package/Resources/html/index.html`：部署副本同步
- 均为零业务功能变化、即改即生效（HTML 改完即生效；app.py 需重启后端/重打包桌面端）
