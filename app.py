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

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from typing import List, Dict, Any, Optional
from functools import partial
import asyncio
import json
import logging
import os
import re
import yaml
import httpx
from pathlib import Path

from learning_agent_system.orchestrator import TeamOrchestrator, Phase, SessionContext
from learning_agent_system.moderation import check_input_safety, check_output_safety
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

from learning_agent_system.database.request_scope import current_user_id


# ── Pydantic Request Models ──
class CreateSessionRequest(BaseModel):
    goal: str


class ExerciseAnswerRequest(BaseModel):
    answer: str


class TutorChatMessage(BaseModel):
    message: str = ""
    history: list = []


class LLMConfigRequest(BaseModel):
    base_url: str = ""
    api_key: str = ""
    model: str = ""


# ── Auth Pydantic Request Models ──

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    email: str = Field(..., max_length=128)
    password: str = Field(..., min_length=6, max_length=128)
    display_name: str = Field("", max_length=64)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)
    remember: bool = False  # 勾选「记住我」→ 长效登录（30 天）


# ── 校验规则 ──
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{2,32}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ProfileUpdateRequest(BaseModel):
    display_name: str = Field("", max_length=64)
    avatar: str = Field("", max_length=8)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=6, max_length=128)

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
        "http://localhost:8753", "http://127.0.0.1:8753",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

from starlette.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=500, compresslevel=9)

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


@app.middleware("http")
async def user_scope_middleware(request: Request, call_next):
    """解析 Bearer token → 当前用户 id，注入请求作用域 contextvar，供 Repository/Orchestrator 做数据隔离。"""
    uid = None
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token_str = auth[len("Bearer "):].strip()
        if token_str:
            try:
                async with get_async_session() as s:
                    user = await UserRepository(s).get_user_by_token(token_str)
                    if user:
                        uid = user.id
            except Exception:
                uid = None
    request.state.user_id = uid
    ctx_token = current_user_id.set(uid)
    try:
        return await call_next(request)
    finally:
        current_user_id.reset(ctx_token)


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
    """加载 Config/config.json；缺失时写入默认配置。

    端口迁移（2026-07-15）：旧版默认 8000 易与系统中其他程序冲突导致黑屏，
    统一迁移到不常用的 8753；若用户已在 config.json 显式设了非 8000 端口则保留。
    """
    cfg = {"app_name": "KnowSubtle Learning Universe", "port": 8753, "host": "127.0.0.1"}
    cfg_path = CONFIG_DIR / "config.json"
    if cfg_path.exists():
        try:
            cfg.update(json.loads(cfg_path.read_text(encoding="utf-8")))
            # 端口迁移：旧默认 8000 -> 8753（避免冲突）；其余端口原样保留
            if int(cfg.get("port", 8753)) == 8000:
                cfg["port"] = 8753
                try:
                    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"加载 config.json 失败，使用默认配置: {e}")
    else:
        try:
            cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    return cfg


# ── 服务端 LLM 配置（Phase 1：Key 仅存服务端，不经浏览器）──
LLM_CONFIG_DIR = APP_ROOT / "Config"
LLM_CONFIG_PATH = LLM_CONFIG_DIR / "llm_config.yaml"


def load_llm_config() -> dict:
    """读取服务端 LLM 配置（Config/llm_config.yaml）。

    结构 {base_url, api_key, model}。文件不存在或解析失败视为未配置，返回 {}。
    """
    if not LLM_CONFIG_PATH.exists():
        return {}
    try:
        data = yaml.safe_load(LLM_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception as e:
        logger.warning("读取 llm_config.yaml 失败，视为未配置: %s", e)
        return {}
    return {
        "base_url": str(data.get("base_url") or "").strip(),
        "api_key": str(data.get("api_key") or "").strip(),
        "model": str(data.get("model") or "").strip(),
    }


def save_llm_config(base_url: str, api_key: str, model: str) -> None:
    """写入服务端 LLM 配置到 Config/llm_config.yaml（api_key 仅落服务端磁盘）。"""
    LLM_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "base_url": str(base_url).strip(),
        "api_key": str(api_key).strip(),
        "model": str(model).strip(),
    }
    LLM_CONFIG_PATH.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


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
    """加载当前会话上下文：优先用 _current_session_id（需为当前用户所有），否则回退到最新会话。

    统一替代散落的 `_load_current_ctx()`，
    避免多会话下各数据端点指向不同 session 的不一致问题；并按用户隔离。
    """
    orch = get_orchestrator()
    # 全局记录的 session 仅在「能为当前用户加载成功」时使用（隔离校验）
    if _current_session_id:
        ctx = orch.load_session(_current_session_id)
        if ctx:
            return ctx
    # 回退到当前用户的最新会话
    sessions = orch.list_sessions()
    sid = sessions[0] if sessions else None
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
class AgentChatMessageItem(BaseModel):
    role: str = "user"
    content: str = ""


class AgentChatRequest(BaseModel):
    # 兼容旧前端（agent 为字符串）与新前端（agent 为 {"name": ...}）
    agent: Any = "tutor"
    message: str = ""
    messages: List[AgentChatMessageItem] = []
    history: list = []


async def _get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """从 Authorization header / 请求作用域解析当前用户（可选鉴权——匿名访问可继续）。"""
    # 优先复用中间件已解析的 user_id（避免重复查库）
    uid = getattr(request.state, "user_id", None)
    if uid is None:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        token_str = auth[len("Bearer "):].strip()
        if not token_str:
            return None
        async with get_async_session() as session:
            user = await UserRepository(session).get_user_by_token(token_str)
            if not user:
                return None
            uid = user.id
    async with get_async_session() as session:
        user = await UserRepository(session).get_by_id(uid)
        if not user:
            return None
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "avatar": user.avatar,
            "created_at": user.created_at.isoformat() if user.created_at else "",
            "last_login": user.last_login.isoformat() if user.last_login else "",
        }


async def _require_user(request: Request) -> Dict[str, Any]:
    """强制鉴权——未登录则 401。"""
    user = await _get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


@app.get("/api/config/llm")
async def get_llm_config(user: Dict[str, Any] = Depends(_require_user)) -> Dict[str, Any]:
    """读取服务端 LLM 配置（绝不回传 api_key）。

    需登录鉴权（chat/config 接口带 token）。
    """
    cfg = load_llm_config()
    return {
        "configured": bool(cfg.get("base_url") and cfg.get("model")),
        "base_url": cfg.get("base_url", ""),
        "model": cfg.get("model", ""),
    }


