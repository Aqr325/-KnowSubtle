#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KnowSubtle 全功能验证脚本：覆盖全部 API 端点 + 完整 AI 流水线 + DB CRUD。

用法：python verify_all.py [BASE_URL]
依赖：仅标准库 (urllib/json)。运行前需先启动服务。
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
results = []


def call(method, path, body=None):
    url = BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                j = json.loads(raw)
            except Exception:
                j = None
            return resp.status, j, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            j = json.loads(raw)
        except Exception:
            j = None
        return e.code, j, raw
    except Exception as e:  # 连接失败等
        return -1, None, str(e)


def check(name, method, path, body=None, expect=200, validator=None, phase="A"):
    status, j, raw = call(method, path, body)
    ok = (status == expect)
    note = ""
    if ok and validator is not None:
        try:
            vok, vnote = validator(status, j, raw)
        except Exception as e:
            vok, vnote = False, f"validator error: {e}"
        ok = vok
        note = vnote
    else:
        if not ok:
            note = f"HTTP {status}"
            if isinstance(j, dict):
                note += " " + str(j)[:200]
    results.append({"phase": phase, "name": name, "ok": ok,
                    "status": status, "note": note})
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {phase} {name}  (HTTP {status}) {note}")
    return ok, status, j


# =====================================================================
# Phase A：健康检查 + 无会话演示端点（应返回 200 演示数据，不依赖 DB 写入）
# =====================================================================
print("\n===== Phase A: 基础/演示端点 =====")
check("health", "GET", "/api/health", validator=lambda s, j, r: (j.get("version") == "3.0.0", f"v={j.get('version')}"), phase="A")
check("planets", "GET", "/api/planets", validator=lambda s, j, r: (isinstance(j, list) and len(j) > 0, f"len={len(j) if isinstance(j,list) else '?'}"), phase="A")
check("progress/1", "GET", "/api/progress/1", validator=lambda s, j, r: (isinstance(j, dict) and "streak" in j, str(j)[:80]), phase="A")
check("tasks/1", "GET", "/api/tasks/1", validator=lambda s, j, r: (isinstance(j, list) and len(j) > 0, f"len={len(j)}"), phase="A")
check("achievements/1", "GET", "/api/achievements/1", validator=lambda s, j, r: (isinstance(j, list), f"len={len(j) if isinstance(j,list) else '?'}"), phase="A")
check("mistakes/1", "GET", "/api/mistakes/1", validator=lambda s, j, r: (isinstance(j, list), f"len={len(j)}"), phase="A")
check("knowledge-graph/1", "GET", "/api/knowledge-graph/1", validator=lambda s, j, r: (isinstance(j, dict) and "nodes" in j, str(j)[:80]), phase="A")
check("memory-curve", "GET", "/api/memory-curve", validator=lambda s, j, r: (isinstance(j, dict) and "dataPoints" in j, "ok"), phase="A")
check("suggestions/1", "GET", "/api/suggestions/1", validator=lambda s, j, r: (isinstance(j, list), f"len={len(j)}"), phase="A")
check("suggestions(global)", "GET", "/api/suggestions", validator=lambda s, j, r: (isinstance(j, list) and len(j) >= 5, f"len={len(j)}"), phase="A")
check("chat/agent(empty, 守卫400)", "POST", "/api/chat/agent", body={"agent": "tutor", "message": ""}, expect=400, validator=lambda s, j, r: (isinstance(j, dict) and "detail" in j, "ok"), phase="A")
check("tutor/chat(no-session)", "POST", "/api/tutor/chat", body={"message": "hi", "history": []}, validator=lambda s, j, r: (j.get("reply"), "ok"), phase="A")
check("vocab(GET)", "GET", "/api/vocab", validator=lambda s, j, r: (isinstance(j, list), f"len={len(j)}"), phase="A")
check("vocab/stats", "GET", "/api/vocab/stats", validator=lambda s, j, r: (isinstance(j, dict), str(j)[:80]), phase="A")
check("vocab/due-review", "GET", "/api/vocab/due-review", validator=lambda s, j, r: (isinstance(j, dict), "ok"), phase="A")
check("goals(GET)", "GET", "/api/goals", validator=lambda s, j, r: (isinstance(j, dict) and "daily_pomodoros" in j, str(j)[:80]), phase="A")
check("goals/today", "GET", "/api/goals/today", validator=lambda s, j, r: (isinstance(j, dict) and "progress" in j, "ok"), phase="A")
check("stats/dashboard", "GET", "/api/stats/dashboard", validator=lambda s, j, r: (isinstance(j, dict) and "summary" in j, "ok"), phase="A")
check("GET / (html)", "GET", "/", validator=lambda s, j, r: ("text/html" in (r.headers.get("Content-Type","") if hasattr(r,"headers") else "") or "<html" in (r or ""), "ok"))
check("landing.html", "GET", "/landing.html", validator=lambda s, j, r: (("text/html" in (r.headers.get("Content-Type","") if hasattr(r,"headers") else "")) or "<html" in (r or ""), "ok"))
check("profile.html", "GET", "/profile.html", validator=lambda s, j, r: (("text/html" in (r.headers.get("Content-Type","") if hasattr(r,"headers") else "")) or "<html" in (r or ""), "ok"))


