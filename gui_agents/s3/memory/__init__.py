"""
Memory Module for Agent-S

Provides procedural memory for task execution and skill integration
for learning from recorded workflows.
"""

from .procedural_memory import PROCEDURAL_MEMORY
from .skill_integration import (
    SkillMemory,
    get_skill_memory,
    enhance_prompt_with_skills,
)

__all__ = [
    "PROCEDURAL_MEMORY",
    "SkillMemory",
    "get_skill_memory",
    "enhance_prompt_with_skills",
]
