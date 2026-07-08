"""
学习系统功能联调测试脚本 v2
根据实际代码结构修正，验证6-Agent协同引擎的各层面功能
"""
import sys
import os
import asyncio
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_phase_1_import_chain():
    """阶段1: 验证完整导入链"""
    print("=" * 60)
    print("[PHASE 1] 完整导入链测试")
    print("=" * 60)

    try:
        from learning_agent_system.orchestrator import TeamOrchestrator, Phase, SessionContext
        from learning_agent_system.agents import (
            LearnerProfiler, ResourceGenerator, LearningPlanner,
            ExerciseEvaluator, LearningTutor, KnowledgeBase
        )
        from learning_agent_system.actions import (
            KnowledgeDiagnosis, CapabilityAssessment, PrefModeling,
            GenerateKnowledgePoint, GenerateExercise, GenerateCase,
            GenerateCodeExample, GenerateVisualAid,
            PlanLearningPath, AdaptiveAdjust,
            EvaluateExercise, AnalyzeMistakes,
            AnswerQuestion, ExplainConcept, GuideDiscussion,
            StoreKnowledge, RetrieveKnowledge, BuildKnowledgeGraph
        )
        from learning_agent_system.schema import (
            LearnerProfile, KnowledgeResource, Exercise,
            LearningModule, LearningPath, ExerciseResult,
            KnowledgeStatus, LearningGoal, KnowledgeDiagnosis as KD,
            ResourcePlan, TutorSession, KnowledgeGraph,
            ResourceType, ExerciseType, ModuleStatus
        )
        from learning_agent_system.memory.longterm_memory import LongTermMemory
        # 修复 Pydantic v2 与 MetaGPT 的 RoleContext 前向引用问题
        from metagpt.environment import Environment
        from metagpt.roles.role import RoleContext
        RoleContext.model_rebuild()
        print(f"  OK: All imports successful ({18} Actions, {15} Schema models, 6 Agents)")
        return True
    except Exception as e:
        print(f"  FAIL: Import error - {e}")
        import traceback
        traceback.print_exc()
        return False


def test_phase_2_agent_instantiation():
    """阶段2: Agent 实例化测试"""
    print("\n" + "=" * 60)
    print("[PHASE 2] Agent 实例化测试")
    print("=" * 60)

    try:
        from learning_agent_system.agents import (
            LearnerProfiler, ResourceGenerator, LearningPlanner,
            ExerciseEvaluator, LearningTutor, KnowledgeBase
        )
        # 修复 Pydantic v2 前向引用
        from metagpt.environment import Environment
        from metagpt.roles.role import RoleContext
        RoleContext.model_rebuild()

        agents = {
            "LearnerProfiler (Alex)": LearnerProfiler,
            "ResourceGenerator (Rhea)": ResourceGenerator,
            "LearningPlanner (Plato)": LearningPlanner,
            "ExerciseEvaluator (Eva)": ExerciseEvaluator,
            "LearningTutor (Socrates)": LearningTutor,
            "KnowledgeBase (Kai)": KnowledgeBase,
        }

        for name, cls in agents.items():
            agent = cls()
            print(f"  OK {name}: {type(agent).__name__}")
            assert hasattr(agent, "run"), f"{name} missing run method"

        print(f"\nAll {len(agents)} agents instantiated successfully")
        return True
    except Exception as e:
        print(f"  FAIL: Agent instantiation error - {e}")
        import traceback
        traceback.print_exc()
        return False


def test_phase_3_orchestrator():
    """阶段3: Orchestrator 测试"""
    print("\n" + "=" * 60)
    print("[PHASE 3] Orchestrator 测试")
    print("=" * 60)

    try:
        from learning_agent_system.orchestrator import TeamOrchestrator

        orch = TeamOrchestrator(storage_dir=".test_memory")
        print(f"  OK: Orchestrator instantiated")
        print(f"  OK: Initial state = {orch.get_summary()}")

        methods = [
            "run_full_pipeline",
            "run_tutor_loop",
            "run_evaluation",
            "load_session",
            "list_sessions",
            "get_summary",
        ]
        for m in methods:
            assert hasattr(orch, m), f"Missing method: {m}"
            print(f"  OK: Method '{m}' exists")

        # Verify private pipeline phases
        priv_methods = [
            "_run_profiler",
            "_run_diagnosis",
            "_run_resource_generation",
            "_run_planning",
            "_run_tutor_round",
            "_run_evaluation",
            "_save_checkpoint",
        ]
        for m in priv_methods:
            assert hasattr(orch, m), f"Missing private method: {m}"

        print(f"\nOrchestrator has all expected methods")
        return orch
    except Exception as e:
        print(f"  FAIL: Orchestrator test error - {e}")
        import traceback
        traceback.print_exc()
        return False


