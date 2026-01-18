#!/usr/bin/env python3
"""
Quick Validation Script for Agent-S Memory System

Runs through core functionality to validate the implementation works.
Can be run directly without pytest.

Usage:
    python validate_memory.py
"""

import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def success(self, name):
        print(f"  ✓ {name}")
        self.passed += 1
    
    def failure(self, name, error):
        print(f"  ✗ {name}")
        print(f"    Error: {error}")
        self.failed += 1
        self.errors.append((name, str(error)))
    
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"Results: {self.passed}/{total} passed")
        if self.errors:
            print(f"\nFailed tests:")
            for name, err in self.errors:
                print(f"  - {name}: {err[:100]}")
        return self.failed == 0


def create_sample_skill():
    """Create a sample skill for testing."""
    from gui_agents.s3.skills.models import (
        Skill, Step, Parameter, FailureMode, SkillMetadata,
        UserContext, ContextType, ActionType
    )
    
    return Skill(
        id=f"test_skill_{int(time.time()*1000)}",
        name="Open Google Chrome and Search",
        summary="Opens Google Chrome browser and performs a web search on Google.",
        steps=[
            Step(
                number=1,
                title="Open Spotlight",
                action_description="Press Cmd+Space to open Spotlight search",
                location=(500, 300),
                ui_element="Spotlight Search Bar",
                purpose="Access macOS search functionality",
                expected_result="Spotlight search overlay appears",
                action_type=ActionType.HOTKEY,
            ),
            Step(
                number=2,
                title="Type Chrome",
                action_description="Type 'Chrome' in Spotlight",
                ui_element="Spotlight text input",
                purpose="Search for Chrome application",
                expected_result="Chrome app appears in search results",
                action_type=ActionType.TYPE,
            ),
            Step(
                number=3,
                title="Press Enter",
                action_description="Press Enter to launch Chrome",
                purpose="Launch the selected application",
                expected_result="Chrome browser opens",
                action_type=ActionType.HOTKEY,
            ),
        ],
        parameters=[
            Parameter(
                name="search_query",
                param_type="String",
                example="weather today",
                description="The search query to perform",
            ),
        ],
        prerequisites=["macOS system", "Chrome installed"],
        preconditions=["Desktop visible"],
        postconditions=["Chrome is open"],
        metadata=SkillMetadata(
            operating_system="macOS",
            applications=["Chrome", "Spotlight"],
            automation_suitability=9,
        ),
        user_context=[
            UserContext(
                key=f"search_engine_{int(time.time()*1000)}",
                value="google.com",
                context_type=ContextType.PREFERENCE,
                application="Chrome",
            ),
        ],
    )


def test_models(result: TestResult):
    """Test data models."""
    print("\n[Models]")
    
    try:
        from gui_agents.s3.skills.models import (
            Skill, Step, Parameter, UserContext, ContextType, ActionType
        )
        
        # Test UserContext round-trip
        ctx = UserContext(
            key="test_url",
            value="https://example.com",
            context_type=ContextType.URL,
            application="Chrome",
        )
        data = ctx.to_dict()
        restored = UserContext.from_dict(data)
        assert restored.key == ctx.key
        assert restored.value == ctx.value
        result.success("UserContext serialization")
    except Exception as e:
        result.failure("UserContext serialization", e)
    
    try:
        # Test Step round-trip
        step = Step(
            number=1,
            title="Click",
            action_description="Click button",
            location=(100, 200),
            action_type=ActionType.CLICK,
        )
        data = step.to_dict()
        restored = Step.from_dict(data)
        assert restored.location == (100, 200)
        assert restored.action_type == ActionType.CLICK
        result.success("Step serialization")
    except Exception as e:
        result.failure("Step serialization", e)
    
    try:
        # Test Skill round-trip
        skill = create_sample_skill()
        data = skill.to_dict()
        restored = Skill.from_dict(data)
        assert restored.name == skill.name
        assert len(restored.steps) == len(skill.steps)
        result.success("Skill serialization")
    except Exception as e:
        result.failure("Skill serialization", e)
    
    try:
        # Test embedding text generation
        skill = create_sample_skill()
        summary_text = skill.to_summary_embedding_text()
        full_text = skill.to_full_embedding_text()
        assert len(full_text) > len(summary_text)
        assert "Chrome" in summary_text
        result.success("Embedding text generation")
    except Exception as e:
        result.failure("Embedding text generation", e)


