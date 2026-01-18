#!/usr/bin/env python3
"""
Comprehensive Stress Tests for Agent-S Memory System

Tests all components:
- Models (serialization/deserialization)
- Context Store (CRUD, persistence, search)
- Skill Store (ChromaDB, search, filtering)
- Retriever (BM25, semantic, hybrid)
- Event conversion
- Memory integration
- Edge cases and performance
"""

import json
import os
import shutil
import sys
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    d = tempfile.mkdtemp(prefix="agent_s_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_skill():
    """Create a sample skill for testing."""
    from gui_agents.s3.skills.models import (
        Skill, Step, Parameter, FailureMode, SkillMetadata,
        UserContext, ContextType, ActionType
    )
    
    return Skill(
        id="test_skill_001",
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
            Step(
                number=4,
                title="Navigate to Google",
                action_description="Type google.com in address bar and press Enter",
                ui_element="Chrome address bar",
                purpose="Navigate to search engine",
                expected_result="Google search page loads",
                action_type=ActionType.TYPE,
            ),
        ],
        parameters=[
            Parameter(
                name="search_query",
                param_type="String",
                example="weather today",
                description="The search query to perform",
            ),
            Parameter(
                name="browser",
                param_type="Application",
                example="Chrome",
                description="Browser to use for search",
            ),
        ],
        prerequisites=["macOS system", "Chrome installed"],
        preconditions=["Desktop visible", "No modal dialogs open"],
        postconditions=["Chrome is open", "Google search page displayed"],
        visual_landmarks={"(500,300)": "Spotlight icon", "(100,50)": "Chrome address bar"},
        timing_delays={"page_load": 2.0, "spotlight_animation": 0.5},
        failure_modes=[
            FailureMode(
                failure="Chrome not installed",
                likelihood="Low",
                recovery="Install Chrome from google.com/chrome",
            ),
            FailureMode(
                failure="Network unavailable",
                likelihood="Medium",
                recovery="Check network connection and retry",
            ),
        ],
        variations=["Use Safari instead", "Use keyboard shortcut Cmd+T for new tab"],
        metadata=SkillMetadata(
            operating_system="macOS",
            applications=["Chrome", "Spotlight"],
            automation_suitability=9,
            source_file="/path/to/log.md",
            recording_id="rec_001",
        ),
        user_context=[
            UserContext(
                key="default_search_engine",
                value="google.com",
                context_type=ContextType.PREFERENCE,
                application="Chrome",
                description="User's preferred search engine",
            ),
        ],
    )


@pytest.fixture
def skill_store(temp_dir):
    """Create a SkillStore with temporary directory."""
    from gui_agents.s3.skills.store import SkillStore
    return SkillStore(store_path=temp_dir, use_sentence_transformers=False)


@pytest.fixture
def context_store(temp_dir):
    """Create a UserContextStore with temporary directory."""
    from gui_agents.s3.skills.context_store import UserContextStore
    return UserContextStore(store_path=temp_dir)


# =============================================================================
# Model Tests
# =============================================================================

