"""
Skills Library for Agent-S

A hierarchical retrieval system for workflow automation that:
1. Indexes workflow documentation (log.md files) into structured skills
2. Supports semantic search over skills with metadata filtering
3. Enables intelligent composition of multiple skills into coherent plans

Architecture:
- SkillStore: Hierarchical vector store (workflow summaries + atomic steps)
- SkillRetriever: Hybrid search (semantic + BM25 + metadata filtering)
- SkillComposer: LLM-based composition of retrieved skills into plans
- UserContextStore: Stores user preferences extracted from recordings
"""

from .models import (
    Skill,
    Step,
    Parameter,
    FailureMode,
    SkillMetadata,
    UserContext,
    ContextType,
    ActionType,
)
from .parser import WorkflowParser
from .store import SkillStore
from .retriever import SkillRetriever, RetrievalResult
from .composer import SkillComposer, ComposedPlan
from .context_store import UserContextStore

__all__ = [
    # Models
    "Skill",
    "Step",
    "Parameter",
    "FailureMode",
    "SkillMetadata",
    "UserContext",
    "ContextType",
    "ActionType",
    # Parser
    "WorkflowParser",
    # Store
    "SkillStore",
    # Retriever
    "SkillRetriever",
    "RetrievalResult",
    # Composer
    "SkillComposer",
    "ComposedPlan",
    # Context
    "UserContextStore",
]
