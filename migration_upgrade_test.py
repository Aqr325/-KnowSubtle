"""
迁移升级路径测试：模拟「旧版数据库」（daily_* 表用 date 单列唯一约束，
SQLite 会自动建 sqlite_autoindex_* 索引，DROP INDEX 无法删除），验证 init_db()
的表重建回退逻辑能成功迁移，且不丢数据、新复合唯一约束就位。

用法（单条 Bash，无需起服）：
    python migration_upgrade_test.py
通过环境变量 LAS_DB_PATH 指定测试库（Windows 绝对路径）。
"""
import asyncio
import os
import sys
import tempfile

PROJ = os.path.dirname(os.path.abspath(__file__))
WINPWD = sys.argv[1] if len(sys.argv) > 1 else None
if not WINPWD:
    WINPWD = os.getcwd()
OLD_DB = os.path.join(WINPWD, "_old_db_test", "knowsubtle.db").replace("/", "\\")
os.environ["LAS_DB_PATH"] = OLD_DB
os.makedirs(os.path.dirname(OLD_DB), exist_ok=True)
if os.path.exists(OLD_DB):
    os.remove(OLD_DB)

sys.path.insert(0, PROJ)
from sqlalchemy import text
from learning_agent_system.database import session as sesh


async def main():
    # 1) 用「旧版 schema」预建 6 张表（模拟已发布版本的数据库）
    engine = await sesh.get_engine()
    old_ddl = [
        "CREATE TABLE sessions(id integer primary key, session_id text unique, "
        "current_phase text, created_at text, updated_at text, metadata_json text)",
        "CREATE TABLE vocab(id integer primary key, word text, meaning text, notes text, "
        "example text, source text, subject text, mastered integer, review_count integer, "
        "last_reviewed text, word_lower text, created_at text)",
        "CREATE UNIQUE INDEX uq_vocab_word_subject ON vocab(word, subject)",
        "CREATE TABLE daily_stats(id integer primary key, date text unique, minutes real)",
        "CREATE TABLE daily_words(id integer primary key, date text unique, new_words integer, total_words integer)",
        "CREATE TABLE daily_accuracy(id integer primary key, date text unique, accuracy real)",
        "CREATE TABLE daily_goals(id integer primary key, date text unique, pomodoros_target integer, "
        "words_target integer, minutes_target integer, pomodoros_done integer, words_done integer, minutes_done integer)",
    ]
    async with engine.begin() as conn:
        for d in old_ddl:
            await conn.execute(text(d))
        # 旧数据
        await conn.execute(text("INSERT INTO sessions(session_id,metadata_json) VALUES('old-sess-1','{}')"))
        await conn.execute(text("INSERT INTO vocab(word,subject,word_lower) VALUES('apple','english','apple')"))
        await conn.execute(text("INSERT INTO daily_stats(date,minutes) VALUES('2026-01-01',42)"))
        await conn.execute(text("INSERT INTO daily_goals(date,words_target) VALUES('0000-00-00',20)"))
    print("[pre] 旧库已建，含旧 autoindex")

    # 2) 运行真实 init_db()（模拟升级）
    await sesh.init_db()

    # 3) 校验迁移结果
    problems = []
    async with engine.begin() as conn:
        for t in ("sessions", "vocab", "daily_stats", "daily_words", "daily_accuracy", "daily_goals"):
            cols = [r[1] for r in (await conn.execute(text(f"PRAGMA table_info({t})"))).fetchall()]
            if "user_id" not in cols:
                problems.append(f"{t} 缺少 user_id 列")
            rows = (await conn.execute(text(f"SELECT * FROM {t}"))).fetchall()
            print(f"[check] {t}: cols={cols} | rows={len(rows)}")
        # 校验唯一索引
        vs_idx = (await conn.execute(text("PRAGMA index_list(vocab)"))).fetchall()
        if not any(i[1] == "uq_vocab_word_subject_user" for i in vs_idx):
            problems.append("vocab 缺少 uq_vocab_word_subject_user")
        for t in ("daily_stats", "daily_words", "daily_accuracy", "daily_goals"):
            idxs = (await conn.execute(text(f"PRAGMA index_list({t})"))).fetchall()
            if not any(i[1] == f"uq_{t}_date_user" for i in idxs):
                problems.append(f"{t} 缺少 uq_{t}_date_user")
        # 校验数据未丢
        n_sess = (await conn.execute(text("SELECT count(*) FROM sessions"))).fetchone()[0]
        n_vocab = (await conn.execute(text("SELECT count(*) FROM vocab"))).fetchone()[0]
        n_stats = (await conn.execute(text("SELECT count(*) FROM daily_stats"))).fetchone()[0]
        if n_sess != 1 or n_vocab != 1 or n_stats != 1:
            problems.append(f"数据丢失: sess={n_sess} vocab={n_vocab} stats={n_stats}")

    if problems:
        print("MIGRATION UPGRADE FAIL:")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("MIGRATION UPGRADE OK (旧库升级成功，autoindex 重建回退生效，数据无丢失)")


asyncio.run(main())