class TestModels:
    """Test data model serialization and edge cases."""
    
    def test_user_context_round_trip(self):
        """Test UserContext serialization/deserialization."""
        from gui_agents.s3.skills.models import UserContext, ContextType
        
        ctx = UserContext(
            key="canvas_url",
            value="https://canvas.asu.edu",
            context_type=ContextType.URL,
            application="Chrome",
            description="Canvas LMS URL",
            source_skill_id="skill_123",
        )
        
        data = ctx.to_dict()
        restored = UserContext.from_dict(data)
        
        assert restored.key == ctx.key
        assert restored.value == ctx.value
        assert restored.context_type == ctx.context_type
        assert restored.application == ctx.application
        assert restored.description == ctx.description
        assert restored.source_skill_id == ctx.source_skill_id
    
    def test_step_round_trip(self):
        """Test Step serialization/deserialization."""
        from gui_agents.s3.skills.models import Step, ActionType
        
        step = Step(
            number=1,
            title="Click Button",
            action_description="Click the submit button",
            location=(100, 200),
            ui_element="Submit Button",
            purpose="Submit the form",
            expected_result="Form submitted",
            action_mapping="CLICK(100, 200)",
            action_type=ActionType.CLICK,
        )
        
        data = step.to_dict()
        restored = Step.from_dict(data)
        
        assert restored.number == step.number
        assert restored.title == step.title
        assert restored.location == step.location
        assert restored.action_type == step.action_type
    
    def test_skill_round_trip(self, sample_skill):
        """Test full Skill serialization/deserialization."""
        from gui_agents.s3.skills.models import Skill
        
        data = sample_skill.to_dict()
        restored = Skill.from_dict(data)
        
        assert restored.id == sample_skill.id
        assert restored.name == sample_skill.name
        assert restored.summary == sample_skill.summary
        assert len(restored.steps) == len(sample_skill.steps)
        assert len(restored.parameters) == len(sample_skill.parameters)
        assert len(restored.failure_modes) == len(sample_skill.failure_modes)
        assert restored.metadata.operating_system == sample_skill.metadata.operating_system
        assert len(restored.user_context) == len(sample_skill.user_context)
    
    def test_skill_embedding_text(self, sample_skill):
        """Test embedding text generation."""
        summary_text = sample_skill.to_summary_embedding_text()
        full_text = sample_skill.to_full_embedding_text()
        
        assert "Chrome" in summary_text
        assert "macOS" in summary_text
        assert len(full_text) > len(summary_text)
        assert "Parameters" in full_text
    
    def test_step_embedding_text(self, sample_skill):
        """Test step embedding text generation."""
        step = sample_skill.steps[0]
        text = step.to_embedding_text()
        
        assert "Step 1" in text
        assert step.title in text
        assert step.action_description in text
    
    def test_empty_skill(self):
        """Test skill with minimal data."""
        from gui_agents.s3.skills.models import Skill
        
        skill = Skill(id="empty", name="Empty Skill", summary="")
        data = skill.to_dict()
        restored = Skill.from_dict(data)
        
        assert restored.id == "empty"
        assert restored.steps == []
        assert restored.parameters == []
    
    def test_special_characters_in_context(self):
        """Test handling of special characters."""
        from gui_agents.s3.skills.models import UserContext, ContextType
        
        special_value = "https://example.com/path?q=hello&name=O'Brien<script>"
        ctx = UserContext(
            key="special_url",
            value=special_value,
            context_type=ContextType.URL,
        )
        
        data = ctx.to_dict()
        restored = UserContext.from_dict(data)
        
        assert restored.value == special_value
    
    def test_unicode_content(self):
        """Test handling of Unicode content."""
        from gui_agents.s3.skills.models import Skill, Step
        
        skill = Skill(
            id="unicode_skill",
            name="搜索中文内容 🔍",
            summary="Поиск на разных языках with émojis 🎉",
            steps=[
                Step(
                    number=1,
                    title="打开浏览器",
                    action_description="Откройте браузер",
                )
            ]
        )
        
        data = skill.to_dict()
        restored = Skill.from_dict(data)
        
        assert "🔍" in restored.name
        assert "🎉" in restored.summary
        assert "打开浏览器" in restored.steps[0].title


# =============================================================================
# Context Store Tests
# =============================================================================