# =====================================================================
# Phase B：词库 CRUD（全量）
# =====================================================================
print("\n===== Phase B: 词库 CRUD =====")
ok, _, j = check("vocab POST(english)", "POST", "/api/vocab",
                 body={"word": "verify_apple", "meaning": "苹果", "example": "an apple a day", "subject": "english"},
                 validator=lambda s, j, r: (j.get("status") == "ok" and "id" in j, str(j)), phase="B")
word_id = (j or {}).get("id")
check("vocab GET(subject=english)", "GET", "/api/vocab?subject=english",
      validator=lambda s, j, r: (any(w.get("word") == "verify_apple" for w in (j or [])), f"count={len(j or [])}"), phase="B")
if word_id:
    check("vocab PUT(mastered)", "PUT", f"/api/vocab/{word_id}",
          body={"mastered": True},
          validator=lambda s, j, r: (j.get("status") == "ok", str(j)), phase="B")
    check("vocab GET verify mastered", "GET", "/api/vocab?subject=english",
          validator=lambda s, j, r: (any(w.get("word") == "verify_apple" and w.get("mastered") is True for w in (j or [])), "mastered ok"), phase="B")
    check("vocab review", "POST", f"/api/vocab/{word_id}/review",
          validator=lambda s, j, r: (j.get("review_count", 0) >= 1, str(j)), phase="B")
check("vocab stats", "GET", "/api/vocab/stats",
      validator=lambda s, j, r: (isinstance(j, dict) and j.get("total", 0) >= 1, str(j)), phase="B")
check("vocab POST(dedup same subject)", "POST", "/api/vocab",
      body={"word": "verify_apple", "subject": "english"},
      validator=lambda s, j, r: (j.get("status") == "exists", str(j)), phase="B")
ok2, _, j2 = check("vocab POST(cross subject)", "POST", "/api/vocab",
                   body={"word": "verify_apple", "subject": "programming"},
                   validator=lambda s, j, r: (j.get("status") == "ok", str(j)), phase="B")
word_id2 = (j2 or {}).get("id")
if word_id:
    check("vocab DELETE", "DELETE", f"/api/vocab/{word_id}",
          validator=lambda s, j, r: (j.get("status") == "deleted", str(j)), phase="B")
    check("vocab GET after delete", "GET", "/api/vocab?subject=english",
          validator=lambda s, j, r: (not any(w.get("word") == "verify_apple" for w in (j or [])), "deleted ok"), phase="B")
if word_id2:
    check("vocab DELETE(cross)", "DELETE", f"/api/vocab/{word_id2}",
          validator=lambda s, j, r: (j.get("status") == "deleted", str(j)), phase="B")


# =====================================================================
# Phase C：每日目标 CRUD
# =====================================================================
print("\n===== Phase C: 目标 CRUD =====")
check("goals PUT", "PUT", "/api/goals",
      body={"daily_pomodoros": 6, "daily_words": 30, "daily_minutes": 90},
      validator=lambda s, j, r: (j.get("daily_pomodoros") == 6, str(j)), phase="C")
check("goals GET(after)", "GET", "/api/goals",
      validator=lambda s, j, r: (j.get("daily_pomodoros") == 6 and j.get("daily_words") == 30, str(j)), phase="C")
# 捕获进度基线：端点为「累加」语义（修复并发丢更新），断言增量而非精确值，
# 这样无论库是否全新都能正确验证（before + delta == after）
_, _, jb = check("goals/today(baseline)", "GET", "/api/goals/today",
      validator=lambda s, j, r: (isinstance(j, dict) and "progress" in j, "ok"), phase="C")
_base = (jb or {}).get("progress", {}) if isinstance(jb, dict) else {}
_base_pomo = int(_base.get("pomodoros_done", 0) or 0)
_base_words = int(_base.get("words_learned", 0) or 0)
_base_mins = int(_base.get("minutes_studied", 0) or 0)
check("goals/today progress(+)", "POST", "/api/goals/today/progress",
      body={"pomodoros": 2, "words": 10, "minutes": 25},
      validator=lambda s, j, r: (j.get("status") == "ok", str(j)), phase="C")
okg, _, jg = check("goals/today(after)", "GET", "/api/goals/today",
      validator=lambda s, j, r: (
          j.get("progress", {}).get("pomodoros_done", 0) == _base_pomo + 2 and
          j.get("progress", {}).get("words_learned", 0) == _base_words + 10 and
          j.get("progress", {}).get("minutes_studied", 0) == _base_mins + 25,
          str(j.get("progress"))), phase="C")