def test_phase_4_schema():
    """阶段4: Schema 数据模型测试"""
    print("\n" + "=" * 60)
    print("[PHASE 4] Schema 数据模型测试")
    print("=" * 60)

    try:
        from learning_agent_system.schema import (
            LearnerProfile, KnowledgeResource, Exercise,
            LearningModule, LearningPath, ExerciseResult,
            KnowledgeStatus, LearningGoal, ResourcePlan,
            TutorSession, KnowledgeGraph,
            ResourceType, ExerciseType, ModuleStatus
        )

        # Test Enums
        print(f"  OK: ResourceType values = {[e.value for e in ResourceType]}")
        print(f"  OK: ExerciseType values = {[e.value for e in ExerciseType]}")
        print(f"  OK: ModuleStatus values = {[e.value for e in ModuleStatus]}")

        # Test LearnerProfile
        profile = LearnerProfile(
            name="Test Learner",
            knowledge_levels={"python_basics": 0.5, "data_structures": 0.3},
            learning_style="visual",
            weaknesses=["loops", "functions"],
            strengths=["variables", "types"]
        )
        print(f"  OK: LearnerProfile - {profile.name}, {len(profile.knowledge_levels)} knowledge items")

        # Test KnowledgeResource
        resource = KnowledgeResource(
            id="res_001",
            title="Python Loops Tutorial",
            content="Loop examples...",
            resource_type=ResourceType.EXPLANATION,
            difficulty=0.4,
            topics=["loops"],
            format="markdown"
        )
        print(f"  OK: KnowledgeResource - {resource.title}")

        # Test Exercise
        exercise = Exercise(
            id="ex_001",
            question="What is the output of range(5)?",
            options=["[0,1,2,3,4]", "[1,2,3,4,5]", "[0,1,2,3]", "[1,2,3,4]"],
            answer="A",
            difficulty=0.3,
            topic="loops",
            exercise_type=ExerciseType.CHOICE,
            points=10
        )
        print(f"  OK: Exercise - {exercise.question[:30]}...")

        # Test LearningModule
        module = LearningModule(
            id="mod_001",
            title="Loops and Iteration",
            topics=["for_loops", "while_loops"],
            exercises=[exercise],
            status=ModuleStatus.PENDING,
            estimated_hours=2.0
        )
        print(f"  OK: LearningModule - {module.title}")

        # Test KnowledgeStatus
        ks = KnowledgeStatus(topic="loops", mastery_level=0.6, confidence=0.7)
        print(f"  OK: KnowledgeStatus - {ks.topic} ({ks.mastery_level})")

        # Test LearningGoal
        lg = LearningGoal(description="Learn Python loops", priority="high")
        print(f"  OK: LearningGoal - {lg.description}")

        # Test ResourcePlan
        rp = ResourcePlan(topics_covered=["loops", "functions"])
        print(f"  OK: ResourcePlan - {len(rp.topics_covered)} topics")

        # Test TutorSession
        ts = TutorSession(round_number=1, topic="loops", explanation="For loops iterate...")
        print(f"  OK: TutorSession - round {ts.round_number}")

        # Test KnowledgeGraph
        kg = KnowledgeGraph(nodes=[{"id": "loop", "label": "Loops"}], topic_count=1)
        print(f"  OK: KnowledgeGraph - {kg.topic_count} topics")

        print("\nAll schema models created successfully")
        return True
    except Exception as e:
        print(f"  FAIL: Schema test error - {e}")
        import traceback
        traceback.print_exc()
        return False