class TestContextStore:
    """Test UserContextStore operations."""
    
    def test_add_and_get(self, context_store):
        """Test adding and retrieving context."""
        from gui_agents.s3.skills.models import UserContext, ContextType
        
        ctx = UserContext(
            key="test_key",
            value="test_value",
            context_type=ContextType.PREFERENCE,
        )
        
        context_store.add(ctx)
        retrieved = context_store.get("test_key")
        
        assert retrieved is not None
        assert retrieved.value == "test_value"
    
    def test_add_many(self, context_store):
        """Test adding multiple contexts."""
        from gui_agents.s3.skills.models import UserContext, ContextType
        
        contexts = [
            UserContext(key=f"key_{i}", value=f"value_{i}", context_type=ContextType.PREFERENCE)
            for i in range(10)
        ]
        
        context_store.add_many(contexts)
        
        for i in range(10):
            ctx = context_store.get(f"key_{i}")
            assert ctx is not None
            assert ctx.value == f"value_{i}"
    
    def test_search(self, context_store):
        """Test context search."""
        from gui_agents.s3.skills.models import UserContext, ContextType
        
        contexts = [
            UserContext(key="canvas_url", value="https://canvas.asu.edu", context_type=ContextType.URL, application="Chrome"),
            UserContext(key="gmail_url", value="https://gmail.com", context_type=ContextType.URL, application="Chrome"),
            UserContext(key="username", value="aryan", context_type=ContextType.CREDENTIAL, application="GitHub"),
        ]
        context_store.add_many(contexts)
        
        # Search by key
        results = context_store.search("canvas")
        assert len(results) >= 1
        assert any("canvas" in r.key for r in results)
        
        # Search by value
        results = context_store.search("gmail")
        assert len(results) >= 1
    
    def test_persistence(self, temp_dir):
        """Test context persistence across store instances."""
        from gui_agents.s3.skills.models import UserContext, ContextType
        from gui_agents.s3.skills.context_store import UserContextStore
        
        # Create and populate store
        store1 = UserContextStore(store_path=temp_dir)
        store1.add(UserContext(key="persistent", value="data", context_type=ContextType.PREFERENCE))
        
        # Create new store instance
        store2 = UserContextStore(store_path=temp_dir)
        retrieved = store2.get("persistent")
        
        assert retrieved is not None
        assert retrieved.value == "data"
    
    def test_clear(self, context_store):
        """Test clearing all contexts."""
        from gui_agents.s3.skills.models import UserContext, ContextType
        
        context_store.add(UserContext(key="to_clear", value="x", context_type=ContextType.PREFERENCE))
        assert context_store.get("to_clear") is not None
        
        context_store.clear()
        assert context_store.get("to_clear") is None
        assert len(context_store.get_all()) == 0
    
    def test_context_string_generation(self, context_store):
        """Test context string generation for prompts."""
        from gui_agents.s3.skills.models import UserContext, ContextType
        
        contexts = [
            UserContext(key="canvas_url", value="https://canvas.asu.edu", context_type=ContextType.URL, application="Chrome"),
            UserContext(key="github_username", value="aryankeluskar", context_type=ContextType.CREDENTIAL, application="GitHub"),
        ]
        context_store.add_many(contexts)
        
        # Full context string
        full_str = context_store.to_context_string()
        assert "canvas" in full_str.lower()
        assert "github" in full_str.lower()
        
        # Filtered context string (use correct parameter name)
        chrome_str = context_store.to_context_string(filter_app="Chrome")
        assert "canvas" in chrome_str.lower()


# =============================================================================
# Skill Store Tests
# =============================================================================