@app.post("/api/config/llm")
async def update_llm_config(request: LLMConfigRequest, user: Dict[str, Any] = Depends(_require_user)) -> Dict[str, Any]:
    """写入服务端 LLM 配置（api_key 仅落服务端磁盘，不经浏览器）。

    需登录鉴权（chat/config 接口带 token）。
    """
    base_url = (request.base_url or "").strip()
    model = (request.model or "").strip()
    if not base_url:
        return JSONResponse(status_code=400, content={"detail": "base_url 为必填项。"})
    if not model:
        return JSONResponse(status_code=400, content={"detail": "model 为必填项。"})
    try:
        save_llm_config(base_url, request.api_key or "", model)
    except Exception as e:
        logger.error("保存 LLM 配置失败: %s", e)
        return JSONResponse(status_code=500, content={"detail": "保存 LLM 配置失败，请稍后重试。"})
    return {"ok": True}


def _normalize_agent_messages(request: AgentChatRequest) -> List[Dict[str, Any]]:
    """把两种入参统一成 OpenAI 风格的 messages 列表。

    支持：
      - {messages: [{role, content}, ...]}
      - {message: "..."}（单轮 user 消息）
    """
    msgs: List[Dict[str, Any]] = []
    for m in request.messages or []:
        role = (m.role or "user").strip() or "user"
        content = (m.content or "").strip()
        if content:
            msgs.append({"role": role, "content": content})
    if msgs:
        return msgs
    text = (request.message or "").strip()
    if text:
        return [{"role": "user", "content": text}]
    return []


@app.post("/api/chat/agent")
async def agent_chat(request: AgentChatRequest, user: Dict[str, Any] = Depends(_require_user)) -> Dict[str, Any]:
    """通用多智能体聊天端点 —— Phase 1：服务端 LLM 代理（API Key 仅存服务端）。

    需登录鉴权（chat/config 接口带 token）。未登录一律 401。
    客户端只传对话内容，不接触任何密钥；服务端以自身身份调用
    {base_url}/chat/completions，Authorization: Bearer <api_key>。
    （Phase 2 才接入真实 metagpt 流水线；此处替换原 metagpt stub 分支。）
    """
    cfg = load_llm_config()
    # 守卫生效：未配置服务端 LLM 时直接拒绝，引导用户先在设置中配置
    if not cfg.get("base_url") or not cfg.get("model"):
        return JSONResponse(
            status_code=400,
            content={"detail": "请先在设置中配置 LLM（base_url / api_key / model）"},
        )

    messages = _normalize_agent_messages(request)
    if not messages:
        return JSONResponse(
            status_code=400,
            content={"detail": "缺少有效的消息内容（message 或 messages）。"},
        )

    try:
        payload = {"model": cfg["model"], "messages": messages}
        headers = {
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{cfg['base_url'].rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
        if resp.status_code >= 400:
            logger.error("LLM 上游错误 %s: %s", resp.status_code, resp.text[:500])
            return JSONResponse(
                status_code=502,
                content={"detail": f"LLM 服务返回错误（HTTP {resp.status_code}），请检查 base_url / api_key / model 配置。"},
            )
        try:
            data = resp.json()
            reply = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as e:
            logger.error("LLM 返回结构异常: %s | %s", e, resp.text[:500])
            return JSONResponse(
                status_code=502,
                content={"detail": "LLM 返回结构异常，无法解析回复内容。"},
            )
        if not isinstance(reply, str):
            reply = str(reply)
        return {"reply": reply}
    except httpx.TimeoutException:
        logger.error("Agent chat proxy 超时")
        return JSONResponse(status_code=504, content={"detail": "调用 LLM 服务超时，请稍后重试。"})
    except Exception as e:
        logger.error("Agent chat proxy 失败: %s", e)
        return JSONResponse(status_code=500, content={"detail": "调用 LLM 服务失败，请稍后重试。"})


# ====================================================================
# Auth Endpoints
# ====================================================================

def _user_to_dict(u) -> Dict[str, Any]:
    """序列化 User 为前端可用的安全字典。"""
    return {
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "display_name": u.display_name or u.username,
        "avatar": u.avatar,
        "created_at": u.created_at.isoformat() if u.created_at else "",
        "last_login": u.last_login.isoformat() if u.last_login else "",
    }


@app.post("/api/auth/register")
async def register(body: RegisterRequest) -> Dict[str, Any]:
    """注册新用户"""
    # 输入校验
    if not _USERNAME_RE.match(body.username):
        raise HTTPException(status_code=400, detail="用户名只能包含字母、数字、下划线，长度 2-32")
    if not _EMAIL_RE.match(body.email):
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    async with get_async_session() as session:
        repo = UserRepository(session)

        # 检查用户名是否已存在
        existing = await repo.get_by_username(body.username)
        if existing:
            raise HTTPException(status_code=409, detail="用户名已被注册")

        # 检查邮箱是否已存在
        existing_email = await repo.get_by_email(body.email)
        if existing_email:
            raise HTTPException(status_code=409, detail="邮箱已被注册")

        try:
            user = await repo.register(
                username=body.username,
                email=body.email,
                password=body.password,
                display_name=body.display_name or body.username,
            )
        except Exception as e:
            logger.error(f"注册失败: {e}")
            raise HTTPException(status_code=500, detail="注册失败，请稍后重试")

        # 注册成功自动生成 token
        try:
            token = await repo.create_token(user.id)
        except Exception as e:
            logger.error(f"注册后生成 token 失败: {e}")
            raise HTTPException(status_code=500, detail="注册成功但生成令牌失败，请尝试登录")

    return {
        "status": "ok",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name or user.username,
            "avatar": user.avatar,
            "last_login": user.last_login.isoformat() if user.last_login else "",
        },
        "token": token.token,
    }


@app.post("/api/auth/login")
async def login(body: LoginRequest) -> Dict[str, Any]:
    """用户登录"""
    async with get_async_session() as session:
        repo = UserRepository(session)
        user = await repo.authenticate(body.username, body.password)
        if not user:
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        # 刷新最后登录时间
        await repo.update_last_login(user.id)

        # 生成 token：勾选「记住我」= 30 天长效，否则 24 小时
        ttl_hours = 24 * 30 if body.remember else 24
        try:
            token = await repo.create_token(user.id, ttl_hours=ttl_hours)
        except Exception as e:
            logger.error(f"登录生成 token 失败: {e}")
            raise HTTPException(status_code=500, detail="登录失败，请稍后重试")

    return {
        "status": "ok",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name or user.username,
            "avatar": user.avatar,
            "last_login": user.last_login.isoformat() if user.last_login else "",
        },
        "token": token.token,
    }


@app.post("/api/auth/logout")
async def logout(request: Request) -> Dict[str, Any]:
    """登出（吊销当前 token）"""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token_str = auth[len("Bearer "):].strip()
        if token_str:
            async with get_async_session() as session:
                repo = UserRepository(session)
                await repo.revoke_token(token_str)
    return {"status": "ok", "message": "已登出"}


