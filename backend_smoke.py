#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KnowSubtle 后端全端点健康冒烟测试（backend_smoke.py）

按真实路由逐个驱动后端，覆盖 e2e_walk 未触及的"孤儿端点"（planets/progress/
mistakes/knowledge-graph/memory-curve/suggestions/achievements/report-card/
exercises/sessions/tutor-chat/chat-agent 等），确认 demo 模式下：
  1) 所有 GET/POST 端点不崩溃（无 500 意外）；
  2) 无会话时预期返回 400/404 的端点行为正确（非 500）；
  3) 创建会话并跑完 demo 流水线后，有会话端点均可用。

仅依赖标准库 urllib，接收 base_url 参数。
用法：python backend_smoke.py http://127.0.0.1:8000
"""
import sys
import json
import time
import urllib.request
import urllib.error

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
results = []


def req(method, path, body=None):
    url = BASE + path
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            code = resp.getcode()
            raw = resp.read().decode("utf-8", "replace")
            try:
                j = json.loads(raw)
            except Exception:
                j = None
            return j, code, None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            j = json.loads(raw)
        except Exception:
            j = None
        return j, e.code, None
    except Exception as e:  # 网络级错误（连接拒绝等）
        return None, 0, str(e)


def check(name, cond, detail=""):
    results.append((name, cond, detail))
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" -- {detail}" if detail else ""))


# ---------- 阶段 A：无会话 GET ----------
no_session_gets = [
    "/api/health", "/api/planets", "/api/progress/1", "/api/tasks/1",
    "/api/achievements/1", "/api/mistakes/1", "/api/knowledge-graph/1",
    "/api/memory-curve", "/api/suggestions/1", "/api/suggestions",
    "/api/sessions", "/api/session/status",
    "/api/vocab", "/api/vocab/stats", "/api/vocab/due-review",
    "/api/goals", "/api/goals/today", "/api/stats/dashboard",
    # 以下 GET 在无会话时预期 400，仍属"非 500"健康范畴
    "/api/report-card",
]
for p in no_session_gets:
    j, c, err = req("GET", p)
    ok = (c in (200, 400, 404)) and err is None
    check(f"GET {p}", ok, f"code={c}" + (f" err={err}" if err else ""))

# ---------- 阶段 A：无会话 POST ----------
j, c, err = req("POST", "/api/tutor/chat", {"message": "", "history": []})
check("POST /api/tutor/chat (无会话)", c == 200 and err is None, f"code={c}")

j, c, err = req("POST", "/api/chat/agent", {"agent": "tutor", "message": "hi", "history": []})
check("POST /api/chat/agent (未配置LLM, 守卫返回400)", c == 400 and err is None, f"code={c}")

j, c, err = req("POST", "/api/exercises", {"answer": "x"})
check("POST /api/exercises (无会话, 预期400非500)", c == 400 and err is None, f"code={c}")

# ---------- 阶段 B：创建会话 + 轮询完成 ----------
j, c, err = req("POST", "/api/sessions", {"goal": "学习 Python 基础语法与数据结构"})
check("POST /api/sessions (创建会话)", c == 200 and err is None, f"code={c}")

sid = None
for _ in range(90):
    j, c, err = req("GET", "/api/session/status")
    if c == 200 and isinstance(j, dict):
        phase = j.get("current_phase")
        # demo 流水线完成态可能为 COMPLETED / REPORT_GENERATED 等
        if phase in ("COMPLETED", "DONE", "REPORT_GENERATED", "FINISHED") or j.get("status") == "completed":
            break
    time.sleep(1)

j, c, err = req("GET", "/api/sessions")
if c == 200 and isinstance(j, list) and j:
    sid = j[0].get("session_id") or j[0].get("id")
check("会话已创建并可列出", bool(sid), f"sid={sid}")

# ---------- 阶段 C：有会话端点 ----------
j, c, err = req("GET", "/api/report-card")
check("GET /api/report-card (有会话)", c == 200 and err is None, f"code={c}")

j, c, err = req("GET", "/api/exercises")
check("GET /api/exercises (有会话)", c == 200 and err is None, f"code={c}")

j, c, err = req("POST", "/api/exercises", {"answer": "42"})
check("POST /api/exercises (有会话, demo占位)", c == 200 and err is None, f"code={c}")

j, c, err = req("GET", "/api/achievements/1")
check("GET /api/achievements/1 (有会话)", c == 200 and err is None, f"code={c}")

j, c, err = req("GET", "/api/mistakes/1")
check("GET /api/mistakes/1 (有会话)", c == 200 and err is None, f"code={c}")

j, c, err = req("GET", "/api/knowledge-graph/1")
check("GET /api/knowledge-graph/1 (有会话)", c == 200 and err is None, f"code={c}")

j, c, err = req("GET", "/api/progress/1")
check("GET /api/progress/1 (有会话)", c == 200 and err is None, f"code={c}")

j, c, err = req("GET", "/api/suggestions/1")
check("GET /api/suggestions/1 (有会话)", c == 200 and err is None, f"code={c}")

j, c, err = req("POST", "/api/tutor/chat", {"message": "什么是变量", "history": []})
check("POST /api/tutor/chat (有会话, demo占位)", c == 200 and err is None, f"code={c}")

j, c, err = req("POST", "/api/chat/agent", {"agent": "planner", "message": "下一步学什么", "history": []})
check("POST /api/chat/agent planner (未配置LLM, 守卫返回400)", c == 400 and err is None, f"code={c}")

j, c, err = req("POST", "/api/chat/agent", {"agent": "evaluator", "message": "我做得怎么样", "history": []})
check("POST /api/chat/agent evaluator (未配置LLM, 守卫返回400)", c == 400 and err is None, f"code={c}")

# ---------- 阶段 D：session/{id} ----------
if sid:
    j, c, err = req("GET", f"/api/sessions/{sid}")
    check(f"GET /api/sessions/{sid}", c == 200 and err is None, f"code={c}")
j, c, err = req("GET", "/api/sessions/nonexistent_id_xyz")
check("GET /api/sessions/不存在 (预期404)", c == 404, f"code={c}")

# ---------- 汇总 ----------
fails = [r for r in results if not r[1]]
print(f"\n总计 {len(results)} 项, {len(results) - len(fails)} 通过, {len(fails)} 失败")
if fails:
    print("失败项:")
    for n, _, d in fails:
        print(f"  - {n}: {d}")
    sys.exit(1)
print("BACKEND SMOKE ALL PASS")