class TestSkillStore:
    """Test SkillStore operations with ChromaDB."""
    
    def test_add_and_get_skill(self, skill_store, sample_skill):
        """Test adding and retrieving a skill."""
        skill_store.add_skill(sample_skill)
        
        retrieved = skill_store.get_skill(sample_skill.id)
        assert retrieved is not None
        assert retrieved.name == sample_skill.name
        assert len(retrieved.steps) == len(sample_skill.steps)
    
    def test_get_all_skills(self, skill_store, sample_skill):
        """Test getting all skills."""
        skill_store.add_skill(sample_skill)
        
        all_skills = skill_store.get_all_skills()
        assert len(all_skills) == 1
        assert all_skills[0].id == sample_skill.id
    
    def test_search_skills(self, skill_store, sample_skill):
        """Test semantic search for skills."""
        skill_store.add_skill(sample_skill)
        
        results = skill_store.search_skills("open browser and search", n_results=5)
        assert len(results) >= 1
        
        skill, score = results[0]
        assert skill.id == sample_skill.id
        assert score > 0
    
    def test_search_steps(self, skill_store, sample_skill):
        """Test semantic search for steps."""
        skill_store.add_skill(sample_skill)
        
        results = skill_store.search_steps("type Chrome", n_results=5)
        assert len(results) >= 1
        
        skill_id, step, score = results[0]
        assert skill_id == sample_skill.id
        assert score > 0
    
    def test_delete_skill(self, skill_store, sample_skill):
        """Test skill deletion."""
        skill_store.add_skill(sample_skill)
        assert skill_store.get_skill(sample_skill.id) is not None
        
        result = skill_store.delete_skill(sample_skill.id)
        assert result is True
        assert skill_store.get_skill(sample_skill.id) is None
    
    def test_clear_store(self, skill_store, sample_skill):
        """Test clearing the entire store."""
        skill_store.add_skill(sample_skill)
        assert len(skill_store.get_all_skills()) == 1
        
        skill_store.clear()
        assert len(skill_store.get_all_skills()) == 0
    
    def test_stats(self, skill_store, sample_skill):
        """Test statistics retrieval."""
        skill_store.add_skill(sample_skill)
        
        stats = skill_store.stats()
        assert stats["total_skills"] == 1
        assert stats["total_steps"] == len(sample_skill.steps)
    
    def test_find_skills_by_postcondition(self, skill_store, sample_skill):
        """Test finding skills by postcondition."""
        skill_store.add_skill(sample_skill)
        
        results = skill_store.find_skills_by_postcondition("Chrome is open")
        assert len(results) >= 1
        assert results[0].id == sample_skill.id
    
    def test_find_skills_by_precondition(self, skill_store, sample_skill):
        """Test finding skills by precondition."""
        skill_store.add_skill(sample_skill)
        
        results = skill_store.find_skills_by_precondition("Desktop visible")
        assert len(results) >= 1
        assert results[0].id == sample_skill.id
    
    def test_persistence(self, temp_dir, sample_skill):
        """Test store persistence across instances."""
        from gui_agents.s3.skills.store import SkillStore
        
        # Create and populate store
        store1 = SkillStore(store_path=temp_dir, use_sentence_transformers=False)
        store1.add_skill(sample_skill)
        
        # Create new store instance
        store2 = SkillStore(store_path=temp_dir, use_sentence_transformers=False)
        retrieved = store2.get_skill(sample_skill.id)
        
        assert retrieved is not None
        assert retrieved.name == sample_skill.name
    
    def test_user_context_integration(self, skill_store, sample_skill):
        """Test that user context is stored when adding skill."""
        skill_store.add_skill(sample_skill)
        
        # Check context store has the context
        ctx = skill_store.context_store.get("default_search_engine")
        assert ctx is not None
        assert ctx.value == "google.com"


# =============================================================================
# BM25 Tests
# =============================================================================

class TestBM25:
    """Test BM25 keyword retrieval."""
    
    def test_basic_search(self):
        """Test basic BM25 search."""
        from gui_agents.s3.skills.retriever import BM25
        
        bm25 = BM25()
        documents = {
            "doc1": "python programming language syntax",
            "doc2": "javascript web development framework",
            "doc3": "python machine learning tensorflow",
        }
        bm25.fit(documents)
        
        results = bm25.search("python", top_k=2)
        assert len(results) == 2
        
        # Both python docs should be returned
        doc_ids = [r[0] for r in results]
        assert "doc1" in doc_ids
        assert "doc3" in doc_ids
    
    def test_empty_corpus(self):
        """Test BM25 with empty corpus."""
        from gui_agents.s3.skills.retriever import BM25
        
        bm25 = BM25()
        bm25.fit({})
        
        results = bm25.search("test")
        assert len(results) == 0
    
    def test_no_matches(self):
        """Test BM25 with no matching documents."""
        from gui_agents.s3.skills.retriever import BM25
        
        bm25 = BM25()
        bm25.fit({"doc1": "apple banana cherry"})
        
        results = bm25.search("python")
        assert len(results) == 0
    
    def test_score_ordering(self):
        """Test that BM25 scores are properly ordered."""
        from gui_agents.s3.skills.retriever import BM25
        
        bm25 = BM25()
        documents = {
            "doc1": "python",
            "doc2": "python python python",  # More occurrences
            "doc3": "java",
        }
        bm25.fit(documents)
        
        results = bm25.search("python", top_k=3)
        
        # doc2 should have higher score than doc1
        scores = {r[0]: r[1] for r in results}
        if "doc2" in scores and "doc1" in scores:
            assert scores["doc2"] > scores["doc1"]


# =============================================================================
# Retriever Tests
# =============================================================================