@app.post("/api/auth/logout-all")
async def logout_all(user: Dict[str, Any] = Depends(_require_user)) -> Dict[str, Any]:
    """登出所有设备（吊销该用户所有 token）"""
    async with get_async_session() as session:
        repo = UserRepository(session)
        count = await repo.revoke_all_user_tokens(user["id"])
    return {"status": "ok", "message": f"已登出全部设备（{count} 个会话）"}


@app.get("/api/auth/me")
async def auth_me(user: Optional[Dict[str, Any]] = Depends(_get_current_user)) -> Dict[str, Any]:
    """获取当前登录用户信息"""
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, "user": user}


@app.get("/api/auth/profile")
async def auth_profile(user: Dict[str, Any] = Depends(_require_user)) -> Dict[str, Any]:
    """获取当前登录用户的完整资料。"""
    async with get_async_session() as session:
        repo = UserRepository(session)
        u = await repo.get_by_id(user["id"])
        if not u:
            raise HTTPException(status_code=404, detail="用户不存在")
    return {"status": "ok", "user": _user_to_dict(u)}


@app.put("/api/auth/profile")
async def update_profile(body: ProfileUpdateRequest,
                         user: Dict[str, Any] = Depends(_require_user)) -> Dict[str, Any]:
    """更新显示名称 / 头像。"""
    async with get_async_session() as session:
        repo = UserRepository(session)
        u = await repo.update_profile(
            user["id"],
            display_name=body.display_name.strip() or None,
            avatar=body.avatar or None,
        )
        if not u:
            raise HTTPException(status_code=404, detail="用户不存在")
    return {"status": "ok", "user": _user_to_dict(u)}


@app.post("/api/auth/change-password")
async def change_password(body: ChangePasswordRequest,
                          user: Dict[str, Any] = Depends(_require_user)) -> Dict[str, Any]:
    """修改密码（需校验原密码）。"""
    async with get_async_session() as session:
        repo = UserRepository(session)
        ok = await repo.change_password(user["id"], body.old_password, body.new_password)
        if not ok:
            raise HTTPException(status_code=400, detail="原密码错误")
    return {"status": "ok", "message": "密码已更新"}


# ====================================================================
# 个性化学习系统端点（功能 1-3：对话式画像 / 多智能体资源 / 路径与精准推送）
# 真实 LLM 接口（Key 仅存服务端，复用 /api/config/llm 配置）
# ====================================================================

from learning_agent_system.database.repo import (
    ProfileRepository, ResourceRepository, PathRepository, EvaluationRepository,
)

# ── 多智能体资源类型元数据（角色人设 + 默认交付格式）──
RESOURCE_META: Dict[str, Dict[str, str]] = {
    "EXPLANATION": {"label": "专业课程讲解", "agent": "讲解员 Rhea",
                    "role": "你是一位严谨的学科讲解专家，善于把复杂概念拆解为清晰、循序渐进的讲解文档。",
                    "format": "markdown"},
    "MIND_MAP": {"label": "知识点思维导图", "agent": "脑图师 Kai",
                 "role": "你是一位知识图谱与思维导图专家，善于用层级化结构梳理知识点之间的关联。",
                 "format": "mermaid"},
    "EXERCISE": {"label": "练习题目", "agent": "习题师 Eva",
                 "role": "你是一位出题专家，善于根据知识点设计梯度合理、覆盖多种题型的练习题目。",
                 "format": "markdown"},
    "READING": {"label": "拓展阅读材料", "agent": "策展人 Plato",
                "role": "你是一位学术阅读策展人，善于推荐并撰写高质量的拓展阅读材料导读。",
                "format": "markdown"},
    "CODE_EXAMPLE": {"label": "代码实操案例", "agent": "代码教练 Socrates",
                     "role": "你是一位工程实践教练，善于提供可运行、注释清晰的代码实操案例。",
                     "format": "code"},
    "VIDEO_SCRIPT": {"label": "教学视频脚本", "agent": "导演 Mira",
                     "role": "你是一位教学视频/动画导演，善于把知识点改写为分镜脚本（含画面、旁白、时长）。",
                     "format": "markdown"},
    "VISUAL_AID": {"label": "图解说明", "agent": "图解师 Lin",
                   "role": "你是一位图解设计师，善于用结构化文字 + Mermaid/ASCII 描述直观的图解方案。",
                   "format": "mermaid"},
}
ALL_RESOURCE_TYPES = list(RESOURCE_META.keys())


# ── 防幻觉 / 安全相关常量 ──
ANTI_HALLUCINATION = (
    "仅基于用户已提供的信息与公认常识作答；对不确定内容明确说明『我不确定』；"
    "涉及具体事实（定义/公式/年份/人物/数据）若无法确认，请加 [待核实] 标注；"
    "不要编造引用、文献或来源链接；如用户请求代写考试答案或学术不端内容，应婉拒并引导正当学习。"
)
# 每个生成的资源 content 末尾追加的脚注（对话式 reply 不加，保持聊天自然）
RESOURCE_FOOTNOTE = (
    "\n\n---\n📌 提示：本内容由 AI 生成，关键知识点请结合教材或权威来源核实。"
)


async def call_llm(messages: List[Dict[str, Any]], *, temperature: float = 0.7,
                   max_tokens: int = 2000, timeout: float = 90.0) -> str:
    """统一的真实 LLM 调用（服务端代理，Key 仅存服务端）。

    未配置 LLM 抛 RuntimeError("LLM_NOT_CONFIGURED")；上游错误抛 RuntimeError("LLM_UPSTREAM_ERROR:xxx")。
    复用了 /api/chat/agent 的代理逻辑，但面向内部编排（不接触浏览器）。
    """
    cfg = load_llm_config()
    if not cfg.get("base_url") or not cfg.get("model"):
        raise RuntimeError("LLM_NOT_CONFIGURED")
    payload = {"model": cfg["model"], "messages": messages, "temperature": temperature}
    if max_tokens:
        payload["max_tokens"] = max_tokens
    headers = {"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{cfg['base_url'].rstrip('/')}/chat/completions", json=payload, headers=headers
        )
    if resp.status_code >= 400:
        raise RuntimeError(f"LLM_UPSTREAM_ERROR:{resp.status_code}")
    data = resp.json()
    return data["choices"][0]["message"]["content"]