def test_context_store(result: TestResult, temp_dir: Path):
    """Test context store operations."""
    print("\n[Context Store]")
    
    try:
        from gui_agents.s3.skills.context_store import UserContextStore
        from gui_agents.s3.skills.models import UserContext, ContextType
        
        store = UserContextStore(store_path=temp_dir)
        
        # Add context
        ctx = UserContext(
            key="canvas_url",
            value="https://canvas.asu.edu",
            context_type=ContextType.URL,
        )
        store.add(ctx)
        
        # Get context
        retrieved = store.get("canvas_url")
        assert retrieved is not None
        assert retrieved.value == "https://canvas.asu.edu"
        result.success("Add and get context")
    except Exception as e:
        result.failure("Add and get context", e)
    
    try:
        # Test persistence
        store2 = UserContextStore(store_path=temp_dir)
        retrieved = store2.get("canvas_url")
        assert retrieved is not None
        result.success("Context persistence")
    except Exception as e:
        result.failure("Context persistence", e)
    
    try:
        # Test search
        results = store.search("canvas")
        assert len(results) >= 1
        result.success("Context search")
    except Exception as e:
        result.failure("Context search", e)


def test_skill_store(result: TestResult, temp_dir: Path):
    """Test skill store operations."""
    print("\n[Skill Store]")
    
    try:
        from gui_agents.s3.skills.store import SkillStore
        
        store = SkillStore(store_path=temp_dir, use_sentence_transformers=False)
        result.success("SkillStore initialization")
    except Exception as e:
        result.failure("SkillStore initialization", e)
        return None
    
    try:
        # Add skill
        skill = create_sample_skill()
        store.add_skill(skill)
        
        retrieved = store.get_skill(skill.id)
        assert retrieved is not None
        assert retrieved.name == skill.name
        result.success("Add and get skill")
    except Exception as e:
        result.failure("Add and get skill", e)
    
    try:
        # Get all skills
        all_skills = store.get_all_skills()
        assert len(all_skills) >= 1
        result.success("Get all skills")
    except Exception as e:
        result.failure("Get all skills", e)
    
    try:
        # Search skills
        results = store.search_skills("browser", n_results=5)
        assert len(results) >= 1
        skill, score = results[0]
        assert score > 0
        result.success("Search skills")
    except Exception as e:
        result.failure("Search skills", e)
    
    try:
        # Search steps
        results = store.search_steps("Chrome", n_results=5)
        assert len(results) >= 1
        result.success("Search steps")
    except Exception as e:
        result.failure("Search steps", e)
    
    try:
        # Stats
        stats = store.stats()
        assert stats["total_skills"] >= 1
        result.success("Store stats")
    except Exception as e:
        result.failure("Store stats", e)
    
    return store


def test_bm25(result: TestResult):
    """Test BM25 retrieval."""
    print("\n[BM25]")
    
    try:
        from gui_agents.s3.skills.retriever import BM25
        
        bm25 = BM25()
        documents = {
            "doc1": "python programming language",
            "doc2": "javascript web development",
            "doc3": "python machine learning tensorflow",
        }
        bm25.fit(documents)
        
        results = bm25.search("python", top_k=2)
        assert len(results) == 2
        doc_ids = [r[0] for r in results]
        assert "doc1" in doc_ids
        assert "doc3" in doc_ids
        result.success("BM25 search")
    except Exception as e:
        result.failure("BM25 search", e)
    
    try:
        # Empty corpus
        bm25 = BM25()
        bm25.fit({})
        results = bm25.search("test")
        assert len(results) == 0
        result.success("BM25 empty corpus")
    except Exception as e:
        result.failure("BM25 empty corpus", e)