# =====================================================================
# Phase D：完整 AI 流水线（建目标→等完成→依赖会话端点）
# =====================================================================
print("\n===== Phase D: 完整 AI 流水线 =====")
okd, _, jd = check("sessions POST(create)", "POST", "/api/sessions",
                   body={"goal": "学习大学英语四级核心词汇3200词，掌握词根词缀和常见搭配"},
                   validator=lambda s, j, r: (j.get("status") == "processing", str(j)), phase="D")

# 轮询等待流水线完成
done = False
sid = None
for i in range(60):  # 最多 ~5 分钟
    st, sj, _ = call("GET", "/api/session/status")
    if isinstance(sj, dict):
        phase_val = sj.get("current_phase")
        if sid is None and sj.get("session_id"):
            sid = sj.get("session_id")
        if phase_val == "completed":
            done = True
            print(f"  pipeline completed after ~{i*5}s (session={sid})")
            break
        if phase_val == "error":
            print(f"  pipeline ERROR: {sj}")
            break
    time.sleep(5)
check("pipeline completed", "GET", "/api/session/status",
      validator=lambda s, j, r: (j.get("current_phase") == "completed", f"phase={j.get('current_phase')}"), phase="D")

if done or sid:
    check("sessions LIST", "GET", "/api/sessions",
          validator=lambda s, j, r: (isinstance(j, list) and len(j) >= 1, f"len={len(j) if isinstance(j,list) else '?'}"), phase="D")
    if sid:
        check("session DETAIL", "GET", f"/api/sessions/{sid}",
              validator=lambda s, j, r: (isinstance(j, dict) and j.get("session_id") == sid, "ok"), phase="D")
    check("session STATUS summary", "GET", "/api/session/status",
          validator=lambda s, j, r: (j.get("has_learning_path") is True or j.get("has_profile") is True, str({k: j.get(k) for k in ["has_profile","has_diagnosis","has_learning_path"]})), phase="D")
    # 依赖会话端点（走真实 ctx）
    check("planets(after session)", "GET", "/api/planets",
          validator=lambda s, j, r: (isinstance(j, list) and len(j) >= 1 and j[0].get("name") == "当前学习目标" if j else False, f"len={len(j) if isinstance(j,list) else '?'}"), phase="D")
    check("progress/1(after)", "GET", "/api/progress/1", validator=lambda s, j, r: (isinstance(j, dict), "ok"), phase="D")
    check("tasks/1(after)", "GET", "/api/tasks/1", validator=lambda s, j, r: (isinstance(j, list), f"len={len(j)}"), phase="D")
    check("tasks toggle", "POST", "/api/tasks/1/1/toggle",
          validator=lambda s, j, r: (j.get("status") == "toggled", str(j)), phase="D")
    check("achievements/1(after)", "GET", "/api/achievements/1", validator=lambda s, j, r: (isinstance(j, list), f"len={len(j)}"), phase="D")
    check("knowledge-graph/1(after)", "GET", "/api/knowledge-graph/1", validator=lambda s, j, r: (isinstance(j, dict), "ok"), phase="D")
    check("tutor/chat(after)", "POST", "/api/tutor/chat", body={"message": "怎么高效记单词", "history": []},
          validator=lambda s, j, r: (j.get("reply"), "ok"), phase="D")
    check("chat/agent tutor (守卫400)", "POST", "/api/chat/agent", body={"agent": "tutor", "message": "解释一下词根 bio", "history": []},
          expect=400, validator=lambda s, j, r: (isinstance(j, dict) and "detail" in j, "ok"), phase="D")
    check("chat/agent planner (守卫400)", "POST", "/api/chat/agent", body={"agent": "planner", "message": ""},
          expect=400, validator=lambda s, j, r: (isinstance(j, dict) and "detail" in j, "ok"), phase="D")
    check("chat/agent evaluator (守卫400)", "POST", "/api/chat/agent", body={"agent": "evaluator", "message": ""},
          expect=400, validator=lambda s, j, r: (isinstance(j, dict) and "detail" in j, "ok"), phase="D")
    check("exercises POST", "POST", "/api/exercises", body={"answer": "bio means life, e.g. biology"},
          validator=lambda s, j, r: (isinstance(j, dict), "ok"), phase="D")
    check("exercises LIST", "GET", "/api/exercises", validator=lambda s, j, r: (isinstance(j, list), f"len={len(j)}"), phase="D")
    check("report-card", "GET", "/api/report-card", validator=lambda s, j, r: (isinstance(j, dict), "ok"), phase="D")


# =====================================================================
# 汇总
# =====================================================================
print("\n===== 汇总 =====")
passed = sum(1 for r in results if r["ok"])
failed = [r for r in results if not r["ok"]]
print(f"总计 {len(results)} 项，通过 {passed}，失败 {len(failed)}")
if failed:
    print("失败项：")
    for r in failed:
        print(f"  - [{r['phase']}] {r['name']}  HTTP {r['status']}  {r['note']}")
    sys.exit(1)
print("全部通过 [ALL PASS]")