async def call_llm_stream(messages: List[Dict[str, Any]], *, temperature: float = 0.7,
                          max_tokens: int = 2000, timeout: float = 120.0):
    """call_llm 的流式变体：async generator，逐段 yield delta 文本(str)。

    未配置 LLM 抛 RuntimeError("LLM_NOT_CONFIGURED")；上游错误(非 200)抛 RuntimeError("LLM_UPSTREAM_ERROR:xxx")。
    容错：若上游返回非流式（无 data: 行，或忽略 stream 字段），退化为一次性拿
    choices[0].message.content 并 yield 整段（保证前端不白屏）。
    """
    cfg = load_llm_config()
    if not cfg.get("base_url") or not cfg.get("model"):
        raise RuntimeError("LLM_NOT_CONFIGURED")
    payload = {"model": cfg["model"], "messages": messages, "temperature": temperature, "stream": True}
    if max_tokens:
        payload["max_tokens"] = max_tokens
    headers = {"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        async with client.stream(
            "POST", f"{cfg['base_url'].rstrip('/')}/chat/completions", json=payload, headers=headers
        ) as resp:
            if resp.status_code >= 400:
                try:
                    body_text = await resp.aread()
                except Exception:
                    body_text = b""
                raise RuntimeError(f"LLM_UPSTREAM_ERROR:{resp.status_code}:{body_text[:500]!r}")

            # 先按 SSE 逐行解析；缓冲所有行以备退化
            lines: List[str] = []
            async for line in resp.aiter_lines():
                if line:
                    lines.append(line)

            saw_data = False
            for line in lines:
                if not line.startswith("data:"):
                    continue
                saw_data = True
                data_str = line[len("data:"):].strip()
                if data_str == "[DONE]":
                    return
                try:
                    chunk = json.loads(data_str)
                except Exception:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = (choices[0].get("delta") or {})
                content = delta.get("content")
                if content:
                    yield content

            # 退化：上游忽略了 stream 字段，整段作为单个 JSON 返回
            if not saw_data:
                raw = "\n".join(lines).strip()
                try:
                    data = json.loads(raw)
                    content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
                    if content:
                        yield content
                except Exception as e:
                    raise RuntimeError(f"LLM_UPSTREAM_ERROR:non-stream fallback failed: {e}")


def _assert_llm_configured() -> None:
    """未配置真实 LLM 时直接拒绝（与 /api/chat/agent 保持一致）。"""
    cfg = load_llm_config()
    if not cfg.get("base_url") or not cfg.get("model"):
        raise HTTPException(
            status_code=400,
            detail="请先在设置中配置 LLM（base_url / api_key / model）",
        )


def parse_llm_json(text: Any) -> Dict[str, Any]:
    """从 LLM 输出中稳健解析 JSON（兼容 ```json 代码围栏 / 前后多余文本）。"""
    if not isinstance(text, str):
        text = str(text)
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t).strip()
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end != -1 and end > start:
        t = t[start:end + 1]
    return json.loads(t)


def _profile_to_text(p: Dict[str, Any]) -> str:
    """把画像字典转成注入 LLM 的紧凑文本。"""
    lines = [
        f"姓名: {p.get('name') or '（未提供）'}",
        f"知识基础: {p.get('knowledge_base') or {}}",
        f"认知风格: {p.get('cognitive_style') or '未知'}",
        f"易错点偏好: {p.get('error_preferences') or []}",
        f"学习目标: {p.get('learning_goals') or []}",
        f"兴趣领域: {p.get('interests') or []}",
        f"优势: {p.get('strengths') or []}",
        f"薄弱点: {p.get('weaknesses') or []}",
        f"学习节奏: {p.get('preferred_pace') or 'normal'}",
        f"学习动机: {p.get('motivation') or '未知'}",
        f"每周可用时间: {p.get('available_hours_per_week') or 0} 小时",
    ]
    return "\n".join(lines)