def test_retriever(result: TestResult, temp_dir: Path):
    """Test skill retriever."""
    print("\n[Retriever]")
    
    try:
        from gui_agents.s3.skills.store import SkillStore
        from gui_agents.s3.skills.retriever import SkillRetriever
        
        store = SkillStore(store_path=temp_dir, use_sentence_transformers=False)
        skill = create_sample_skill()
        store.add_skill(skill)
        
        retriever = SkillRetriever(store)
        result.success("Retriever initialization")
    except Exception as e:
        result.failure("Retriever initialization", e)
        return
    
    try:
        # Semantic retrieval
        results = retriever.retrieve(
            query="open web browser",
            n_results=5,
            use_hybrid=False,
        )
        assert len(results) >= 1
        result.success("Semantic retrieval")
    except Exception as e:
        result.failure("Semantic retrieval", e)
    
    try:
        # Hybrid retrieval
        results = retriever.retrieve(
            query="Chrome Spotlight macOS",
            n_results=5,
            use_hybrid=True,
        )
        assert len(results) >= 1
        result.success("Hybrid retrieval")
    except Exception as e:
        result.failure("Hybrid retrieval", e)
    
    try:
        # Retrieve with steps
        results = retriever.retrieve_with_steps(
            query="search",
            n_skills=3,
            n_steps_per_skill=3,
        )
        assert len(results) >= 1
        result.success("Retrieve with steps")
    except Exception as e:
        result.failure("Retrieve with steps", e)


def test_event_conversion(result: TestResult):
    """Test event conversion."""
    print("\n[Event Conversion]")
    
    try:
        from gui_agents.s3.recording.convert_events import convert_events
        
        events = [
            {"type": "click", "x": 100, "y": 200, "button": "left", "pressed": True, "time": 0.0},
        ]
        actions = convert_events(events)
        assert len(actions) == 1
        assert "CLICK" in actions[0]
        result.success("Click event conversion")
    except Exception as e:
        result.failure("Click event conversion", e)
    
    try:
        events = [
            {"type": "scroll", "x": 500, "y": 300, "dx": 0, "dy": -3, "time": 0.0},
        ]
        actions = convert_events(events)
        assert len(actions) == 1
        assert "SCROLL" in actions[0]
        result.success("Scroll event conversion")
    except Exception as e:
        result.failure("Scroll event conversion", e)
    
    try:
        from gui_agents.s3.recording.convert_events import simplify_events
        
        events = [
            {"type": "move", "x": 100, "y": 100, "time": 0.0},
            {"type": "move", "x": 110, "y": 100, "time": 0.01},
            {"type": "move", "x": 120, "y": 100, "time": 0.02},
            {"type": "click", "x": 120, "y": 100, "button": "left", "pressed": True, "time": 0.1},
        ]
        simplified = simplify_events(events)
        move_count = sum(1 for e in simplified if e["type"] == "move")
        assert move_count < 3
        result.success("Event simplification")
    except Exception as e:
        result.failure("Event simplification", e)