class TestSkillRetriever:
    """Test hybrid skill retriever."""
    
    def test_semantic_only_retrieval(self, skill_store, sample_skill):
        """Test semantic-only retrieval."""
        from gui_agents.s3.skills.retriever import SkillRetriever
        
        skill_store.add_skill(sample_skill)
        retriever = SkillRetriever(skill_store)
        
        results = retriever.retrieve(
            query="How do I open a web browser?",
            n_results=5,
            use_hybrid=False,
        )
        
        assert len(results) >= 1
        assert results[0].match_reason == "semantic"
    
    def test_hybrid_retrieval(self, skill_store, sample_skill):
        """Test hybrid (semantic + BM25) retrieval."""
        from gui_agents.s3.skills.retriever import SkillRetriever
        
        skill_store.add_skill(sample_skill)
        retriever = SkillRetriever(skill_store)
        
        results = retriever.retrieve(
            query="Chrome Spotlight macOS search",
            n_results=5,
            use_hybrid=True,
        )
        
        assert len(results) >= 1
        # Should find the skill via hybrid or one of the methods
    
    def test_retrieve_with_steps(self, skill_store, sample_skill):
        """Test retrieval with step matching."""
        from gui_agents.s3.skills.retriever import SkillRetriever
        
        skill_store.add_skill(sample_skill)
        retriever = SkillRetriever(skill_store)
        
        results = retriever.retrieve_with_steps(
            query="type in spotlight search",
            n_skills=3,
            n_steps_per_skill=3,
        )
        
        assert len(results) >= 1
        # matched_steps should be populated
        if results:
            assert isinstance(results[0].matched_steps, list)
    
    def test_retrieve_composable(self, skill_store, sample_skill):
        """Test retrieval for multiple sub-goals."""
        from gui_agents.s3.skills.retriever import SkillRetriever
        
        skill_store.add_skill(sample_skill)
        retriever = SkillRetriever(skill_store)
        
        results = retriever.retrieve_composable(
            goal="Open Chrome and search for something",
            sub_goals=["open Chrome browser", "search on Google"],
            n_results_per_goal=2,
        )
        
        assert len(results) == 2  # One result list per sub-goal
    
    def test_refresh_index(self, skill_store, sample_skill):
        """Test BM25 index refresh."""
        from gui_agents.s3.skills.retriever import SkillRetriever
        
        retriever = SkillRetriever(skill_store)
        
        # Add skill after retriever creation
        skill_store.add_skill(sample_skill)
        retriever.refresh_index()
        
        results = retriever.retrieve("Chrome browser", n_results=5)
        assert len(results) >= 1


# =============================================================================
# Event Conversion Tests
# =============================================================================

