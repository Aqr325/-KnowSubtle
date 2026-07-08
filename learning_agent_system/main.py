"""
main.py — 学习智能体系统 CLI 入口

用法：
  python -m learning_agent_system.main --goal "学习Python"
  python -m learning_agent_system.main --resume <session_id>
  python -m learning_agent_system.main --status
  python -m learning_agent_system.main --list-sessions
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# 确保项目根在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from learning_agent_system.orchestrator import TeamOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("cli")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="learning-agent-system",
        description="基于 MetaGPT 的个性化资源生成与学习多智能体系统",
    )
    parser.add_argument(
        "--goal", "-g",
        type=str,
        default=None,
        help="学习目标描述，例如 '学习Python基础语法'"
    )
    parser.add_argument(
        "--resume", "-r",
        type=str,
        default=None,
        help="恢复指定 session_id 的会话"
    )
    parser.add_argument(
        "--status", "-s",
        action="store_true",
        help="查看当前会话状态"
    )
    parser.add_argument(
        "--list-sessions", "-l",
        action="store_true",
        help="列出所有历史会话"
    )
    parser.add_argument(
        "--storage",
        type=str,
        default=".learning_memory",
        help="存储目录路径 (默认: .learning_memory)"
    )
    parser.add_argument(
        "--tutor-rounds",
        type=int,
        default=3,
        help="辅导对话轮次 (默认: 3)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="输出详细日志"
    )
    return parser


async def async_main(args: argparse.Namespace) -> None:
    orchestrator = TeamOrchestrator(storage_dir=args.storage)

    # 查看状态
    if args.status:
        if args.resume:
            orchestrator.load_session(args.resume)
        summary = orchestrator.get_summary()
        logger.info("Session Status:")
        for k, v in summary.items():
            logger.info(f"  {k}: {v}")
        return

    # 列出会话
    if args.list_sessions:
        sessions = orchestrator.list_sessions()
        if not sessions:
            logger.info("No historical sessions found.")
            return
        logger.info(f"Found {len(sessions)} sessions:")
        for sid in sessions:
            ctx = orchestrator.load_session(sid)
            if ctx:
                logger.info(f"  [{sid}] phase={ctx.current_phase.value} goal={ctx.learning_goal.description[:40] if ctx.learning_goal else 'N/A'}...")
        return

    # 恢复会话
    if args.resume:
        ctx = orchestrator.load_session(args.resume)
        if ctx is None:
            logger.error(f"Session not found: {args.resume}")
            sys.exit(1)
        logger.info(f"Resumed session: {ctx.session_id}, phase={ctx.current_phase.value}")

        if ctx.current_phase.value in ("profiling", "diagnosis", "resource", "planning"):
            logger.info("Continuing pipeline from current phase...")
            ctx = await orchestrator.run_full_pipeline(ctx.learning_goal.description)
        else:
            logger.info(f"Session is in {ctx.current_phase.value} phase, no pipeline rerun needed.")
        return

    # 新建学习会话
    if not args.goal:
        logger.error("Please provide a learning goal with --goal/-g")
        sys.exit(1)

    logger.info(f"Starting full pipeline for goal: {args.goal}")

    # 执行完整流水线
    ctx = await orchestrator.run_full_pipeline(args.goal)

    logger.info("=" * 50)
    logger.info("Pipeline Complete!")
    logger.info(f"Session ID: {ctx.session_id}")
    logger.info(f"Learner Profile: {'✓' if ctx.learner_profile else '✗'}")
    logger.info(f"Knowledge Diagnosis: {'✓' if ctx.diagnosis else '✗'}")
    logger.info(f"Resource Plan: {'✓' if ctx.resource_plan else '✗'}")
    logger.info(f"Learning Path: {'✓' if ctx.learning_path else '✗'}")
    logger.info("=" * 50)

    # 辅导对话
    logger.info(f"Starting tutor loop ({args.tutor_rounds} rounds)...")
    sessions = await orchestrator.run_tutor_loop(rounds=args.tutor_rounds)
    logger.info(f"Completed {len(sessions)} tutor rounds.")

    logger.info("Done! Use --resume to restore this session.")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()