def _merge_profile(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    """增量合并：字典字段合并；列表字段取并集去重；标量取新值（有则覆盖，否则保留旧）。"""
    merged = dict(old)
    list_fields = ("error_preferences", "learning_goals", "interests", "strengths", "weaknesses")
    for k, v in (new or {}).items():
        if v is None:
            continue
        if k in list_fields and isinstance(v, list):
            base = list(old.get(k) or [])
            for item in v:
                if item not in base:
                    base.append(item)
            merged[k] = base
        elif k == "knowledge_base" and isinstance(v, dict):
            base = dict(old.get(k) or {})
            base.update({kk: float(vv) for kk, vv in v.items()})
            merged[k] = base
        else:
            merged[k] = v
    return merged


def _sse(payload: Dict[str, Any]) -> str:
    """把事件字典序列化为标准 SSE `data: ...` 帧。"""
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


async def _extract_and_merge_profile(existing: Dict[str, Any], message: str,
                                     reply_text: str) -> Dict[str, Any]:
    """复用原 profile_converse 的「LLM 抽 JSON → 合并 → 持久化」逻辑，返回全量画像 dict。"""
    system = (
        "你是一位学习者画像构建助手。请根据用户的自然语言，抽取结构化学习画像并以 JSON 返回。\n"
        "字段说明：\n"
        "  name: 姓名(字符串)\n"
        "  knowledge_base: 对象，学科名 -> 自评掌握度(0~1 的数字)\n"
        "  cognitive_style: 认知风格，取值 visual / auditory / read_write / kinaesthetic\n"
        "  error_preferences: 数组，常错的题型或知识点\n"
        "  learning_goals: 数组，学习目标\n"
        "  interests: 数组，兴趣领域\n"
        "  strengths: 数组，优势\n"
        "  weaknesses: 数组，薄弱点\n"
        "  preferred_pace: 学习节奏 slow / normal / fast\n"
        "  motivation: 学习动机(字符串)\n"
        "  available_hours_per_week: 每周可用学习时间(数字，小时)\n"
        "规则：\n"
        "  1) 只返回 JSON，不要额外解释；\n"
        "  2) 整体结构为 {\"profile\": {上述字段}, \"reply\": \"一句中文确认你更新了哪些内容(≤40字)\"}；\n"
        "  3) 用户未提及的字段，请从『现有画像』继承原值，不要清空；\n"
        "  4) 列表字段可追加新条目，保留旧条目。\n"
        f"现有画像：\n{json.dumps(existing, ensure_ascii=False)}"
    )
    out, _demo = await _llm_profile_json(message, existing)
    try:
        parsed = parse_llm_json(out)
    except Exception:
        parsed = _offline_profile(message, existing)
    raw_profile = parsed.get("profile") if isinstance(parsed, dict) and "profile" in parsed else parsed
    if not isinstance(raw_profile, dict):
        raw_profile = {}
    merged = _merge_profile(existing, raw_profile)
    history = list(existing.get("conversation_history") or [])
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": reply_text or "（已更新画像）"})
    async with get_async_session() as session:
        updated = await ProfileRepository(session).update(merged, history)
    return updated


async def _generate_resource_content(rtype: str, meta: Dict[str, str],
                                     body: "ResourceGenerateRequest",
                                     profile_text: str) -> Dict[str, Any]:
    """生成单个资源（非流式），返回 {title, summary, content}。"""
    system = (
        f"你是「{meta['agent']}」，{meta['role']}\n"
        f"请针对给定主题生成一份「{meta['label']}」。\n"
        "直接返回 JSON：{\"title\": 标题, \"summary\": 一句话简介, \"content\": 完整正文}。\n"
        "正文格式：讲解/练习/阅读/视频脚本用 Markdown；代码案例用 ```语言 代码块；思维导图/图解用 Mermaid 代码块。\n"
        "不要包含额外解释，只返回 JSON。\n"
        + ANTI_HALLUCINATION
    )
    user_msg = (
        f"学科/主题：{body.subject}\n"
        f"细分知识点：{body.topic or '（由你根据主题合理拆解）'}\n"
        f"学生需求/薄弱点：{body.focus or '无'}\n"
        f"学习者画像：\n{profile_text}"
    )
    out = await call_llm(
        [{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
        temperature=0.85, max_tokens=2500,
    )
    parsed = parse_llm_json(out)
    if not isinstance(parsed, dict):
        raise ValueError("返回非 JSON 对象")
    return parsed


# ── 请求模型 ──
class ProfileConverseRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list = []


class ResourceGenerateRequest(BaseModel):
    subject: str = Field(..., min_length=1, max_length=128)
    topic: str = Field("", max_length=512)
    focus: str = Field("", max_length=512)
    resource_types: List[str] = []
    per_type: int = Field(1, ge=1, le=3)


class PathPlanRequest(BaseModel):
    subject: str = Field(..., min_length=1, max_length=128)
    goals: List[str] = []
    duration_weeks: int = Field(8, ge=1, le=52)


class EvaluationCreateRequest(BaseModel):
    dimension: str = Field(..., min_length=1, max_length=64)
    score: float = Field(0.0, ge=0.0, le=100.0)
    detail: str = Field("", max_length=2000)


# ── 离线/演示生成回退（与 session 流水线 DEMO_MODE 一致）──
# 个性化学习 5 个端点原本直连 call_llm，真实 LLM 不可用时直接 400/502，
# 导致「生成失败 + 数据不同步」连锁。以下回退使其在离线时也能产出合法内容并落库，
# 配置真实 LLM 时仍走真实生成（行为不变）。回退函数返回 JSON 字符串（供 parse_llm_json 解析）。

def _offline_reply(message: str) -> str:
    return (f"（演示模式·未连接大模型）已收到你的留言：「{message[:40]}」。"
            f"我已根据你的描述更新了学习画像，可在「学习画像维度」中查看。")


def _offline_profile(message: str, existing: Dict[str, Any]) -> Dict[str, Any]:
    text = message or ""
    subjects = []
    for kw in ("数学", "英语", "物理", "化学", "语文", "生物", "历史", "地理", "政治",
               "编程", "Python", "Java", "机器学习", "深度学习", "算法", "数据结构", "AI"):
        if kw in text:
            subjects.append(kw)
    goals, weaknesses = [], []
    for seg in re.split(r"[。！？\n;；]", text):
        seg = seg.strip()
        if not seg:
            continue
        if any(k in seg for k in ("目标", "想", "希望", "学会", "掌握", "提高", "提升")):
            goals.append(seg[:30])
        if any(k in seg for k in ("薄弱", "不会", "不懂", "差", "困难", "易错", "错")):
            weaknesses.append(seg[:20])
    merged = dict(existing or {})
    kb = dict(existing.get("knowledge_base") or {})
    for s in subjects:
        kb.setdefault(s, 0.3)
    if subjects:
        merged["knowledge_base"] = kb
    if goals:
        merged["learning_goals"] = list(dict.fromkeys(list(existing.get("learning_goals") or []) + goals))
    if weaknesses:
        merged["weaknesses"] = list(dict.fromkeys(list(existing.get("weaknesses") or []) + weaknesses))
    merged.setdefault("name", existing.get("name") or "")
    merged.setdefault("cognitive_style", existing.get("cognitive_style") or "visual")
    merged.setdefault("preferred_pace", existing.get("preferred_pace") or "normal")
    merged.setdefault("motivation", existing.get("motivation") or "自主提升")
    merged.setdefault("available_hours_per_week", existing.get("available_hours_per_week") or 5.0)
    return {"profile": merged, "reply": "（演示模式）已根据你的描述更新学习画像。"}


def _offline_resource(rtype: str, meta: Dict[str, str], body: "ResourceGenerateRequest",
                      profile_text: str) -> Dict[str, Any]:
    subject = body.subject
    topic = body.topic or subject
    label = meta["label"]
    agent = meta["agent"]
    fmt = meta["format"]
    if fmt == "mermaid":
        content = (f"```mermaid\nmindmap\n  root(({topic}))\n"
                   f"    {subject} 核心概念\n    {subject} 关联知识\n    {subject} 典型应用\n```")
    elif fmt == "code":
        content = (f"```python\n# {label}：{topic}\n"
                   f"# 演示模式生成（未连接大模型）。配置 LLM 后可获得更精准内容。\n"
                   f"def demo_{rtype.lower()}():\n    print(\"Hello, {topic}!\")\n```")
    else:
        content = (f"# {label}：{topic}\n\n"
                   f"> 本内容由「{agent}」在演示模式下生成，未连接大模型。\n\n"
                   f"## 要点\n- 围绕 {subject} 的「{topic}」展开\n"
                   f"- 学习者画像：{profile_text[:120]}\n\n"
                   f"## 详情\n（演示占位内容，用于验证资源生成与资源库同步链路。）")
    return {
        "title": f"{label}：{topic}",
        "summary": f"{subject} · {topic} 的{label}（演示）",
        "content": content,
    }


def _offline_path(body: "PathPlanRequest", prof: Dict[str, Any], resources_text: str) -> Dict[str, Any]:
    subject = body.subject
    goals = body.goals or [f"掌握{subject}核心概念"]
    duration = max(1, int(body.duration_weeks or 8))
    milestones = [
        {"title": f"{subject} 基础入门", "description": f"建立 {subject} 的整体认知框架。",
         "resource_types": ["EXPLANATION", "MIND_MAP"], "est_hours": 4.0, "week": 1},
        {"title": f"{subject} 核心突破", "description": "针对薄弱点进行专项训练。",
         "resource_types": ["EXERCISE", "CODE_EXAMPLE"], "est_hours": 6.0, "week": max(2, duration // 3)},
        {"title": f"{subject} 综合提升", "description": "通过阅读与视频拓展视野，巩固所学。",
         "resource_types": ["READING", "VIDEO_SCRIPT"], "est_hours": 5.0, "week": max(3, duration * 2 // 3)},
    ]
    return {
        "title": f"{subject} 个性化学习路径（演示）",
        "description": f"基于目标「{', '.join(goals)}」与已有资源生成的路径（演示模式）。",
        "milestones": milestones,
    }


def _derive_resource_tags(body: "ResourceGenerateRequest", prof: Dict[str, Any]) -> List[str]:
    """从学科/主题/画像推导资源标签，供资源库与精准推送做关键词匹配（修复同步一致性）。"""
    tags: List[str] = [body.subject]
    if body.topic:
        tags.append(body.topic)
    for w in (prof.get("weaknesses") or [])[:3]:
        if w:
            tags.append(str(w))
    for i in (prof.get("interests") or [])[:2]:
        if i:
            tags.append(str(i))
    seen, out = set(), []
    for t in tags:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


async def _get_latest_profile_dict(session) -> Dict[str, Any]:
    """精准推送/路径规划前拉取最新画像（同步钩子），保证基于最新画像数据。"""
    return ProfileRepository.to_dict(await ProfileRepository(session).get_or_create())


async def _llm_profile_json(message: str, existing: Dict[str, Any]):
    """画像抽取：真实 LLM 优先，失败回退离线。返回 (json_str, used_demo)。"""
    system = (
        "你是一位学习者画像构建助手。请根据用户的自然语言，抽取结构化学习画像并以 JSON 返回。\n"
        "字段说明：\n"
        "  name: 姓名(字符串)\n"
        "  knowledge_base: 对象，学科名 -> 自评掌握度(0~1 的数字)\n"
        "  cognitive_style: 认知风格，取值 visual / auditory / read_write / kinaesthetic\n"
        "  error_preferences: 数组，常错的题型或知识点\n"
        "  learning_goals: 数组，学习目标\n"
        "  interests: 数组，兴趣领域\n"
        "  strengths: 数组，优势\n"
        "  weaknesses: 数组，薄弱点\n"
        "  preferred_pace: 学习节奏 slow / normal / fast\n"
        "  motivation: 学习动机(字符串)\n"
        "  available_hours_per_week: 每周可用学习时间(数字，小时)\n"
        "规则：\n"
        "  1) 只返回 JSON，不要额外解释；\n"
        "  2) 整体结构为 {\"profile\": {上述字段}, \"reply\": \"一句中文确认你更新了哪些内容(≤40字)\"}；\n"
        "  3) 用户未提及的字段，请从『现有画像』继承原值，不要清空；\n"
        "  4) 列表字段可追加新条目，保留旧条目。\n"
        f"现有画像：\n{json.dumps(existing, ensure_ascii=False)}"
    )
    try:
        out = await call_llm(
            [{"role": "system", "content": system}, {"role": "user", "content": f"用户说：{message}"}],
            temperature=0.3, max_tokens=1200,
        )
        return out, False
    except Exception as e:
        logger.warning("画像 LLM 生成失败，回退离线: %s", e)
        return json.dumps(_offline_profile(message, existing), ensure_ascii=False), True


async def _llm_resource_json(rtype: str, meta: Dict[str, str], body: "ResourceGenerateRequest",
                             profile_text: str):
    """资源内容生成：真实 LLM 优先，失败回退离线。返回 (json_str, used_demo)。"""
    system = (
        f"你是「{meta['agent']}」，{meta['role']}\n"
        f"请针对给定主题生成一份「{meta['label']}」。\n"
        "直接返回 JSON：{\"title\": 标题, \"summary\": 一句话简介, \"content\": 完整正文}。\n"
        "正文格式：讲解/练习/阅读/视频脚本用 Markdown；代码案例用 ```语言 代码块；思维导图/图解用 Mermaid 代码块。\n"
        "不要包含额外解释，只返回 JSON。\n" + ANTI_HALLUCINATION
    )
    user_msg = (
        f"学科/主题：{body.subject}\n"
        f"细分知识点：{body.topic or '（由你根据主题合理拆解）'}\n"
        f"学生需求/薄弱点：{body.focus or '无'}\n"
        f"学习者画像：\n{profile_text}"
    )
    try:
        out = await call_llm(
            [{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
            temperature=0.85, max_tokens=2500,
        )
        return out, False
    except Exception as e:
        logger.warning("资源 LLM 生成失败(%s)，回退离线: %s", rtype, e)
        return json.dumps(_offline_resource(rtype, meta, body, profile_text), ensure_ascii=False), True


async def _llm_path_json(body: "PathPlanRequest", prof: Dict[str, Any], resources_text: str):
    """路径规划：真实 LLM 优先，失败回退离线。返回 (json_str, used_demo)。"""
    profile_text = _profile_to_text(prof)
    system = (
        "你是「规划师 Plato」，善于制定科学、动态、有序的个性化学习路径。\n"
        "请输出 JSON：{\"title\": 路径标题, \"description\": 概述, "
        "\"milestones\": [ {\"title\": 阶段名, \"description\": 说明, \"resource_types\": [资源类型], "
        "\"est_hours\": 预计学时(数字), \"week\": 周次} ]}。\n"
        "要求：milestones 按学习顺序从易到难排列，覆盖用户目标与薄弱点；可引用已有资源类型。"
        "只返回 JSON，不要额外解释。"
    )
    user_msg = (
        f"学科：{body.subject}\n"
        f"学习目标：{', '.join(body.goals) or '（由你根据学科合理设定）'}\n"
        f"计划周期：{body.duration_weeks} 周\n"
        f"学习者画像：\n{profile_text}\n"
        f"已有资源：\n{resources_text}"
    )
    try:
        out = await call_llm(
            [{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
            temperature=0.5, max_tokens=2500,
        )
        return out, False
    except Exception as e:
        logger.warning("路径 LLM 规划失败，回退离线: %s", e)
        return json.dumps(_offline_path(body, prof, resources_text), ensure_ascii=False), True


# ── 端点 ──

@app.get("/api/profile")
async def get_profile(user: Dict[str, Any] = Depends(_require_user)) -> Dict[str, Any]:
    """获取当前用户的对话式学习画像（未构建则返回 null）。"""
    async with get_async_session() as session:
        p = await ProfileRepository(session).get()
        data = ProfileRepository.to_dict(p) if p else None
    return {"profile": data}


@app.post("/api/profile/converse")
async def profile_converse(body: ProfileConverseRequest,
                           user: Dict[str, Any] = Depends(_require_user)) -> Dict[str, Any]:
    """自然语言对话 → 真实 LLM 抽取 ≥6 维结构化画像 → 增量合并 → 持久化（随学随新）。"""
    async with get_async_session() as session:
        repo = ProfileRepository(session)
        existing = ProfileRepository.to_dict(await repo.get_or_create())
    try:
        out, demo = await _llm_profile_json(body.message, existing)
        try:
            parsed = parse_llm_json(out)
        except Exception:
            parsed = _offline_profile(body.message, existing)
            demo = True
    except Exception as e:
        logger.error("画像抽取失败: %s", e)
        return JSONResponse(status_code=502, content={"detail": "画像抽取失败，请稍后重试。"})

    raw_profile = parsed.get("profile") if isinstance(parsed, dict) and "profile" in parsed else parsed
    reply = parsed.get("reply", "") if isinstance(parsed, dict) else ""
    if not isinstance(raw_profile, dict):
        raw_profile = {}
    merged = _merge_profile(existing, raw_profile)

    history = list(existing.get("conversation_history") or [])
    history.append({"role": "user", "content": body.message})
    history.append({"role": "assistant", "content": reply or "（已更新画像）"})

    async with get_async_session() as session:
        updated = await ProfileRepository(session).update(merged, history)
    return {"profile": updated, "reply": reply, "demo": demo}


@app.post("/api/profile/converse/stream")
async def profile_converse_stream(body: ProfileConverseRequest,
                                  user: Dict[str, Any] = Depends(_require_user)):
    """流式对话版：边生成边推送 token，结束后抽取画像并合并持久化（SSE / text/event-stream）。

    事件协议：token(delta) → [safety(warning)] → profile(全量画像) → done(ok)。
    任何异常：error(detail) 后结束。
    """
    # 同步校验（流式中无法用 HTTPException 返回状态）
    safety = check_input_safety(body.message)
    if not safety.get("safe"):
        raise HTTPException(
            status_code=400,
            detail=f"内容安全检查未通过：{','.join(safety.get('reasons', []))}",
        )

    async def gen():
        try:
            async with get_async_session() as session:
                existing = ProfileRepository.to_dict(await ProfileRepository(session).get_or_create())

            # 1) 流式对话 messages（防幻觉系统提示 + 历史 + 用户消息）
            system_stream = (
                "你是一位耐心的学习陪伴助手，用中文与用户自然对话，帮助用户梳理学习目标、"
                "巩固知识、发现薄弱点。\n" + ANTI_HALLUCINATION
            )
            messages = [{"role": "system", "content": system_stream}]
            for h in (existing.get("conversation_history") or []):
                role = h.get("role")
                content = h.get("content")
                if role and content:
                    messages.append({"role": role, "content": content})
            messages.append({"role": "user", "content": body.message})

            # 2) 流式累积回复，逐段推送
            reply = []
            try:
                async for delta in call_llm_stream(messages, temperature=0.7, max_tokens=2000):
                    reply.append(delta)
                    yield _sse({"event": "token", "delta": delta})
            except Exception as e:
                logger.warning("流式对话 LLM 失败，回退离线回复: %s", e)
                offline_reply = _offline_reply(body.message)
                reply.append(offline_reply)
                yield _sse({"event": "token", "delta": offline_reply})
            reply_text = "".join(reply)

            # 输出安全检查（不阻断，仅提示）
            out_safety = check_output_safety(reply_text)
            if not out_safety.get("safe"):
                yield _sse({"event": "safety",
                            "warning": ",".join(out_safety.get("reasons", [])) or "输出含需核实内容"})

            # 3) 抽取画像并合并持久化（复用原逻辑，非流式更稳）
            try:
                profile_dict = await _extract_and_merge_profile(existing, body.message, reply_text)
            except Exception as e:
                logger.warning("流式对话画像抽取失败，回退到现有画像: %s", e)
                profile_dict = existing

            # 4) 推送画像
            yield _sse({"event": "profile", "profile": profile_dict})

            # 5) 收尾
            yield _sse({"event": "done", "ok": True})
        except Exception as e:
            logger.error("流式对话异常: %s", e)
            yield _sse({"event": "error", "detail": str(e)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/resources")
async def list_resources(resource_type: str = "", subject: str = "",
                        user: Dict[str, Any] = Depends(_require_user)) -> Dict[str, Any]:
    """列出当前用户的个性化资源库（可按类型/学科过滤）。"""
    async with get_async_session() as session:
        items = await ResourceRepository(session).list(resource_type or None, subject or None)
    return {"resources": items}


@app.delete("/api/resources/{rid}")
async def delete_resource(rid: int, user: Dict[str, Any] = Depends(_require_user)) -> Dict[str, Any]:
    """删除一条资源。"""
    async with get_async_session() as session:
        ok = await ResourceRepository(session).delete(rid)
    if not ok:
        raise HTTPException(status_code=404, detail="资源不存在")
    return {"ok": True}


@app.post("/api/resources/generate")
async def resources_generate(body: ResourceGenerateRequest,
                            user: Dict[str, Any] = Depends(_require_user)) -> Dict[str, Any]:
    """多智能体协同生成个性化资源：为每个请求的类型派遣对应角色智能体（真实 LLM）。"""
    async with get_async_session() as session:
        prof = ProfileRepository.to_dict(await ProfileRepository(session).get_or_create())
    types = [t for t in (body.resource_types or ALL_RESOURCE_TYPES) if t in RESOURCE_META]
    if not types:
        types = ALL_RESOURCE_TYPES
    profile_text = _profile_to_text(prof)

    async def _gen_one(rtype: str, idx: int) -> Dict[str, Any]:
        meta = RESOURCE_META[rtype]
        profile_text = _profile_to_text(prof)
        try:
            out, demo = await _llm_resource_json(rtype, meta, body, profile_text)
            parsed = parse_llm_json(out)
        except Exception:
            parsed = _offline_resource(rtype, meta, body, profile_text)
            demo = True
        if not isinstance(parsed, dict):
            parsed = _offline_resource(rtype, meta, body, profile_text)
        tags = _derive_resource_tags(body, prof)
        return {
            "resource_type": rtype, "title": parsed.get("title", f"{meta['label']}：{body.subject}"),
            "summary": parsed.get("summary", ""), "content": parsed.get("content", ""),
            "format": meta["format"], "source_agent": meta["agent"], "subject": body.subject,
            "difficulty": 1, "ok": True, "tags": tags, "demo": demo,
        }

    tasks = []
    for rtype in types:
        for i in range(max(1, body.per_type)):
            tasks.append(_gen_one(rtype, i))
    results = await asyncio.gather(*tasks)

    created, errors = [], []
    async with get_async_session() as session:
        repo = ResourceRepository(session)
        for r in results:
            if r.get("ok"):
                created.append(await repo.add(
                    resource_type=r["resource_type"], title=r["title"], summary=r["summary"],
                    content=r["content"], format=r["format"], source_agent=r["source_agent"],
                    subject=r["subject"], difficulty=r["difficulty"], tags=r.get("tags", []),
                ))
            else:
                errors.append({"resource_type": r["resource_type"], "title": r["title"], "summary": r["summary"]})
    return {"resources": created, "errors": errors, "generated": len(created)}


@app.post("/api/resources/generate/stream")
async def resources_generate_stream(body: ResourceGenerateRequest,
                                    user: Dict[str, Any] = Depends(_require_user)):
    """流式资源生成版：逐类型推送 progress/resource，结束推送 done（SSE / text/event-stream）。

    事件协议：progress(start) → resource(单条) → [progress(error)] → … → progress(done)。
    单个类型失败不影响其余类型（progress error 后继续）。
    """
    # 同步校验（流式中无法用 HTTPException 返回状态）
    safety = check_input_safety(f"{body.subject} {body.topic} {body.focus}")
    if not safety.get("safe"):
        raise HTTPException(
            status_code=400,
            detail=f"内容安全检查未通过：{','.join(safety.get('reasons', []))}",
        )

    async def gen():
        errors = []
        generated = 0
        try:
            async with get_async_session() as session:
                repo = ResourceRepository(session)
                prof = ProfileRepository.to_dict(await ProfileRepository(session).get_or_create())
            profile_text = _profile_to_text(prof)
            types = [t for t in (body.resource_types or ALL_RESOURCE_TYPES) if t in RESOURCE_META]
            if not types:
                types = ALL_RESOURCE_TYPES

            async with get_async_session() as session:
                repo = ResourceRepository(session)
                for rtype in types:
                    for _i in range(max(1, body.per_type)):
                        meta = RESOURCE_META[rtype]
                        yield _sse({"event": "progress", "agent": meta["agent"],
                                    "label": meta["label"], "status": "start"})
                        try:
                            try:
                                out, demo = await _llm_resource_json(rtype, meta, body, profile_text)
                                parsed = parse_llm_json(out)
                            except Exception:
                                parsed = _offline_resource(rtype, meta, body, profile_text)
                                demo = True
                            if not isinstance(parsed, dict):
                                parsed = _offline_resource(rtype, meta, body, profile_text)
                            content = parsed.get("content", "")
                            out_safety = check_output_safety(content)
                            flagged = not out_safety.get("safe", True)
                            resource = await repo.add(
                                resource_type=rtype,
                                title=parsed.get("title", f"{meta['label']}：{body.subject}"),
                                summary=parsed.get("summary", ""),
                                content=(content + RESOURCE_FOOTNOTE) if content else "",
                                format=meta["format"], source_agent=meta["agent"],
                                subject=body.subject, difficulty=1,
                                tags=_derive_resource_tags(body, prof),
                            )
                            if flagged:
                                resource = dict(resource)
                                resource["flagged"] = True
                                resource["safety_warning"] = ",".join(out_safety.get("reasons", [])) or "内容需核实"
                            if demo:
                                resource = dict(resource)
                                resource["demo"] = True
                            yield _sse({"event": "resource", "resource": resource})
                            generated += 1
                        except Exception as e:
                            logger.warning("资源生成失败 %s: %s", rtype, e)
                            errors.append({"resource_type": rtype, "detail": str(e)[:200]})
                            yield _sse({"event": "progress", "agent": meta["agent"],
                                        "label": meta["label"], "status": "error", "detail": str(e)[:200]})

            yield _sse({"event": "progress", "status": "done", "generated": generated, "errors": errors})
        except Exception as e:
            logger.error("流式资源生成异常: %s", e)
            yield _sse({"event": "error", "detail": str(e)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/path/plan")
async def path_plan(body: PathPlanRequest,
                   user: Dict[str, Any] = Depends(_require_user)) -> Dict[str, Any]:
    """依托多智能体协同机制，结合画像与已有资源，规划科学、动态、有序的个性化学习路径。"""
    async with get_async_session() as session:
        prof = await _get_latest_profile_dict(session)
        resources = await ResourceRepository(session).list(subject=body.subject, limit=50)
    profile_text = _profile_to_text(prof)
    resources_text = "\n".join(
        [f"- [{r['resource_type']}] {r['title']} (id={r['id']})" for r in resources]
    ) or "（暂无资源，请先生成）"
    out, demo = await _llm_path_json(body, prof, resources_text)
    try:
        parsed = parse_llm_json(out)
    except Exception:
        parsed = _offline_path(body, prof, resources_text)
        demo = True
    if not isinstance(parsed, dict):
        parsed = _offline_path(body, prof, resources_text)
    milestones = parsed.get("milestones", []) if isinstance(parsed, dict) else []
    async with get_async_session() as session:
        path = await PathRepository(session).create(
            body.subject, parsed.get("title", f"{body.subject} 学习路径"),
            parsed.get("description", ""), milestones,
        )
    return {"path": path, "demo": demo}


@app.get("/api/path")
async def get_path(user: Dict[str, Any] = Depends(_require_user)) -> Dict[str, Any]:
    """获取当前用户最新的一条学习路径。"""
    async with get_async_session() as session:
        p = await PathRepository(session).get_latest()
    return {"path": p}


@app.get("/api/recommendations")
async def get_recommendations(user: Dict[str, Any] = Depends(_require_user)) -> Dict[str, Any]:
    """基于画像（薄弱点/兴趣/学科）对已有资源做精准匹配推送。"""
    async with get_async_session() as session:
        prof = await _get_latest_profile_dict(session)
        recs = await ResourceRepository(session).recommend_for(prof)
    return {"recommendations": recs, "profile_synced": True}


@app.post("/api/evaluation")
async def create_evaluation(body: EvaluationCreateRequest,
                           user: Dict[str, Any] = Depends(_require_user)) -> Dict[str, Any]:
    """记录一条学习效果评估（功能 5 数据落地，供后续自适应策略使用）。"""
    async with get_async_session() as session:
        rec = await EvaluationRepository(session).add(body.dimension, body.score, body.detail)
    return {"evaluation": rec}


@app.get("/api/evaluation")
async def list_evaluations(user: Dict[str, Any] = Depends(_require_user)) -> Dict[str, Any]:
    """列出当前用户最近的评估记录。"""
    async with get_async_session() as session:
        recs = await EvaluationRepository(session).list_recent()
    return {"evaluations": recs}


# ====================================================================
# Stats / Dashboard Analytics Endpoint
# ====================================================================

import random
import math
from datetime import datetime, timedelta

# 数据库查询替代 JSON 文件
from learning_agent_system.database.repo import StatsRepository, VocabRepository, DailyGoalRepository, UserRepository, User


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
    return FileResponse(dashboard_path, headers={"Cache-Control": "no-store"})


@app.get("/landing.html")
async def serve_landing():
    landing_path = DASHBOARD_DIR / "landing.html"
    if not landing_path.exists():
        return JSONResponse({"error": "landing not found"}, status_code=404)
    return FileResponse(landing_path, headers={"Cache-Control": "no-store"})


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
    return FileResponse(profile_path, headers={"Cache-Control": "no-store"})


@app.get("/learning.html")
async def serve_learning():
    learning_path = DASHBOARD_DIR / "learning.html"
    if not learning_path.exists():
        fallback = Path(__file__).parent / "dashboard" / "learning.html"
        if fallback.exists():
            learning_path = fallback
    if not learning_path.exists():
        return JSONResponse({"error": "learning not found"}, status_code=404)
    return FileResponse(learning_path, headers={"Cache-Control": "no-store"})


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