class TestEventConversion:
    """Test event conversion from raw events to actions."""
    
    def test_convert_click_event(self):
        """Test click event conversion."""
        from gui_agents.s3.recording.convert_events import convert_events
        
        events = [
            {"type": "click", "x": 100, "y": 200, "button": "left", "pressed": True, "time": 0.0},
        ]
        
        actions = convert_events(events)
        assert len(actions) == 1
        assert "CLICK" in actions[0]
        assert "100" in actions[0]
        assert "200" in actions[0]
    
    def test_convert_typing_event(self):
        """Test typing event conversion."""
        from gui_agents.s3.recording.convert_events import convert_events, simplify_events
        
        # Raw key events that will be merged by simplify_events
        events = [
            {"type": "key", "key": "H", "pressed": True, "time": 0.0},
            {"type": "key", "key": "e", "pressed": True, "time": 0.1},
            {"type": "key", "key": "l", "pressed": True, "time": 0.2},
            {"type": "key", "key": "l", "pressed": True, "time": 0.3},
            {"type": "key", "key": "o", "pressed": True, "time": 0.4},
        ]
        
        # First simplify to merge characters into typing
        simplified = simplify_events(events)
        actions = convert_events(simplified)
        assert len(actions) >= 1
        # Should see TYPING
        assert any("TYPING" in a or "Hello" in a for a in actions)
    
    def test_convert_special_key_event(self):
        """Test special key event conversion."""
        from gui_agents.s3.recording.convert_events import convert_events
        
        # Special keys should be converted directly
        events = [
            {"type": "key", "key": "Return", "pressed": True, "time": 0.0},
        ]
        
        actions = convert_events(events)
        assert len(actions) >= 1
        assert any("PRESS" in a for a in actions)
    
    def test_convert_hotkey_event(self):
        """Test hotkey event conversion."""
        from gui_agents.s3.recording.convert_events import convert_events
        
        events = [
            {"type": "key", "key": "cmd", "pressed": True, "time": 0.0},
            {"type": "key", "key": "c", "pressed": True, "time": 0.1},
            {"type": "key", "key": "c", "pressed": False, "time": 0.2},
            {"type": "key", "key": "cmd", "pressed": False, "time": 0.3},
        ]
        
        actions = convert_events(events)
        assert len(actions) >= 1
    
    def test_convert_scroll_event(self):
        """Test scroll event conversion."""
        from gui_agents.s3.recording.convert_events import convert_events
        
        events = [
            {"type": "scroll", "x": 500, "y": 300, "dx": 0, "dy": -3, "time": 0.0},
        ]
        
        actions = convert_events(events)
        assert len(actions) == 1
        assert "SCROLL" in actions[0]
    
    def test_simplify_events(self):
        """Test event simplification (merging consecutive typing, removing moves)."""
        from gui_agents.s3.recording.convert_events import simplify_events
        
        events = [
            {"type": "move", "x": 100, "y": 100, "time": 0.0},
            {"type": "move", "x": 110, "y": 100, "time": 0.01},
            {"type": "move", "x": 120, "y": 100, "time": 0.02},
            {"type": "click", "x": 120, "y": 100, "button": "left", "pressed": True, "time": 0.1},
        ]
        
        simplified = simplify_events(events)
        
        # Should remove intermediate moves
        move_count = sum(1 for e in simplified if e["type"] == "move")
        assert move_count < 3
    
    def test_load_events_from_jsonl(self, temp_dir):
        """Test loading events from JSONL file."""
        from gui_agents.s3.recording.convert_events import load_events
        
        events_file = temp_dir / "events.jsonl"
        with open(events_file, "w") as f:
            f.write('{"type": "click", "x": 100, "y": 200, "button": "left", "pressed": true, "time": 0.0}\n')
            f.write('{"type": "key", "key": "a", "pressed": true, "time": 0.1}\n')
        
        events = load_events(events_file)
        assert len(events) == 2
        assert events[0]["type"] == "click"
        assert events[1]["type"] == "key"


# =============================================================================
# Memory Integration Tests
# =============================================================================

class TestSkillMemory:
    """Test skill memory integration with procedural memory."""
    
    def test_skill_memory_initialization(self, temp_dir):
        """Test SkillMemory initialization."""
        # Patch the default store path
        import gui_agents.s3.skills.store as store_module
        original_path = store_module.DEFAULT_STORE_PATH
        store_module.DEFAULT_STORE_PATH = temp_dir
        
        try:
            from gui_agents.s3.memory.skill_integration import SkillMemory
            memory = SkillMemory()
            
            assert memory.store is not None
            assert memory.retriever is not None
            assert memory.composer is not None
        finally:
            store_module.DEFAULT_STORE_PATH = original_path
    
    def test_has_skills(self, temp_dir, sample_skill):
        """Test has_skills check."""
        import gui_agents.s3.skills.store as store_module
        original_path = store_module.DEFAULT_STORE_PATH
        store_module.DEFAULT_STORE_PATH = temp_dir
        
        try:
            from gui_agents.s3.memory.skill_integration import SkillMemory
            memory = SkillMemory()
            
            assert not memory.has_skills()
            
            memory.store.add_skill(sample_skill)
            assert memory.has_skills()
        finally:
            store_module.DEFAULT_STORE_PATH = original_path
    
    def test_skill_context_prompt(self, temp_dir, sample_skill):
        """Test skill context prompt generation."""
        import gui_agents.s3.skills.store as store_module
        original_path = store_module.DEFAULT_STORE_PATH
        store_module.DEFAULT_STORE_PATH = temp_dir
        
        try:
            from gui_agents.s3.memory.skill_integration import SkillMemory
            memory = SkillMemory()
            memory.store.add_skill(sample_skill)
            memory.retriever.refresh_index()
            
            prompt = memory.get_skill_context_prompt("open web browser")
            
            assert len(prompt) > 0
            assert "LEARNED SKILLS" in prompt or sample_skill.name in prompt
        finally:
            store_module.DEFAULT_STORE_PATH = original_path
    
    def test_enhance_procedural_memory(self, temp_dir, sample_skill):
        """Test prompt enhancement."""
        import gui_agents.s3.skills.store as store_module
        original_path = store_module.DEFAULT_STORE_PATH
        store_module.DEFAULT_STORE_PATH = temp_dir
        
        try:
            from gui_agents.s3.memory.skill_integration import SkillMemory
            memory = SkillMemory()
            memory.store.add_skill(sample_skill)
            memory.retriever.refresh_index()
            
            base_prompt = "You are a helpful assistant."
            enhanced = memory.enhance_procedural_memory(
                base_prompt=base_prompt,
                task_description="open Chrome browser",
            )
            
            assert enhanced.startswith(base_prompt)
            assert len(enhanced) >= len(base_prompt)
        finally:
            store_module.DEFAULT_STORE_PATH = original_path


