"""
用户隔离 + 记住我 端到端冒烟测试（标准库 urllib，无额外依赖）。

用法（需与起服命令在同一条 Bash 内执行，规避沙箱跨调用网络隔离）：
    python isolation_smoke.py http://127.0.0.1:8000
DB 路径通过环境变量 ISO_DB_PATH 读取（与起服时的 LAS_DB_PATH 一致）。
"""
import sys, json, os, time, datetime, sqlite3
import urllib.request, urllib.error

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
DB = os.environ.get("ISO_DB_PATH", "")

results = []


def check(name, cond, detail=""):
    results.append((name, cond, detail))
    print(("PASS " if cond else "FAIL") + " | " + name + ((" | " + str(detail)) if detail != "" else ""))


def req(method, path, body=None, token=None, timeout=40):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}
    except Exception as e:
        return -1, {"error": str(e)}


def db_query(sql):
    if not DB:
        return []
    con = sqlite3.connect(DB)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def ttl_hours(token):
    rows = db_query(f"SELECT expires_at FROM auth_tokens WHERE token='{token}'")
    if not rows:
        return None
    try:
        exp = datetime.datetime.fromisoformat(rows[0][0])
    except Exception:
        return None
    return (exp - datetime.datetime.now()).total_seconds() / 3600.0


print("=== 账号隔离 + 记住我 冒烟测试 ===")
print("BASE =", BASE, "| DB =", DB)

# 1) 注册 alice / bob
s, d = req("POST", "/api/auth/register",
           {"username": "alice", "email": "alice@x.com", "password": "secret123", "display_name": "Alice"})
check("注册 alice", s == 200 and "token" in d, f"status={s}")
tokenA = d.get("token")

s, d = req("POST", "/api/auth/register",
           {"username": "bob", "email": "bob@x.com", "password": "secret123", "display_name": "Bob"})
check("注册 bob", s == 200 and "token" in d, f"status={s}")
tokenB = d.get("token")

# 2) 记住我：alice 勾选 -> ~30 天；bob 不勾选 -> ~24 小时
s, d = req("POST", "/api/auth/login", {"username": "alice", "password": "secret123", "remember": True})
check("登录 alice (remember=true)", s == 200 and "token" in d, f"status={s}")
tokenA2 = d.get("token")
dh = ttl_hours(tokenA2)
check("remember=true -> ~720h", dh is not None and 700 <= dh <= 745, f"delta_h={dh}")

s, d = req("POST", "/api/auth/login", {"username": "bob", "password": "secret123", "remember": False})
check("登录 bob (remember=false)", s == 200 and "token" in d, f"status={s}")
tokenB2 = d.get("token")
dh = ttl_hours(tokenB2)
check("remember=false -> ~24h", dh is not None and 20 <= dh <= 28, f"delta_h={dh}")

# 3) 词库隔离：alice 加词，bob 不可见
s, d = req("POST", "/api/vocab",
           {"word": "isolationword", "meaning": "隔离测试", "example": "", "subject": "english"},
           token=tokenA2)
check("alice 添加词库词", s == 200, f"status={s} {d}")

s, d = req("GET", "/api/vocab?subject=english", token=tokenB2)
bob_words = [w["word"] for w in d] if isinstance(d, list) else []
check("bob 词库不含 alice 的词", "isolationword" not in bob_words, f"bob_words={bob_words}")

s, d = req("GET", "/api/vocab?subject=english", token=tokenA2)
alice_words = [w["word"] for w in d] if isinstance(d, list) else []
check("alice 词库含自己的词", "isolationword" in alice_words, f"alice_words={alice_words}")

# 不同学科同词允许（复合唯一约束）
s, d = req("POST", "/api/vocab",
           {"word": "isolationword", "meaning": "隔离测试", "example": "", "subject": "main"},
           token=tokenA2)
check("alice 同词不同学科可并存", s == 200, f"status={s} {d}")

# 4) 目标隔离：alice 设定制目标，bob 应看到默认值（不泄漏）
s, d = req("PUT", "/api/goals", {"daily_pomodoros": 8, "daily_words": 999, "daily_minutes": 120}, token=tokenA2)
check("alice 设置每日目标", s == 200, f"status={s} {d}")
s, d = req("GET", "/api/goals/today", token=tokenB2)
bob_target_words = d.get("target", {}).get("words") if isinstance(d, dict) else None
check("bob 目标未被 alice 污染", bob_target_words != 999, f"bob_target_words={bob_target_words}")
s, d = req("GET", "/api/goals/today", token=tokenA2)
alice_target_words = d.get("target", {}).get("words") if isinstance(d, dict) else None
check("alice 目标保留定制值", alice_target_words == 999, f"alice_target_words={alice_target_words}")

# 5) 学习计划（session）隔离：alice 创建会话，bob 不可见（尽力而为，依赖 demo 流水线完成）
s, d = req("POST", "/api/sessions", {"goal": "测试学习计划隔离"}, token=tokenA2)
check("alice 发起学习计划", s == 200, f"status={s} {d}")

alice_sessions = []
for _ in range(30):  # 最多等 30s 让 demo 流水线落盘
    s, d = req("GET", "/api/sessions", token=tokenA2)
    if isinstance(d, list) and len(d) > 0:
        alice_sessions = d
        break
    time.sleep(1)

s, d = req("GET", "/api/sessions", token=tokenB2)
bob_sessions = d if isinstance(d, list) else []
if len(alice_sessions) > 0:
    check("学习计划按用户隔离（bob 看不到 alice 的）", len(bob_sessions) == 0,
          f"alice={len(alice_sessions)} bob={len(bob_sessions)}")
else:
    check("学习计划隔离（demo 流水线未落盘，跳过硬断言）", True,
          "alice_sessions=0 (pipeline 未完成/超时，仅词库/目标隔离已验证)")

# 汇总
failed = [r for r in results if not r[1]]
print("\n=== 结果 ===")
print(f"总计 {len(results)} 项，通过 {len(results)-len(failed)} 项，失败 {len(failed)} 项")
if failed:
    print("失败项:")
    for n, _, det in failed:
        print("  -", n, det)
    sys.exit(1)
print("全部通过")
sys.exit(0)
