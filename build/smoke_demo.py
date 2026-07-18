"""Smoke test: 验证 DEMO_MODE 下离线流水线 + 持久化往返正确（无需真实大模型）。"""
import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # 使 local_metagpt 与 learning_agent_system 可被导入
import local_metagpt.stub  # noqa: F401  # 触发 stub，设置 METAGPT_STUBBED

from learning_agent_system.orchestrator import TeamOrchestrator, DEMO_MODE

assert DEMO_MODE, "DEMO_MODE 应为 True（stub 已设置环境变量）"


async def main():
    with tempfile.TemporaryDirectory() as td:
        orch = TeamOrchestrator(storage_dir=td)

        # 1) 离线流水线
        ctx = await orch.run_full_pipeline("测试：掌握 Python 基础")
        assert ctx.learning_goal is not None, "learning_goal 缺失"
        assert ctx.diagnosis is not None, "diagnosis 缺失"
        assert ctx.learning_path is not None, "learning_path 缺失"
        print("[ok] run_full_pipeline (demo) ->", ctx.session_id, ctx.current_phase)

        # 2) 评测（demo）
        res = await orch.run_evaluation("我的答案")
        assert res.exercise_id, "exercise_id 缺失"
        assert res.is_correct is False
        print("[ok] run_evaluation (demo) ->", res.exercise_id)

        # 3) 辅导循环（demo）
        sess_list = await orch.run_tutor_loop(1)
        assert sess_list and sess_list[0].round_number == 1
        print("[ok] run_tutor_loop (demo) ->", sess_list[0].round_number)

        # 4) 成就/错题/连续天数等此前遗漏字段写入
        ctx.achievements.append(type(ctx.achievements[0])() if False else None) if False else None
        # 手动塞入一个成就对象验证 to_dict/from_dict
        from learning_agent_system.schema import Achievement
        ctx.achievements.append(Achievement(id="a1", title="首次学习", description="demo"))
        ctx.study_streak.current_streak = 3
        orch._save_checkpoint()

        # 5) 持久化往返
        loaded = orch.load_session(ctx.session_id)
        assert loaded is not None, "load_session 失败"
        assert loaded.achievements and loaded.achievements[0].title == "首次学习", "achievements 未持久化"
        assert loaded.study_streak.current_streak == 3, "study_streak 未持久化（此前 bug）"
        print("[ok] checkpoint 往返 -> achievements=%d streak=%d" % (
            len(loaded.achievements), loaded.study_streak.current_streak))

        # 6) 损坏文件安全降级
        bad = Path(td) / "checkpoint_bad.json"
        bad.write_text("{ this is not json", encoding="utf-8")
        assert orch.load_session("bad") is None, "损坏文件应安全返回 None"
        assert not bad.exists(), "损坏文件应被清理"
        print("[ok] 损坏 checkpoint 安全降级")

    print("\nALL DEMO SMOKE TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