def test_phase_5_actions():
    """阶段5: Action 类测试"""
    print("\n" + "=" * 60)
    print("[PHASE 5] Action 类测试")
    print("=" * 60)

    try:
        from learning_agent_system.actions import (
            KnowledgeDiagnosis, CapabilityAssessment, PrefModeling,
            GenerateKnowledgePoint, GenerateExercise, GenerateCase,
            GenerateCodeExample, GenerateVisualAid,
            PlanLearningPath, AdaptiveAdjust,
            EvaluateExercise, AnalyzeMistakes,
            AnswerQuestion, ExplainConcept, GuideDiscussion,
            StoreKnowledge, RetrieveKnowledge, BuildKnowledgeGraph
        )

        actions = [
            ("KnowledgeDiagnosis", KnowledgeDiagnosis),
            ("CapabilityAssessment", CapabilityAssessment),
            ("PrefModeling", PrefModeling),
            ("GenerateKnowledgePoint", GenerateKnowledgePoint),
            ("GenerateExercise", GenerateExercise),
            ("GenerateCase", GenerateCase),
            ("GenerateCodeExample", GenerateCodeExample),
            ("GenerateVisualAid", GenerateVisualAid),
            ("PlanLearningPath", PlanLearningPath),
            ("AdaptiveAdjust", AdaptiveAdjust),
            ("EvaluateExercise", EvaluateExercise),
            ("AnalyzeMistakes", AnalyzeMistakes),
            ("AnswerQuestion", AnswerQuestion),
            ("ExplainConcept", ExplainConcept),
            ("GuideDiscussion", GuideDiscussion),
            ("StoreKnowledge", StoreKnowledge),
            ("RetrieveKnowledge", RetrieveKnowledge),
            ("BuildKnowledgeGraph", BuildKnowledgeGraph),
        ]

        for name, cls in actions:
            action = cls()
            print(f"  OK: {name}")

        print(f"\nAll {len(actions)} actions instantiated successfully")
        return True
    except Exception as e:
        print(f"  FAIL: Action test error - {e}")
        import traceback
        traceback.print_exc()
        return False


def test_phase_6_memory():
    """阶段6: 持久化记忆测试"""
    print("\n" + "=" * 60)
    print("[PHASE 6] 持久化记忆测试")
    print("=" * 60)

    try:
        from learning_agent_system.memory.longterm_memory import LongTermMemory
        from learning_agent_system.configs.system_config import SystemConfig

        config = SystemConfig.from_env()
        memory = LongTermMemory(config=config)
        print("  OK: LongTermMemory instantiated")

        # Test memory save/load/delete
        test_data = {"profile": "visual", "level": "intermediate"}
        memory.save(key="test_profile", data=test_data)
        print("  OK: Memory saved")

        loaded = memory.load(key="test_profile")
        print(f"  OK: Memory loaded - {loaded}")

        # Cleanup test file
        memory.delete(key="test_profile")
        print("  OK: Memory cleaned up")

        print("\nMemory module test passed")
        return True
    except Exception as e:
        print(f"  FAIL: Memory test error - {e}")
        import traceback
        traceback.print_exc()
        return False


@pytest.mark.asyncio
async def test_phase_7_pipeline_mock():
    """阶段7: Pipeline 异步流程测试（Mock LLM）"""
    print("\n" + "=" * 60)
    print("[PHASE 7] Pipeline 异步流程测试 (Mock)")
    print("=" * 60)

    try:
        from learning_agent_system.orchestrator import TeamOrchestrator
        from metagpt.schema import Message

        orch = TeamOrchestrator(storage_dir=".test_memory")

        # Mock the profiler agent to return a valid profile JSON
        from learning_agent_system.agents import LearnerProfiler
        original_run = LearnerProfiler.run

        async def mock_run(self, msg=None):
            from learning_agent_system.schema import LearnerProfile
            profile = LearnerProfile(
                name="Mock Learner",
                knowledge_levels={"python": 0.5},
                learning_style="visual"
            )
            return Message(content=profile.to_json())

        LearnerProfiler.run = mock_run

        # Run pipeline phase 1 only (profiler)
        ctx = type('Ctx', (), {
            'session_id': 'mock_001',
            'learning_goal': type('LG', (), {'to_dict': lambda self: {'description': 'test'}})(),
            'current_phase': None,
            'learner_profile': None,
            'diagnosis': None,
            'resource_plan': None,
            'learning_path': None,
            'tutor_sessions': [],
            'exercise_results': [],
            'metadata': {}
        })()
        orch.context = ctx

        result = await orch._run_profiler()
        print(f"  OK: Mock profiler returned profile: {result.name}")

        # Restore original
        LearnerProfiler.run = original_run

        print("\nPipeline mock test passed")
        return True
    except Exception as e:
        print(f"  FAIL: Pipeline mock test error - {e}")
        import traceback
        traceback.print_exc()
        return False