# =============================================================================
# Stress Tests
# =============================================================================

class TestStress:
    """Stress tests for performance and edge cases."""
    
    def test_many_skills(self, skill_store):
        """Test adding many skills."""
        from gui_agents.s3.skills.models import Skill, Step, SkillMetadata
        
        n_skills = 50
        for i in range(n_skills):
            skill = Skill(
                id=f"skill_{i:03d}",
                name=f"Workflow {i}",
                summary=f"This is workflow number {i} that does something specific",
                steps=[
                    Step(number=j, title=f"Step {j}", action_description=f"Do action {j}")
                    for j in range(1, 6)
                ],
                metadata=SkillMetadata(
                    operating_system="macOS" if i % 2 == 0 else "Windows",
                    applications=["App1", "App2"] if i % 3 == 0 else ["App3"],
                ),
            )
            skill_store.add_skill(skill)
        
        stats = skill_store.stats()
        assert stats["total_skills"] == n_skills
        assert stats["total_steps"] == n_skills * 5
        
        # Search should still work
        results = skill_store.search_skills("workflow", n_results=10)
        assert len(results) >= 1
    
    def test_large_skill(self, skill_store):
        """Test skill with many steps."""
        from gui_agents.s3.skills.models import Skill, Step
        
        n_steps = 100
        skill = Skill(
            id="large_skill",
            name="Large Workflow",
            summary="A workflow with many steps",
            steps=[
                Step(
                    number=i,
                    title=f"Step {i}: Do something specific",
                    action_description=f"This is a detailed description of action {i} " * 5,
                    purpose=f"Purpose {i}",
                    expected_result=f"Result {i}",
                )
                for i in range(1, n_steps + 1)
            ],
        )
        
        skill_store.add_skill(skill)
        
        retrieved = skill_store.get_skill("large_skill")
        assert retrieved is not None
        assert len(retrieved.steps) == n_steps
    
    def test_sequential_access(self, temp_dir, sample_skill):
        """Test sequential access to the store from multiple instances.
        
        Note: ChromaDB with SQLite doesn't support concurrent writes from
        multiple clients well, so we test sequential access instead.
        """
        from gui_agents.s3.skills.store import SkillStore
        from gui_agents.s3.skills.models import Skill
        
        # Sequential writes from multiple store instances
        for i in range(5):
            store = SkillStore(store_path=temp_dir, use_sentence_transformers=False)
            skill = Skill(
                id=f"sequential_{i}",
                name=f"Sequential Skill {i}",
                summary=f"Added in iteration {i}",
            )
            store.add_skill(skill)
        
        # Final check - all skills should be accessible
        store = SkillStore(store_path=temp_dir, use_sentence_transformers=False)
        all_skills = store.get_all_skills()
        assert len(all_skills) == 5
    
    def test_long_text_content(self, skill_store):
        """Test handling of very long text content."""
        from gui_agents.s3.skills.models import Skill, Step
        
        long_text = "A" * 10000  # 10KB of text
        
        skill = Skill(
            id="long_text_skill",
            name="Long Text Skill",
            summary=long_text,
            steps=[
                Step(
                    number=1,
                    title="Long Step",
                    action_description=long_text,
                )
            ],
        )
        
        skill_store.add_skill(skill)
        
        retrieved = skill_store.get_skill("long_text_skill")
        assert retrieved is not None
        assert len(retrieved.summary) == 10000
    
    def test_special_character_search(self, skill_store):
        """Test search with special characters."""
        from gui_agents.s3.skills.models import Skill
        
        skill = Skill(
            id="special_chars",
            name="C++ & Python <Workflow>",
            summary="Handle 'special' characters in \"search\" [queries]",
        )
        
        skill_store.add_skill(skill)
        
        # These should not crash
        results = skill_store.search_skills("C++")
        results = skill_store.search_skills("&")
        results = skill_store.search_skills("<>")
        results = skill_store.search_skills("'quotes'")
    
    def test_empty_search(self, skill_store, sample_skill):
        """Test search with empty/whitespace query."""
        skill_store.add_skill(sample_skill)
        
        # Empty string
        results = skill_store.search_skills("")
        # Should handle gracefully
        
        # Whitespace only
        results = skill_store.search_skills("   ")
        # Should handle gracefully
    
    def test_duplicate_skill_ids(self, skill_store, sample_skill):
        """Test handling of duplicate skill IDs (upsert behavior)."""
        skill_store.add_skill(sample_skill)
        
        # Modify and add again with same ID
        sample_skill.name = "Modified Name"
        skill_store.add_skill(sample_skill)
        
        # Should only have one skill
        stats = skill_store.stats()
        assert stats["total_skills"] == 1
        
        # Should have updated name
        retrieved = skill_store.get_skill(sample_skill.id)
        assert retrieved.name == "Modified Name"
    
    def test_bm25_large_corpus(self):
        """Test BM25 with large corpus."""
        from gui_agents.s3.skills.retriever import BM25
        
        bm25 = BM25()
        
        # Create 1000 documents
        documents = {
            f"doc_{i}": f"document number {i} with content {' python' if i % 10 == 0 else ''}"
            for i in range(1000)
        }
        
        start = time.time()
        bm25.fit(documents)
        fit_time = time.time() - start
        
        start = time.time()
        results = bm25.search("python", top_k=50)
        search_time = time.time() - start
        
        # Should find ~100 documents with "python"
        assert len(results) >= 50
        
        # Should be reasonably fast
        assert fit_time < 5.0  # Under 5 seconds
        assert search_time < 1.0  # Under 1 second


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_get_nonexistent_skill(self, skill_store):
        """Test getting a skill that doesn't exist."""
        result = skill_store.get_skill("nonexistent_id")
        assert result is None
    
    def test_delete_nonexistent_skill(self, skill_store):
        """Test deleting a skill that doesn't exist."""
        result = skill_store.delete_skill("nonexistent_id")
        assert result is False
    
    def test_search_empty_store(self, skill_store):
        """Test searching an empty store."""
        results = skill_store.search_skills("anything")
        assert len(results) == 0
    
    def test_context_get_nonexistent(self, context_store):
        """Test getting nonexistent context."""
        result = context_store.get("nonexistent_key")
        assert result is None
    
    def test_retriever_empty_store(self, skill_store):
        """Test retriever with empty store."""
        from gui_agents.s3.skills.retriever import SkillRetriever
        
        retriever = SkillRetriever(skill_store)
        results = retriever.retrieve("anything")
        assert len(results) == 0
    
    def test_skill_with_none_values(self, skill_store):
        """Test skill with None values in optional fields."""
        from gui_agents.s3.skills.models import Skill, Step
        
        skill = Skill(
            id="none_values",
            name="Skill with None",
            summary="Test skill",
            steps=[
                Step(
                    number=1,
                    title="Step",
                    action_description="Action",
                    location=None,
                    ui_element=None,
                    action_type=None,
                )
            ],
        )
        
        skill_store.add_skill(skill)
        retrieved = skill_store.get_skill("none_values")
        
        assert retrieved is not None
        assert retrieved.steps[0].location is None
        assert retrieved.steps[0].ui_element is None


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    # Run with: python -m pytest test_memory_system.py -v
    pytest.main([__file__, "-v", "--tb=short"])
