"""Launch the frozen KnowSubtle.exe (WC_HEADLESS) and run the same auth
checks as verify_live2.py. Confirms the packaged binary enforces auth.
"""
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, "Release-Package", "Core", "KnowSubtle", "KnowSubtle.exe")
DB = os.path.join(HERE, ".authtest", "live_exe.db")
if os.path.exists(DB):
    os.remove(DB)
# Windows-style path required by frozen exe (POSIX /d/... crashes mkdir)
DB_WIN = "D:/workbuddy workspace/2026-06-26-10-37-12/learning-agent-system/.authtest/live_exe.db"
APPDATA_LOCAL = os.path.join(HERE, ".authtest", "appdata_exe")

BASE = "http://127.0.0.1:8753"
env = dict(os.environ)
env["WC_HEADLESS"] = "1"
env["LAS_DB_PATH"] = DB_WIN
env["APPDATA"] = APPDATA_LOCAL
env["KS_FORCE_BROWSER"] = "0"

proc = subprocess.Popen(
    [EXE],
    env=env,
    cwd=HERE,
    stdout=open(os.path.join(HERE, ".authtest", "exe_stdout.log"), "w"),
    stderr=subprocess.STDOUT,
)
print("exe pid", proc.pid)


def wait_port(timeout=90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with socket.create_connection(("127.0.0.1", 8753), 1):
                return True
        except OSError:
            # fall back: read run.lock for actual port
            try:
                import glob
                locks = glob.glob(os.path.join(APPDATA_LOCAL, "KnowSubtle", "run.lock"))
                if locks:
                    txt = open(locks[0]).read()
                    import re
                    m = re.search(r'"port":\s*(\d+)', txt)
                    if m:
                        p = int(m.group(1))
                        with socket.create_connection(("127.0.0.1", p), 1):
                            global BASE
                            BASE = f"http://127.0.0.1:{p}"
                            return True
            except Exception:
                pass
            time.sleep(1)
    return False


def req(method, path, token=None, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        resp = urllib.request.urlopen(r, timeout=30)
        return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def check(name, got, expect):
    ok = got == expect
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: got {got} expect {expect}")
    return ok


try:
    if not wait_port():
        print("EXE SERVER FAILED TO START — dumping stdout log:")
        try:
            print(open(os.path.join(HERE, ".authtest", "exe_stdout.log")).read()[-2000:])
        except Exception:
            pass
        sys.exit(1)
    print("exe server up at", BASE)

    import random
    uname = "exetest_" + str(random.randint(100000, 999999))
    pw = "Password123"
    results = []

    s, b = req("POST", "/api/auth/register", body={
        "username": uname, "email": uname + "@example.com", "password": pw, "display_name": uname})
    results.append(check("register", s, 200))

    s, b = req("POST", "/api/auth/login", body={"username": uname, "password": pw, "remember": False})
    tok1 = json.loads(b).get("token")
    results.append(check("login1", s, 200))

    results.append(check("profile(tok1)", req("GET", "/api/auth/profile", token=tok1)[0], 200))
    s, b = req("GET", "/api/auth/me", token=tok1)
    results.append(check("me(tok1) authenticated", (s, json.loads(b).get("authenticated")), (200, True)))

    s, b = req("POST", "/api/auth/login", body={"username": uname, "password": pw, "remember": False})
    tok2 = json.loads(b).get("token")
    results.append(check("login2", s, 200))

    results.append(check("profile(tok1) revoked->401", req("GET", "/api/auth/profile", token=tok1)[0], 401))
    results.append(check("profile(tok2) still 200", req("GET", "/api/auth/profile", token=tok2)[0], 200))

    results.append(check("logout-all(tok2)", req("POST", "/api/auth/logout-all", token=tok2)[0], 200))
    results.append(check("profile(tok1) after logout-all->401", req("GET", "/api/auth/profile", token=tok1)[0], 401))
    results.append(check("profile(tok2) after logout-all->401", req("GET", "/api/auth/profile", token=tok2)[0], 401))

    results.append(check("change-password no token->401", req("POST", "/api/auth/change-password",
                        body={"old_password": pw, "new_password": "NewPass456"})[0], 401))

    results.append(check("chat no token->401", req("POST", "/api/chat/agent", body={"message": "hi"})[0], 401))
    results.append(check("config POST no token->401", req("POST", "/api/config/llm",
                        body={"base_url": "", "api_key": "", "model": ""})[0], 401))
    results.append(check("config GET no token->401", req("GET", "/api/config/llm")[0], 401))

    s, b = req("POST", "/api/auth/login", body={"username": uname, "password": pw, "remember": False})
    tok3 = json.loads(b).get("token")
    results.append(check("login3 (fresh valid tok)", s, 200))
    results.append(check("profile(tok3) valid->200", req("GET", "/api/auth/profile", token=tok3)[0], 200))
    results.append(check("chat with tok, no LLM->400", req("POST", "/api/chat/agent",
                        token=tok3, body={"message": "hi"})[0], 400))
    results.append(check("chat with tok, empty msg->400", req("POST", "/api/chat/agent",
                        token=tok3, body={"message": ""})[0], 400))

    passed = sum(results)
    total = len(results)
    print(f"\n=== EXE: {passed}/{total} checks passed ===")
finally:
    try:
        proc.send_signal(signal.SIGTERM)
    except Exception:
        pass
    try:
        proc.wait(timeout=8)
    except Exception:
        proc.kill()
