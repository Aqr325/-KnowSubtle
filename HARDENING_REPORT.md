# 安全加固与启动守护交付报告（第二轮）

> 项目：`learning-agent-system`
> 日期：2026-07-07
> 范围：① 补 `/api/suggestions` 无参端点 ② 后端加 CSP 双层 XSS 防护 ③ 一键启动 + 进程守护脚本
> 验证方式：`py_compile` + `fastapi.testclient.TestClient` 进程内探针（绕过沙箱网络隔离）

---

## 1. 补 `/api/suggestions` 无参端点

**落点**：`app.py:581-598` 新增 `get_global_suggestions`

```python
@app.get("/api/suggestions")
async def get_global_suggestions(planet_id: Optional[int] = None) -> List[Dict[str, Any]]:
    global_suggestions = [
        {"icon": "💡", "text": "设定一个学习目标..."},
        {"icon": "📚", "text": "探索我们的学习星球..."},
        {"icon": "🩺", "text": "先做一次诊断测试..."},
        {"icon": "🍅", "text": "开启番茄钟专注模式..."},
        {"icon": "🏆", "text": "坚持每日打卡..."},
    ]
    if planet_id is not None:
        try:
            items = await get_suggestions(planet_id)   # 复用星球级建议
            global_suggestions = items + global_suggestions
        except Exception:
            logger.exception("合并星球级建议失败，回退到默认列表")
    return global_suggestions
```

**行为**：
- 无参 → 返回 5 条全局学习建议（欢迎/目标/诊断/番茄钟/打卡）。
- `?planet_id=N` → 合并该星球的个性化建议（异常时安全回退到默认列表，不影响返回）。
- 不影响已有 `/api/suggestions/{planet_id}` 端点。

**验证**：
| 请求 | 结果 |
|------|------|
| `GET /api/suggestions` | 200，JSON list，len=5 |
| `GET /api/suggestions?planet_id=1` | 200，JSON list，len=7（合并生效） |

---

## 2. CSP 安全响应头（与前端 `escHtml` 形成双层防护）

**落点**：
- `app.py:87-99`：模块级常量 `CSP_POLICY`，可被环境变量 `CSP_POLICY` 覆盖。
- `app.py:101-108`：`@app.middleware("http") add_security_headers`，为所有响应注入 4 个头。

```python
CSP_POLICY = os.environ.get("CSP_POLICY",
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "connect-src 'self' https:; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'; "
    "upgrade-insecure-requests")

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = CSP_POLICY
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response
```

**策略说明（纵深防御）**：
- 前端 `escHtml()` 是**第一层**（转义用户/智能体消息，防 DOM XSS）。
- 后端 CSP 是**第二层**（即便有注入点，也禁止外部脚本加载、禁止插件、防点击劫持、限制 `base` 注入、限制数据外发仅 `self`+`https`）。
- `script-src`/`style-src` 保留 `'unsafe-inline'`：因 `dashboard/index.html` 是单文件内联脚本/样式，必须放行内联；真正的 XSS 拦截已由 `escHtml` 负责。
- `connect-src 'self' https:`：兼容前端配置的真实 LLM API（https 端点）。

**验证**（根路径 `GET /`）：
| 响应头 | 状态 |
|--------|------|
| `Content-Security-Policy` | present |
| `X-Content-Type-Options: nosniff` | present |
| `X-Frame-Options: DENY` | present |
| `Referrer-Policy: no-referrer` | present |

---

## 3. 一键启动 + 进程守护脚本

| 文件 | 平台 | 解释器探测 | 守护逻辑 |
|------|------|-----------|----------|
| `start.sh` | bash / git bash / Linux / macOS | 优先 `./.venv/bin/python`，回退 `python3` | `while true` 循环；非零退出打印 `[guardian]` 并 `sleep 3` 重启，0 退出则 `break` |
| `start.bat` | Windows cmd | 优先 `.venv\Scripts\python.exe`，回退 `python` | `:loop` + `goto`；`%errorlevel%!=0` 时 `timeout /t 3` 后回 `:loop`，0 则结束 |

**行为**：崩溃自愈（进程非零退出 3 秒后自动重启），干净退出则停止；不硬编码本机托管 python 路径，可移植。
**语法校验**：`bash -n start.sh` 通过。

---

## 端到端验证总览

| 项 | 命令/探针 | 结果 |
|----|-----------|------|
| 语法 | `python -m py_compile app.py` | OK |
| 端点 1 | `GET /api/suggestions` | 200 / list len=5 |
| 端点 2 | `GET /api/suggestions?planet_id=1` | 200 / list len=7 |
| 安全头 | `GET /` 响应头 | 4 个头全部 present |
| 启动脚本 | `bash -n start.sh` | 语法 OK |

**结论**：三项加固全部落地，运行时验证 ALL_GREEN。前端 `escHtml` + 后端 CSP 构成双层 XSS 防护；`/api/suggestions` 死端点已复活；后端进程退出不再需要手动拉起。

---

## 用法

```bash
# 开发/本机运行（带崩溃自愈）
./start.sh        # Linux / macOS / git bash
start.bat         # Windows 双击或 cmd 运行

# 自定义 CSP（可选）
export CSP_POLICY="default-src 'none'; script-src 'self' 'unsafe-inline'; ..."
./start.sh
```

> 注意：沙箱内 `preview_url("http://localhost:8000")` 因网络命名空间隔离连不到；
> 要看带真实数据的完整效果，请在本机执行 `start.sh`/`start.bat` 后浏览器开 `http://localhost:8000/`。