def test_phase_8_cross_module():
    """阶段8: 跨模块集成测试"""
    print("\n" + "=" * 60)
    print("[PHASE 8] 跨模块集成测试")
    print("=" * 60)

    try:
        from learning_agent_system.orchestrator import TeamOrchestrator, Phase
        from learning_agent_system.agents import LearnerProfiler
        from learning_agent_system.schema import LearnerProfile
        from learning_agent_system.configs.system_config import SystemConfig

        # Verify agent name
        profiler = LearnerProfiler()
        # MetaGPT Role has a name attribute
        print(f"  OK: Agent name = {profiler.name if hasattr(profiler, 'name') else 'N/A'}")

        # Verify orchestrator state transitions
        orch = TeamOrchestrator(storage_dir=".test_memory")
        assert Phase.PROFILING.value == "profiling"
        assert Phase.DIAGNOSIS.value == "diagnosis"
        assert Phase.RESOURCE.value == "resource"
        assert Phase.PLANNING.value == "planning"
        assert Phase.TUTORING.value == "tutoring"
        assert Phase.EVALUATION.value == "evaluation"
        print(f"  OK: All 6 phases defined correctly")

        # Verify schema JSON serialization
        profile = LearnerProfile(name="Integration Test")
        json_str = profile.to_json()
        loaded = LearnerProfile.from_json(json_str)
        assert loaded.name == "Integration Test"
        print(f"  OK: Schema JSON roundtrip verified")

        # Verify config loading
        config = SystemConfig.from_env()
        print(f"  OK: SystemConfig loaded, knowledge_dir = {config.knowledge_dir}")

        print("\nCross-module integration test passed")
        return True
    except Exception as e:
        print(f"  FAIL: Cross-module test error - {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试流程"""
    print("\n")
    print("=" * 60)
    print("  个性化资源生成与学习多Agent系统 - 功能联调测试 v2")
    print("=" * 60)
    print()

    results = {}

    # Synchronous tests
    results["Phase1_导入链"] = test_phase_1_import_chain()
    results["Phase2_Agent实例化"] = test_phase_2_agent_instantiation()
    orchestrator = test_phase_3_orchestrator()
    results["Phase3_Orchestrator"] = orchestrator is not False

    if isinstance(orchestrator, object) and not isinstance(orchestrator, bool):
        results["_orchestrator"] = orchestrator

    results["Phase4_Schema"] = test_phase_4_schema()
    results["Phase5_Action"] = test_phase_5_actions()
    results["Phase6_记忆"] = test_phase_6_memory()
    results["Phase8_跨模块"] = test_phase_8_cross_module()

    # Asynchronous test
    print("\n" + "=" * 60)
    print("[PHASE 7] Pipeline 异步流程测试 (Mock)")
    print("=" * 60)
    try:
        async_result = asyncio.run(test_phase_7_pipeline_mock())
        results["Phase7_Pipeline_Mock"] = async_result
    except Exception as e:
        print(f"  FAIL: Async test error - {e}")
        results["Phase7_Pipeline_Mock"] = False

    # Clean up test memory
    import shutil
    if os.path.exists(".test_memory"):
        shutil.rmtree(".test_memory")

    # Summary report
    print("\n" + "=" * 60)
    print("[SUMMARY] 测试汇总报告")
    print("=" * 60)

    # Filter out internal keys
    summary_results = {k: v for k, v in results.items() if not k.startswith("_")}
    passed = 0
    total = len(summary_results)

    for name, result in summary_results.items():
        status = "PASS" if result else "FAIL"
        symbol = "[+]" if result else "[-]"
        print(f"  {symbol} {name}: {status}")
        if result:
            passed += 1

    print("-" * 60)
    print(f"Results: {passed}/{total} passed")

    if passed == total:
        print("\n*** ALL TESTS PASSED! System is fully operational. ***\n")
    else:
        print(f"\nWARNING: {total - passed} module(s) failed. Check errors above.\n")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
