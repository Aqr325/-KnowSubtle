# ── Demo stub: replace metagpt with local stub (no real AI) ──
import sys
import os
import logging
from pathlib import Path
_stub_path = str(Path(__file__).parent / "local_metagpt")
if _stub_path not in sys.path:
    sys.path.insert(0, _stub_path)
_stub_ok = False
try:
    import local_metagpt.stub  # noqa: F401 — side-effect: patches metagpt + sets METAGPT_STUBBED=1
    _stub_ok = True
except Exception as _e:
    _stub_ok = False
    # 不吞静默：显式警告，避免开发者在离线桌面端无感知回退到真实 metagpt
    logging.getLogger("app").warning(
        "[STUB-LOAD-FAIL] local_metagpt.stub failed to load (%s: %s). "
        "Desktop app will fall back to real metagpt (requires API Key + network). "
        "Verify local_metagpt/ is bundled in the PyInstaller build.", type(_e).__name__, _e
    )

"""
KnowSubtle Learning Universe - FastAPI Backend
Personalized Resource Generation & Learning Multi-Agent System
重构后：所有 Mock API 端点替换为 TeamOrchestrator 真实调用
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from typing import List, Dict, Any, Optional
from functools import partial
import asyncio
import json
import logging
import os
from pathlib import Path

from learning_agent_system.orchestrator import TeamOrchestrator, Phase, SessionContext
from pydantic import BaseModel, Field, field_validator

from learning_agent_system.schema import (
    LearningGoal,
    LearnerProfile,
    KnowledgeDiagnosis,
    ResourcePlan,
    LearningPath,
    TutorSession,
    ExerciseResult,
    Exercise,
    KnowledgeStatus,
    Achievement,
    MistakeRecord,
    StudyStreak,
    ReportCard,
    MultiGoalProgress,
    ModuleStatus,
)


# ── Pydantic Request Models ──
class CreateSessionRequest(BaseModel):
    goal: str


class ExerciseAnswerRequest(BaseModel):
    answer: str


class TutorChatMessage(BaseModel):
    message: str = ""
    history: list = []

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app")

# ── FastAPI App ──
app = FastAPI(
    title="KnowSubtle Learning Universe API",
    description="个性化资源生成与学习多智能体系统",
    version="3.0.0"
)

# ── 数据库初始化 ──
from learning_agent_system.database.session import init_db, close_db, get_async_session

@app.on_event("startup")
async def startup_db():
    await init_db()

@app.on_event("shutdown")
async def shutdown_db():
    await close_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000", "http://localhost:8001", "http://localhost:8002",
        "http://127.0.0.1:8000", "http://127.0.0.1:8001", "http://127.0.0.1:8002",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

from fastapi.responses import JSONResponse
from fastapi import Request

@app.exception_handler(Exception)
async def _unhandled_exception(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})

CSP_POLICY = os.environ.get(
    "CSP_POLICY",
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "connect-src 'self' https:; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'; "
    "upgrade-insecure-requests"
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = CSP_POLICY
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response

# ── 路径解析（开发模式 / PyInstaller 打包后通用）──
def _app_root() -> Path:
    # PyInstaller 单文件夹打包时 sys.executable 为 Core/KnowSubtle/KnowSubtle.exe
    # （--onedir 会在 --name 外再套一层目录）；单文件/直接 Core/KnowSubtle/KnowSubtle.exe 则为上一层。
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _find_up(start: Path, *rel) -> "Path | None":
    """从 start 逐级向上查找存在的 rel 路径（最多 6 层）。"""
    cur = Path(start).resolve()
    for _ in range(6):
        cand = cur.joinpath(*rel)
        if cand.is_dir():
            return cand
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    return None


def _resolve_resource_dir() -> Path:
    # 打包布局随方式浮动，不能硬编码层级：
    #   onedir (--onedir):  <dist>/main/KnowSubtle.exe  -> 向上两级到 Release-Package/Resources/html
    #   直接 Core/KnowSubtle/KnowSubtle.exe: 向上一级到 Release-Package/Resources/html
    #   NSIS 分发:          Release-Package/Resources/html 与 Core 同级
    # 因此从 _app_root() 向上逐级查找包含 html 的 Resources 目录。
    found = _find_up(_app_root(), "Resources", "html")
    if found:
        return found
    env = os.environ.get("LAS_RESOURCE_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent / "dashboard"


def _resolve_config_dir() -> Path:
    found = _find_up(_app_root(), "Resources", "Config") or _find_up(_app_root(), "Config")
    if found:
        return found
    if getattr(sys, "frozen", False):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        d = Path(base) / "KnowSubtle" / "Config"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path(__file__).resolve().parent / "config"


def _resolve_data_dir() -> Path:
    env = os.environ.get("LAS_DATA_DIR")
    if env:
        d = Path(env)
        d.mkdir(parents=True, exist_ok=True)
        return d
    if getattr(sys, "frozen", False):
        # 安装到 Program Files 时程序目录不可写，落到用户 AppData
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        d = Path(base) / "KnowSubtle" / "Data"
        d.mkdir(parents=True, exist_ok=True)
        return d
    d = Path(__file__).resolve().parent / ".learning_memory"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── 全局状态 ──
APP_ROOT = _app_root()
RESOURCE_DIR = _resolve_resource_dir()
CONFIG_DIR = _resolve_config_dir()
STORAGE_DIR = _resolve_data_dir()


def load_app_config() -> dict:
    """加载 Config/config.json；缺失时写入默认配置。"""
    cfg = {"app_name": "KnowSubtle Learning Universe", "port": 8000, "host": "127.0.0.1"}
    cfg_path = CONFIG_DIR / "config.json"
    if cfg_path.exists():
        try:
            cfg.update(json.loads(cfg_path.read_text(encoding="utf-8")))
        except Exception as e:
            logger.warning(f"加载 config.json 失败，使用默认配置: {e}")
    else:
        try:
            cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    return cfg

# 全局 orchestrator 实例（懒初始化）
_orchestrator: Optional[TeamOrchestrator] = None
_current_session_id: Optional[str] = None

# 后台流水线任务集合（防止被 GC，并监控异常）
_background_tasks: set = set()


def get_orchestrator() -> TeamOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = TeamOrchestrator(storage_dir=str(STORAGE_DIR))
    return _orchestrator


# ── Helper: 检查 session 是否有实质内容 ──
def _has_meaningful_session() -> bool:
    """检查是否存在有实质数据的 session"""
    orch = get_orchestrator()
    sessions = orch.list_sessions()
    if not sessions:
        return False
    ctx = orch.load_session(sessions[0])
    if not ctx:
        return False
    # session 有实质内容：画像、诊断、或学习路径中至少有一项
    return bool(ctx.learning_goal or ctx.learner_profile or ctx.diagnosis or
                ctx.resource_plan or ctx.learning_path or ctx.exercise_results or
                ctx.mistake_records or ctx.achievements)


def _load_current_ctx():
    """加载当前会话上下文：优先用 _current_session_id，否则回退到最新会话。

    统一替代散落的 `_load_current_ctx()`，
    避免多会话下各数据端点指向不同 session 的不一致问题。
    """
    orch = get_orchestrator()
    sessions = orch.list_sessions()
    sid = _current_session_id or (sessions[0] if sessions else None)
    return orch.load_session(sid) if sid else None


# ── Helper: Pipeline 后台任务 ──
async def _run_pipeline(goal: str) -> str:
    """后台执行完整流水线，返回 session_id"""
    orch = get_orchestrator()
    ctx = await orch.run_full_pipeline(goal)
    global _current_session_id
    _current_session_id = ctx.session_id
    return ctx.session_id


# ── Helper: 序列化 Pydantic 模型 ──
def serialize(obj):
    """通用序列化：Pydantic model → dict, dict → dict, 否则 → str"""
    if obj is None:
        return None
    # dict 直接递归处理每个值
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    # Pydantic v2 模型
    if hasattr(obj, "model_dump"):
        d = obj.model_dump()
        return {k: serialize(v) for k, v in d.items()}
    # 带 to_dict 的对象（如 SessionContext）
    if hasattr(obj, "to_dict"):
        return serialize(obj.to_dict())
    # 列表
    if isinstance(obj, list):
        return [serialize(item) for item in obj]
    # 基本类型直接返回
    if isinstance(obj, (str, int, float, bool)):
        return obj
    return str(obj)


def serialize_list(lst):
    return [serialize(item) for item in lst]


# ── Helper: 星球 → 学习目标映射 ──
PLANET_TO_GOAL = {
    1: "学习大学英语四级核心词汇3200词，掌握词根词缀和常见搭配",
    2: "学习大学英语六级进阶词汇4800词，提升阅读理解能力",
    3: "学习考研英语核心词汇5500词，为研究生入学考试做准备",
    4: "学习医学英语专业术语2800词，掌握医学术语词根词缀",
}


# ====================================================================
# Planet Endpoints
# ====================================================================

@app.get("/api/planets")
async def get_planets() -> List[Dict[str, Any]]:
    """获取所有学习星球"""
    if _has_meaningful_session():
        orch = get_orchestrator()
        ctx = _load_current_ctx()
        if ctx and ctx.learning_goal:
            return [{
                "id": 1,
                "name": "当前学习目标",
                "desc": ctx.learning_goal.description[:30],
                "totalWords": 100,
                "learnedPercent": 0,
                "icon": "📚",
                "theme": ctx.learning_goal.domain or "custom",
            }]
    # 无有效 session 时返回默认列表（带演示进度数据）
    return [
        {"id": 1, "name": "四级词汇", "desc": "大学英语四级核心词库", "totalWords": 3200, "learnedPercent": 35, "icon": "📚", "theme": "vocab"},
        {"id": 2, "name": "六级词汇", "desc": "大学英语六级进阶词库", "totalWords": 4800, "learnedPercent": 12, "icon": "🎯", "theme": "cet6"},
        {"id": 3, "name": "考研英语", "desc": "研究生入学考试词汇", "totalWords": 5500, "learnedPercent": 5, "icon": "🎓", "theme": "post"},
        {"id": 4, "name": "医学英语", "desc": "医学专业术语与词根词缀", "totalWords": 2800, "learnedPercent": 0, "icon": "🩺", "theme": "med"}
    ]


# ====================================================================
# Progress Endpoints
# ====================================================================

@app.get("/api/progress/{planet_id}")
async def get_progress(planet_id: int) -> Dict[str, Any]:
    """获取星球学习进度"""
    if not _has_meaningful_session():
        defaults = {
            1: {"todayGoal": "12/50", "weekGoal": "45/350", "reviewCount": 156, "streak": 3, "accuracy": 72},
            2: {"todayGoal": "0/50", "weekGoal": "18/350", "reviewCount": 62, "streak": 0, "accuracy": 65},
            3: {"todayGoal": "0/50", "weekGoal": "6/350", "reviewCount": 28, "streak": 0, "accuracy": 58},
            4: {"todayGoal": "0/50", "weekGoal": "0/350", "reviewCount": 0, "streak": 0, "accuracy": 0},
        }
        return defaults.get(planet_id, defaults[1])

    orch = get_orchestrator()
    ctx = _load_current_ctx()
    if not ctx:
        return {"todayGoal": "0/50", "weekGoal": "0/350", "reviewCount": 0, "streak": 0, "accuracy": 0}

    streak = ctx.study_streak
    exercise_count = len(ctx.exercise_results)
    correct_count = sum(1 for r in ctx.exercise_results if r.is_correct)
    accuracy = round(correct_count / exercise_count * 100, 1) if exercise_count > 0 else 0

    return {
        "todayGoal": f"{correct_count}/{max(exercise_count, 50)}",
        "weekGoal": f"{exercise_count}/{350}",
        "reviewCount": exercise_count,
        "streak": streak.current_streak if ctx.study_streak else 0,
        "accuracy": accuracy,
    }


# ====================================================================
# Tasks Endpoints
# ====================================================================

@app.get("/api/tasks/{planet_id}")
async def get_tasks(planet_id: int) -> List[Dict[str, Any]]:
    """获取今日任务（从 learning_path.modules 生成）"""
    default_tasks = [
        {"id": 1, "text": "复习昨日内容", "done": False, "duration": "15分钟"},
        {"id": 2, "text": "新学 Unit 1", "done": False, "duration": "10分钟"},
        {"id": 3, "text": "新学 Unit 2", "done": False, "duration": "10分钟"},
        {"id": 4, "text": "随堂测验", "done": False, "duration": "8分钟"},
        {"id": 5, "text": "错题整理与收藏", "done": False, "duration": "5分钟"},
    ]

    if not _has_meaningful_session():
        return default_tasks

    orch = get_orchestrator()
    ctx = _load_current_ctx()
    if not ctx or not ctx.learning_path:
        return default_tasks

    tasks = []
    for i, module in enumerate(ctx.learning_path.modules):
        tasks.append({
            "id": i + 1,
            "text": module.title,
            "done": module.status == ModuleStatus.COMPLETED,
            "duration": f"{int(module.estimated_hours * 60)}分钟",
        })

    if not tasks:
        tasks = [
            {"id": 1, "text": "复习昨日内容", "done": False, "duration": "15分钟"},
            {"id": 2, "text": "新学模块", "done": False, "duration": "30分钟"},
            {"id": 3, "text": "随堂测验", "done": False, "duration": "10分钟"},
        ]

    return tasks


@app.post("/api/tasks/{planet_id}/{task_id}/toggle")
async def toggle_task(planet_id: int, task_id: int) -> Dict[str, Any]:
    """切换任务完成状态（更新 checkpoint）"""
    if not _has_meaningful_session():
        raise HTTPException(status_code=400, detail="没有活跃的学习会话。请先创建一个学习目标。")

    orch = get_orchestrator()
    ctx = _load_current_ctx()
    if not ctx or not ctx.learning_path:
        raise HTTPException(status_code=400, detail="学习路径尚未生成，请先运行学习流水线。")

    if task_id < 1 or task_id > len(ctx.learning_path.modules):
        raise HTTPException(status_code=404, detail=f"Task #{task_id} not found")
    task = ctx.learning_path.modules[task_id - 1]

    # 切换状态（使用枚举值，避免字符串赋值类型问题）
    if task.status == ModuleStatus.COMPLETED:
        task.status = ModuleStatus.PENDING
    else:
        task.status = ModuleStatus.COMPLETED
        orch.record_study_activity()

    orch._save_checkpoint()
    return {"status": "toggled", "planet_id": planet_id, "task_id": task_id, "new_status": task.status.value}


# ====================================================================
# Tutor / Chat Endpoints
# ====================================================================

@app.post("/api/tutor/chat")
async def tutor_chat(request: TutorChatMessage) -> Dict[str, Any]:
    """AI 导师对话端点（调用 orchestrator tutor loop）"""
    orch = get_orchestrator()
    message = request.message
    history = request.history

    if not _has_meaningful_session():
        return {
            "reply": "请先设定一个学习目标来激活学习系统。我可以帮您制定个性化的学习计划和资源推荐！",
            "suggestions": ["帮我制定学习计划", "推荐学习资料", "安排复习时间"],
        }

    ctx = _load_current_ctx()
    if not ctx or not ctx.learning_path:
        return {
            "reply": "学习路径尚未生成，请先运行完整学习流水线。",
            "suggestions": ["重新生成学习路径", "查看当前进度"],
        }

    try:
        tutor_session = await orch._run_tutor_round(len(ctx.tutor_sessions) + 1, history=history)
        ctx.tutor_sessions.append(tutor_session)
        orch._save_checkpoint()

        reply = tutor_session.explanation or "这是一段辅导回复。"
        suggestions = tutor_session.next_steps[:3] if tutor_session.next_steps else ["继续下一轮辅导", "查看错题", "复习薄弱知识点"]

        return {
            "reply": reply,
            "suggestions": suggestions,
        }
    except Exception as e:
        logger.error(f"Tutor chat failed: {e}")
        return {
            "reply": "导师服务暂时不可用，请稍后重试。",
            "suggestions": ["查看学习进度", "做一套练习题"],
        }


# ====================================================================
# Achievement Endpoints
# ====================================================================

@app.get("/api/achievements/{planet_id}")
async def get_achievements(planet_id: int) -> List[Dict[str, Any]]:
    """获取成就列表"""
    if not _has_meaningful_session():
        # 无有效 session 时返回预设成就池作为预览
        from learning_agent_system.actions.achievement_checker import ACHIEVEMENT_POOL
        return [serialize(a) for a in ACHIEVEMENT_POOL]

    orch = get_orchestrator()
    ctx = _load_current_ctx()
    if not ctx:
        from learning_agent_system.actions.achievement_checker import ACHIEVEMENT_POOL
        return [serialize(a) for a in ACHIEVEMENT_POOL]

    # 实时检测新成就（按 id 去重，避免 GET 幂等性缺失导致重复累加）
    check_result = orch._achievement_checker.check(streak=ctx.study_streak, results=ctx.exercise_results, mistakes=ctx.mistake_records)
    existing_ids = {a.id for a in ctx.achievements}
    for new_a in check_result.new_achievements:
        if new_a.id not in existing_ids:
            ctx.achievements.append(new_a)
            existing_ids.add(new_a.id)
    orch._save_checkpoint()

    # 序列化
    result = []
    for ach in ctx.achievements:
        serialized = serialize(ach)
        serialized["unlocked"] = bool(serialized.get("unlocked_at"))
        result.append(serialized)

    # 如果没有 achievements，返回预设池中的所有
    if not result:
        from learning_agent_system.actions.achievement_checker import ACHIEVEMENT_POOL
        result = [serialize(a) for a in ACHIEVEMENT_POOL]
        # 标记已解锁的
        for a in result:
            if a["id"] in [ach.id for ach in ctx.achievements]:
                a["unlocked"] = True

    return result


# ====================================================================
# Mistake Endpoints
# ====================================================================

@app.get("/api/mistakes/{planet_id}")
async def get_mistakes(planet_id: int) -> List[Dict[str, Any]]:
    """获取错题记录"""
    if not _has_meaningful_session():
        return []

    orch = get_orchestrator()
    ctx = _load_current_ctx()
    if not ctx:
        return []

    return serialize_list(ctx.mistake_records) if ctx.mistake_records else []


# ====================================================================
# Knowledge Graph Endpoint
# ====================================================================

@app.get("/api/knowledge-graph/{planet_id}")
async def get_knowledge_graph(planet_id: int) -> Dict[str, Any]:
    """获取知识图谱数据"""
    if not _has_meaningful_session():
        return {"nodes": [], "edges": [], "metadata": {}}

    orch = get_orchestrator()
    ctx = _load_current_ctx()
    if not ctx or not ctx.diagnosis:
        return {"nodes": [], "edges": [], "metadata": {}}

    # 准备知识状态
    status_list = []
    for topic, level in ctx.diagnosis.diagnosed_topics.items():
        status_list.append(KnowledgeStatus(topic=topic, mastery_level=level))

    # 生成图谱
    graph = orch._graph_generator.generate(status_list, None)
    ctx.graph_data = graph
    orch._save_checkpoint()

    return serialize(graph)


# ====================================================================
# Memory Curve Endpoint
# ====================================================================

@app.get("/api/memory-curve")
async def get_memory_curve() -> Dict[str, Any]:
    """获取艾宾浩斯记忆曲线数据（使用标准遗忘曲线公式计算）"""
    # 标准遗忘曲线：遗忘率 = 1 - e^(-t/τ)，τ ≈ 30天
    # 记忆保持率 = 100 * e^(-t/8) (无复习)
    import math

    def retention_without_review(days):
        """无复习的记忆保持率"""
        return round(max(5, 100 * math.exp(-days / 5)), 1)

    def retention_with_review(days):
        """有复习的记忆保持率（假设每 7 天复习一次）"""
        review_effect = min(0.7, days // 7 * 0.1)
        return round(max(55, 100 * math.exp(-(days - review_effect * days) / 10)), 1)

    intervals = [
        {"label": "当天", "days": 0},
        {"label": "1天后", "days": 1},
        {"label": "3天后", "days": 3},
        {"label": "7天后", "days": 7},
        {"label": "15天后", "days": 15},
        {"label": "30天后", "days": 30},
        {"label": "60天后", "days": 60},
    ]

    x_positions = [0, 80, 160, 250, 340, 410, 460]

    data_points = []
    with_review_points = []
    for i, interval in enumerate(intervals):
        data_points.append({
            "label": interval["label"],
            "retention": retention_without_review(interval["days"]),
            "x": x_positions[i],
            "y": round(20 + (100 - retention_without_review(interval["days"])) * 1.5, 1),
        })
        with_review_points.append({
            "label": interval["label"],
            "retention": retention_with_review(interval["days"]),
            "x": x_positions[i],
            "y": round(20 + (100 - retention_with_review(interval["days"])) * 1.2, 1),
        })

    return {
        "dataPoints": data_points,
        "withReview": with_review_points,
    }


# ====================================================================
# AI Suggestions Endpoint
# ====================================================================

@app.get("/api/suggestions/{planet_id}")
async def get_suggestions(planet_id: int) -> List[Dict[str, Any]]:
    """获取 AI 学习建议"""
    default_suggestions = [
        {"icon": "💡", "text": "设定一个学习目标，我将为您生成个性化的学习方案。"},
        {"icon": "📚", "text": "探索我们的学习星球，选择适合您的词库开始学习。"},
    ]

    suggestions = list(default_suggestions)

    if not _has_meaningful_session():
        return default_suggestions

    orch = get_orchestrator()
    ctx = _load_current_ctx()
    if not ctx:
        return default_suggestions

    # 基于 streak 的建议
    streak = ctx.study_streak
    if streak and streak.current_streak > 0:
        suggestions.append({
            "icon": "🔥",
            "text": f"连续学习 <strong>{streak.current_streak}天</strong>，继续保持！"
        })

    # 基于 weak_points 的建议
    if ctx.diagnosis and ctx.diagnosis.weak_points:
        weak = ctx.diagnosis.weak_points[:2]
        suggestions.append({
            "icon": "🎯",
            "text": f"以下知识点需要加强：<strong>{'、'.join(weak)}</strong>，建议优先复习。"
        })

    # 基于准确率的建议
    if ctx.exercise_results:
        correct = sum(1 for r in ctx.exercise_results if r.is_correct)
        total = len(ctx.exercise_results)
        acc = round(correct / total * 100)
        if acc < 60:
            suggestions.append({
                "icon": "📊",
                "text": f"当前练习正确率为 <strong>{acc}%</strong>，建议增加基础知识的练习量。"
            })
        else:
            suggestions.append({
                "icon": "📊",
                "text": f"当前练习正确率为 <strong>{acc}%</strong>，表现不错！"
            })

    # 基于错题的建议
    if ctx.mistake_records:
        suggestions.append({
            "icon": "📝",
            "text": f"您有 <strong>{len(ctx.mistake_records)}道</strong>错题需要复习，别忘了查看错题本。"
        })

    # 默认兜底建议
    if not suggestions:
        suggestions.append({
            "icon": "💡",
            "text": "根据您的学习路径，建议先完成 Unit 1 的新词学习。"
        })

    return suggestions


@app.get("/api/suggestions")
async def get_global_suggestions(planet_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """获取无参的全局学习建议；可选 planet_id 合并星球级建议"""
    global_suggestions = [
        {"icon": "💡", "text": "设定一个学习目标，我将为您生成个性化的学习方案。"},
        {"icon": "📚", "text": "探索我们的学习星球，选择适合您的词库开始学习。"},
        {"icon": "🩺", "text": "先做一次诊断测试，让我了解你的薄弱点并量身定制计划。"},
        {"icon": "🍅", "text": "开启番茄钟专注模式，每次 25 分钟高效吸收新词。"},
        {"icon": "🏆", "text": "坚持每日打卡，连续学习可解锁成就与专属奖励。"},
    ]

    if planet_id is not None:
        try:
            items = await get_suggestions(planet_id)
            global_suggestions = items + global_suggestions
        except Exception:
            logger.exception("合并星球级建议失败，回退到默认列表")
    return global_suggestions


# ====================================================================
# New: Session Management Endpoints
# ====================================================================

@app.post("/api/sessions")
async def create_session(request: Request) -> Dict[str, Any]:
    """创建新的学习会话（异步执行完整流水线）"""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体必须是有效的 JSON")
    description = body.get("goal", "")
    if not description:
        raise HTTPException(status_code=400, detail="请提供学习目标描述")
    if len(description) > 500:
        raise HTTPException(status_code=400, detail="学习目标描述不得超过 500 字符")

    # 启动后台任务执行流水线（保留引用 + 异常回调，避免静默失败）
    task = asyncio.create_task(_run_pipeline(description))
    _background_tasks.add(task)

    def _on_pipeline_done(t):
        _background_tasks.discard(t)
        if t.exception():
            err = str(t.exception())
            logger.error(f"Pipeline task failed: {err}")
            # 持久化 error 状态，使 GET /api/sessions 可感知失败，前端可据此展示错误
            try:
                orch = get_orchestrator()
                ctx = orch.context
                if ctx:
                    ctx.metadata["status"] = "error"
                    ctx.metadata["error"] = err
                    orch._save_checkpoint() if hasattr(orch, '_save_checkpoint') else None
            except Exception:
                pass

    task.add_done_callback(_on_pipeline_done)

    return {
        "status": "processing",
        "message": "学习流水线已启动。请通过 /api/session/status 查看进度。",
        "goal": description,
    }


@app.get("/api/sessions")
async def get_sessions() -> List[Dict[str, Any]]:
    """列出所有学习会话"""
    orch = get_orchestrator()
    sessions = orch.list_sessions()
    result = []
    for sid in sessions:
        ctx = orch.load_session(sid)
        if ctx:
            result.append(serialize(ctx.to_dict()))
    return result


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str) -> Dict[str, Any]:
    """获取指定会话详情"""
    orch = get_orchestrator()
    ctx = orch.load_session(session_id)
    if not ctx:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return serialize(ctx.to_dict())


@app.get("/api/session/status")
async def get_session_status() -> Dict[str, Any]:
    """获取当前会话摘要"""
    orch = get_orchestrator()
    return orch.get_summary()


# ====================================================================
# New: Report Card Endpoint
# ====================================================================

@app.get("/api/report-card")
async def get_report_card() -> Dict[str, Any]:
    """生成学习报告卡"""
    if not _has_meaningful_session():
        raise HTTPException(status_code=400, detail="没有活跃的学习会话。请先创建一个学习目标。")

    orch = get_orchestrator()
    ctx = _load_current_ctx()
    if not ctx:
        raise HTTPException(status_code=404, detail="会话不存在")

    try:
        report = await orch.generate_report_card()
        return serialize(report)
    except Exception as e:
        logger.error(f"Report card generation failed: {e}")
        raise HTTPException(status_code=500, detail="生成报告卡失败，请稍后重试")


# ====================================================================
# New: Exercise Submission Endpoint
# ====================================================================

@app.post("/api/exercises")
async def submit_exercise(answer: ExerciseAnswerRequest) -> Dict[str, Any]:
    """提交练习答案并获取评测结果"""
    if not _has_meaningful_session():
        raise HTTPException(status_code=400, detail="没有活跃的学习会话。请先创建一个学习目标。")

    orch = get_orchestrator()
    ctx = _load_current_ctx()
    if not ctx:
        raise HTTPException(status_code=404, detail="会话不存在")

    student_answer = answer.answer.strip()
    if not student_answer:
        raise HTTPException(status_code=400, detail="请提供答案内容")

    try:
        result = await orch.run_evaluation(student_answer)
        return serialize(result)
    except Exception as e:
        logger.error(f"Exercise evaluation failed: {e}")
        raise HTTPException(status_code=500, detail="练习评测失败，请稍后重试")


@app.get("/api/exercises")
async def get_exercises() -> List[Dict[str, Any]]:
    """获取练习记录列表"""
    if not _has_meaningful_session():
        return []

    orch = get_orchestrator()
    ctx = _load_current_ctx()
    if not ctx:
        return []

    return serialize_list(ctx.exercise_results)


# ── Chat Request Model ──
class AgentChatRequest(BaseModel):
    agent: str = "tutor"  # tutor | planner | evaluator
    message: str = ""
    history: list = []


@app.post("/api/chat/agent")
async def agent_chat(request: AgentChatRequest) -> Dict[str, Any]:
    """通用多智能体聊天端点"""
    agent_type = request.agent
    message = request.message
    history = request.history

    if not message or not message.strip():
        return {"reply": "请输入您的问题。", "agent": agent_type, "suggestions": []}

    if not _has_meaningful_session():
        agent_responses = {
            "tutor": "我是您的 AI 导师 Socrates。请先设定学习目标，我将为您开启苏格拉底式引导教学！",
            "planner": "我是学习规划师 Plato。请先运行完整学习流水线，我将为您定制个性化学习路径！",
            "evaluator": "我是练习评测师 Eva。请先开始学习并做一些练习，我将为您提供详细反馈！",
        }
        return {
            "reply": agent_responses.get(agent_type, "请先完成学习初始化。"),
            "agent": agent_type,
            "suggestions": [],
        }

    orch = get_orchestrator()
    ctx = _load_current_ctx()
    if not ctx:
        return {"reply": "会话数据未加载，请重新初始化学习系统。", "agent": agent_type, "suggestions": []}

    try:
        if agent_type == "tutor":
            # 导师：基于上下文进行问答辅导
            round_num = len(ctx.tutor_sessions) + 1
            tutor_session = await orch._run_tutor_round(round_num, history=history)
            ctx.tutor_sessions.append(tutor_session)
            orch._save_checkpoint()
            reply = tutor_session.explanation or "让我来为您解答这个问题。"
            suggestions = tutor_session.next_steps[:3] if tutor_session.next_steps else ["继续辅导", "查看学习进度"]

        elif agent_type == "planner":
            # 规划师：基于学习路径给出建议
            if ctx.learning_path and ctx.learning_path.modules:
                current_module = next(
                    (m for m in ctx.learning_path.modules if m.status.value != "completed"),
                    ctx.learning_path.modules[-1]
                )
                reply = (
                    f"根据您的学习路径规划，当前建议专注于：<strong>{current_module.title}</strong>\n\n"
                    f"预计耗时：{current_module.estimated_hours * 60:.0f} 分钟\n"
                    f"完成状态：{current_module.status.value}\n\n"
                    f"建议按计划逐步推进，先完成基础知识学习，再进行练习巩固。"
                )
                suggestions = ["查看详细学习路径", "跳转到下一个模块", "查看已完成模块"]
            else:
                reply = "您的学习路径尚未生成，请先运行完整学习流水线。"
                suggestions = ["运行完整流水线"]

        elif agent_type == "evaluator":
            # 评测师：提供练习建议
            exercise_count = len(ctx.exercise_results)
            correct_count = sum(1 for r in ctx.exercise_results if r.is_correct)
            accuracy = round(correct_count / exercise_count * 100, 1) if exercise_count > 0 else 0

            reply = (
                f"📊 **练习统计汇报**\n\n"
                f"- 总练习次数：{exercise_count}\n"
                f"- 正确次数：{correct_count}\n"
                f"- 准确率：{accuracy}%\n\n"
            )
            if exercise_count == 0:
                reply += "您还没有进行过练习，建议先从基础题目开始测试！"
                suggestions = ["开始第一套练习题"]
            elif accuracy >= 80:
                reply += "表现优秀！可以开始进阶知识点的练习。"
                suggestions = ["进阶练习", "查看错题本", "复习薄弱知识点"]
            elif accuracy >= 60:
                reply += "表现中等，建议重点复习错题本中的知识点。"
                suggestions = ["查看错题分析", "基础练习", "复习相关知识"]
            else:
                reply += "需要加强基础学习，建议重新学习薄弱知识点后再进行练习。"
                suggestions = ["复习基础知识", "查看诊断报告", "基础练习"]
        else:
            reply = f"未知智能体类型：{agent_type}"
            suggestions = []

        return {
            "reply": reply,
            "agent": agent_type,
            "suggestions": suggestions,
        }

    except Exception as e:
        logger.error(f"Agent chat ({agent_type}) failed: {e}")
        return {
            "reply": f"{agent_type} 服务暂时不可用，请稍后重试。",
            "agent": agent_type,
            "suggestions": ["刷新页面", "查看学习进度"],
        }


# ====================================================================
# Stats / Dashboard Analytics Endpoint
# ====================================================================

import random
import math
from datetime import datetime, timedelta

# 数据库查询替代 JSON 文件
from learning_agent_system.database.repo import StatsRepository, VocabRepository, DailyGoalRepository


@app.get("/api/stats/dashboard")
async def get_stats_dashboard() -> Dict[str, Any]:
    """学习分析仪表盘聚合数据"""
    async with get_async_session() as session:
        repo = StatsRepository(session)
        summary = await repo.get_dashboard_summary()

    orch = get_orchestrator()
    ctx = None
    if _has_meaningful_session():
        ctx = _load_current_ctx()

    streak = 0
    exercise_count = 0
    correct_count = 0
    if ctx:
        streak = ctx.study_streak.current_streak if ctx.study_streak else 0
        exercise_count = len(ctx.exercise_results)
        correct_count = sum(1 for r in ctx.exercise_results if r.is_correct)

    summary["summary"]["streak"] = streak
    summary["summary"]["exerciseCount"] = exercise_count
    summary["summary"]["correctCount"] = correct_count

    return summary


# ====================================================================
# Vocabulary / Word Collection Endpoint
# ====================================================================

class VocabEntry(BaseModel):
    word: str = Field(..., max_length=128)
    meaning: str = Field("", max_length=2000)
    notes: str = Field("", max_length=2000)
    example: str = Field("", max_length=2000)
    source: str = "manual"  # manual | tutor | exercise
    subject: str = "main"   # main | english | programming | history
    mastered: Optional[bool] = None


class VocabUpdateEntry(BaseModel):
    """更新模型：word 可选（前端“标记掌握”仅传 {mastered}，不应 422）。"""
    word: Optional[str] = None
    meaning: Optional[str] = None
    notes: Optional[str] = None
    example: Optional[str] = None
    source: Optional[str] = None
    subject: Optional[str] = None
    mastered: Optional[bool] = None


@app.get("/api/vocab")
async def get_vocab(subject: Optional[str] = None) -> List[Dict[str, Any]]:
    """获取收藏单词，可选按学科过滤"""
    async with get_async_session() as session:
        repo = VocabRepository(session)
        words = await repo.get_by_subject(subject)
    return [
        {
            "id": w.id,
            "word": w.word,
            "meaning": w.meaning,
            "notes": w.notes,
            "example": w.example,
            "source": w.source,
            "subject": w.subject,
            "mastered": w.mastered,
            "review_count": w.review_count,
            "created_at": w.created_at.isoformat() if w.created_at else "",
            "last_reviewed": w.last_reviewed,
        }
        for w in words
    ]


@app.post("/api/vocab")
async def add_vocab(entry: VocabEntry) -> Dict[str, Any]:
    """添加生词收藏（按学科去重）"""
    async with get_async_session() as session:
        repo = VocabRepository(session)
        word_obj, created = await repo.add(
            word=entry.word,
            meaning=entry.meaning,
            notes=entry.notes,
            example=entry.example,
            source=entry.source,
            subject=entry.subject,
        )
    if not created:
        return {"status": "exists", "word": entry.word, "message": "该单词已在该学科收藏"}
    return {"status": "ok", "word": entry.word, "id": word_obj.id}


@app.put("/api/vocab/{word_id}")
async def update_vocab(word_id: int, entry: VocabUpdateEntry) -> Dict[str, Any]:
    """更新单词笔记/掌握状态"""
    async with get_async_session() as session:
        repo = VocabRepository(session)
        v = await repo.get_by_id(word_id)
        if not v:
            raise HTTPException(status_code=404, detail=f"Word #{word_id} not found")

        updates = {}
        if entry.notes is not None:
            updates["notes"] = entry.notes
        if entry.meaning is not None:
            updates["meaning"] = entry.meaning
        if entry.example is not None:
            updates["example"] = entry.example
        if entry.source is not None:
            updates["source"] = entry.source
        if entry.subject is not None:
            updates["subject"] = entry.subject
        if entry.mastered is not None:
            updates["mastered"] = entry.mastered

        await repo.update(word_id, **updates)
    return {"status": "ok", "word": v.word}


@app.delete("/api/vocab/{word_id}")
async def delete_vocab(word_id: int) -> Dict[str, Any]:
    """删除收藏单词"""
    async with get_async_session() as session:
        repo = VocabRepository(session)
        ok = await repo.delete(word_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Word #{word_id} not found")
    return {"status": "deleted", "id": word_id}


@app.post("/api/vocab/{word_id}/review")
async def review_vocab(word_id: int) -> Dict[str, Any]:
    """记录一次复习"""
    async with get_async_session() as session:
        repo = VocabRepository(session)
        v = await repo.get_by_id(word_id)
        if not v:
            raise HTTPException(status_code=404, detail=f"Word #{word_id} not found")
        v = await repo.record_review(word_id)
    return {"status": "ok", "word": v.word, "review_count": v.review_count}


@app.get("/api/vocab/stats")
async def get_vocab_stats() -> Dict[str, Any]:
    """词库统计"""
    async with get_async_session() as session:
        repo = VocabRepository(session)
        stats = await repo.get_stats()
    return {**stats, "sources": {}}


@app.get("/api/vocab/due-review")
async def get_vocab_due_review() -> Dict[str, Any]:
    """艾宾浩斯遗忘曲线复习推荐 — 计算哪些单词需要复习"""
    async with get_async_session() as session:
        repo = VocabRepository(session)
        return await repo.get_due_review()


# ====================================================================
# Daily Goals Endpoint
# ====================================================================

class GoalSetting(BaseModel):
    daily_pomodoros: int = 4
    daily_words: int = 20
    daily_minutes: int = 60


@app.get("/api/goals")
async def get_goals() -> Dict[str, Any]:
    """获取每日目标设定"""
    async with get_async_session() as session:
        repo = DailyGoalRepository(session)
        target = await repo.get_target()
    return target


@app.put("/api/goals")
async def update_goals(goal: GoalSetting) -> Dict[str, Any]:
    """更新每日目标"""
    async with get_async_session() as session:
        repo = DailyGoalRepository(session)
        await repo.update_target(goal.daily_pomodoros, goal.daily_words, goal.daily_minutes)
        target = await repo.get_target()
    return {"status": "ok", **target}


@app.get("/api/goals/today")
async def get_today_progress() -> Dict[str, Any]:
    """获取今日进度"""
    async with get_async_session() as session:
        repo = DailyGoalRepository(session)
        return await repo.get_today_progress()


class ProgressUpdate(BaseModel):
    pomodoros: Optional[int] = None
    words: Optional[int] = None
    minutes: Optional[int] = None

    @field_validator("pomodoros", "words", "minutes", mode="before")
    @classmethod
    def _non_neg_int(cls, v):
        if v is None:
            return v
        try:
            iv = int(v)
        except (TypeError, ValueError):
            raise ValueError("进度值必须为整数")
        if iv < 0:
            raise ValueError("进度值不能为负数")
        return iv


@app.post("/api/goals/today/progress")
async def update_today_progress(data: ProgressUpdate) -> Dict[str, Any]:
    """更新今日进度（增量，校验非负整数）"""
    async with get_async_session() as session:
        repo = DailyGoalRepository(session)
        await repo.update_today_progress(
            pomodoros=data.pomodoros or 0,
            words=data.words or 0,
            minutes=data.minutes or 0,
        )
        progress = await repo.get_today_progress()
    return {"status": "ok", "progress": progress["progress"]}


# ====================================================================
# Health Check
# ====================================================================

@app.get("/api/health")
async def health_check() -> Dict[str, str]:
    return {"status": "ok", "service": "KnowSubtle Learning Universe API", "version": "3.0.0"}


# ====================================================================
# Serve Frontend
# ====================================================================

DASHBOARD_DIR = RESOURCE_DIR

@app.get("/")
async def serve_dashboard():
    dashboard_path = DASHBOARD_DIR / "index.html"
    if not dashboard_path.exists():
        # 尝试从 learning_agent_system 目录查找
        dashboard_path = Path(__file__).parent / "index.html"
    if not dashboard_path.exists():
        return JSONResponse({"error": "dashboard not found"}, status_code=404)
    return FileResponse(dashboard_path)


@app.get("/landing.html")
async def serve_landing():
    landing_path = DASHBOARD_DIR / "landing.html"
    if not landing_path.exists():
        return JSONResponse({"error": "landing not found"}, status_code=404)
    return FileResponse(landing_path)


@app.get("/index.html")
async def serve_index():
    """Redirect to root dashboard"""
    return RedirectResponse("/")


@app.get("/profile.html")
async def serve_profile():
    profile_path = DASHBOARD_DIR / "profile.html"
    if not profile_path.exists():
        fallback = Path(__file__).parent / "dashboard" / "profile.html"
        if fallback.exists():
            profile_path = fallback
    if not profile_path.exists():
        return JSONResponse({"error": "profile not found"}, status_code=404)
    return FileResponse(profile_path)


def _smoke_paths():
    """自检路径解析（仅供打包验证，不对外暴露路由）。"""
    return {
        "app_root": str(APP_ROOT),
        "resource_dir": str(RESOURCE_DIR),
        "config_dir": str(CONFIG_DIR),
        "storage_dir": str(STORAGE_DIR),
    }


if __name__ == "__main__":
    import uvicorn

    cfg = load_app_config()
    port = int(cfg.get("port", 8000))
    host = cfg.get("host", "127.0.0.1")
    try:
        uvicorn.run(app, host=host, port=port)
    except OSError as e:
        msg = str(e).lower()
        # 兼容 Windows(WinError 10048) 与类 Unix 的端口占用提示
        if "address already in use" in msg or "only one usage" in msg \
                or "10048" in msg or "address" in msg:
            port = port + 1
            logger.warning(f"端口 {port-1} 被占用，回退到端口 {port}")
            uvicorn.run(app, host=host, port=port)
        else:
            raise