def test_stress(result: TestResult, temp_dir: Path):
    """Stress tests."""
    print("\n[Stress Tests]")
    
    try:
        from gui_agents.s3.skills.store import SkillStore
        from gui_agents.s3.skills.models import Skill, Step, SkillMetadata
        
        store = SkillStore(store_path=temp_dir / "stress", use_sentence_transformers=False)
        
        n_skills = 30
        start = time.time()
        for i in range(n_skills):
            skill = Skill(
                id=f"stress_skill_{i:03d}",
                name=f"Workflow {i}",
                summary=f"This is workflow number {i}",
                steps=[
                    Step(number=j, title=f"Step {j}", action_description=f"Do action {j}")
                    for j in range(1, 6)
                ],
                metadata=SkillMetadata(operating_system="macOS"),
            )
            store.add_skill(skill)
        
        elapsed = time.time() - start
        stats = store.stats()
        assert stats["total_skills"] == n_skills
        result.success(f"Add {n_skills} skills ({elapsed:.2f}s)")
    except Exception as e:
        result.failure(f"Add {n_skills} skills", e)
    
    try:
        # Search performance
        start = time.time()
        for _ in range(10):
            store.search_skills("workflow", n_results=10)
        elapsed = time.time() - start
        result.success(f"10 searches ({elapsed:.2f}s)")
    except Exception as e:
        result.failure("Search performance", e)
    
    try:
        # Large skill
        large_skill = Skill(
            id="large_skill",
            name="Large Workflow",
            summary="A" * 5000,  # 5KB summary
            steps=[
                Step(number=i, title=f"Step {i}", action_description="B" * 500)
                for i in range(1, 51)  # 50 steps
            ],
        )
        store.add_skill(large_skill)
        retrieved = store.get_skill("large_skill")
        assert retrieved is not None
        assert len(retrieved.steps) == 50
        result.success("Large skill handling")
    except Exception as e:
        result.failure("Large skill handling", e)


def test_edge_cases(result: TestResult, temp_dir: Path):
    """Edge case tests."""
    print("\n[Edge Cases]")
    
    try:
        from gui_agents.s3.skills.store import SkillStore
        
        store = SkillStore(store_path=temp_dir / "edge", use_sentence_transformers=False)
        
        # Get nonexistent
        r = store.get_skill("nonexistent")
        assert r is None
        result.success("Get nonexistent skill")
    except Exception as e:
        result.failure("Get nonexistent skill", e)
    
    try:
        # Delete nonexistent
        r = store.delete_skill("nonexistent")
        assert r is False
        result.success("Delete nonexistent skill")
    except Exception as e:
        result.failure("Delete nonexistent skill", e)
    
    try:
        # Search empty store
        results = store.search_skills("anything")
        assert len(results) == 0
        result.success("Search empty store")
    except Exception as e:
        result.failure("Search empty store", e)
    
    try:
        from gui_agents.s3.skills.models import Skill
        
        # Unicode content
        skill = Skill(
            id="unicode_skill",
            name="搜索中文 🔍",
            summary="Поиск 🎉",
        )
        store.add_skill(skill)
        retrieved = store.get_skill("unicode_skill")
        assert "🔍" in retrieved.name
        result.success("Unicode content")
    except Exception as e:
        result.failure("Unicode content", e)
    
    try:
        # Special characters
        skill = Skill(
            id="special_chars",
            name="C++ & Python",
            summary="Handle 'special' chars",
        )
        store.add_skill(skill)
        
        # These should not crash
        store.search_skills("C++")
        store.search_skills("&")
        store.search_skills("'quotes'")
        result.success("Special characters")
    except Exception as e:
        result.failure("Special characters", e)


def main():
    """Run all validation tests."""
    print("=" * 60)
    print("Agent-S Memory System Validation")
    print("=" * 60)
    
    result = TestResult()
    
    # Create temp directory
    temp_dir = Path(tempfile.mkdtemp(prefix="agent_s_validate_"))
    print(f"\nUsing temp directory: {temp_dir}")
    
    try:
        test_models(result)
        test_context_store(result, temp_dir / "context")
        test_skill_store(result, temp_dir / "skills")
        test_bm25(result)
        test_retriever(result, temp_dir / "retriever")
        test_event_conversion(result)
        test_stress(result, temp_dir / "stress")
        test_edge_cases(result, temp_dir / "edge")
        
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        traceback.print_exc()
    finally:
        # Cleanup
        print(f"\nCleaning up temp directory...")
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    success = result.summary()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
