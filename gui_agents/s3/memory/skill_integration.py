"""
Skill Integration for Agent-S Memory

Integrates the skills system into Agent-S procedural memory,
providing skill-augmented prompts and context for task execution.
"""

import platform
from typing import Optional, List

from gui_agents.s3.skills import (
    SkillStore,
    SkillRetriever,
    SkillComposer,
    RetrievalResult,
    ComposedPlan,
)


class SkillMemory:
    """
    Integrates skills into Agent-S procedural memory.
    
    Provides:
    - Skill retrieval for task-relevant workflows
    - User context for personalization
    - Composed plans from multiple skills
    """
    
    def __init__(self):
        """Initialize the skill memory system."""
        self._store: Optional[SkillStore] = None
        self._retriever: Optional[SkillRetriever] = None
        self._composer: Optional[SkillComposer] = None
    
    @property
    def store(self) -> SkillStore:
        """Lazily initialize skill store."""
        if self._store is None:
            self._store = SkillStore()
        return self._store
    
    @property
    def retriever(self) -> SkillRetriever:
        """Lazily initialize skill retriever."""
        if self._retriever is None:
            self._retriever = SkillRetriever(self.store)
        return self._retriever
    
    @property
    def composer(self) -> SkillComposer:
        """Lazily initialize skill composer."""
        if self._composer is None:
            self._composer = SkillComposer(self.retriever)
        return self._composer
    
    def has_skills(self) -> bool:
        """Check if any skills are indexed."""
        return self.store.stats()["total_skills"] > 0
    
    def get_relevant_skills(
        self,
        task_description: str,
        n_results: int = 3,
    ) -> List[RetrievalResult]:
        """
        Retrieve skills relevant to a task.
        
        Args:
            task_description: Description of the task
            n_results: Number of skills to retrieve
            
        Returns:
            List of RetrievalResult objects
        """
        if not self.has_skills():
            return []
        
        return self.retriever.retrieve_with_steps(
            query=task_description,
            n_skills=n_results,
            n_steps_per_skill=5,
        )
    
    def compose_plan(self, goal: str) -> Optional[ComposedPlan]:
        """
        Compose a plan from relevant skills.
        
        Args:
            goal: User's goal
            
        Returns:
            ComposedPlan or None if no skills available
        """
        if not self.has_skills():
            return None
        
        return self.composer.compose_plan(
            goal=goal,
            os_info=platform.system(),
        )
    
    def get_skill_context_prompt(
        self,
        task_description: str,
        n_skills: int = 2,
    ) -> str:
        """
        Generate a prompt addition with skill context for a task.
        
        Args:
            task_description: Description of the task
            n_skills: Number of skills to include
            
        Returns:
            Prompt string with skill context
        """
        if not self.has_skills():
            return ""
        
        results = self.get_relevant_skills(task_description, n_skills)
        
        if not results:
            return ""
        
        # Build context string
        parts = [
            "\n\n## LEARNED SKILLS (from previous recordings)",
            "The following workflows have been learned and may be relevant to this task:",
        ]
        
        for i, result in enumerate(results, 1):
            skill = result.skill
            parts.append(f"\n### Skill {i}: {skill.name}")
            parts.append(f"Relevance: {result.score:.0%}")
            parts.append(f"Summary: {skill.summary}")
            
            if skill.parameters:
                param_strs = [f"{p.name}={p.example}" for p in skill.parameters[:5]]
                parts.append(f"Parameters: {', '.join(param_strs)}")
            
            if skill.steps:
                parts.append("Key steps:")
                for step in skill.steps[:5]:
                    parts.append(f"  {step.number}. {step.title}")
        
        parts.append(
            "\nUse these skills as reference when relevant, "
            "but adapt to the specific task at hand."
        )
        
        return "\n".join(parts)
    
    def get_user_context_prompt(self, filter_app: Optional[str] = None) -> str:
        """
        Generate a prompt addition with user context.
        
        Args:
            filter_app: Optional application to filter by
            
        Returns:
            Prompt string with user context
        """
        context_store = self.store.context_store
        context_str = context_store.to_context_string(filter_app)
        
        if not context_str:
            return ""
        
        return f"\n\n## USER CONTEXT\n{context_str}"
    
    def enhance_procedural_memory(
        self,
        base_prompt: str,
        task_description: str,
        include_skills: bool = True,
        include_context: bool = True,
    ) -> str:
        """
        Enhance a procedural memory prompt with skill and context information.
        
        Args:
            base_prompt: Base procedural memory prompt
            task_description: Current task description
            include_skills: Whether to include relevant skills
            include_context: Whether to include user context
            
        Returns:
            Enhanced prompt
        """
        enhanced = base_prompt
        
        if include_skills:
            skill_context = self.get_skill_context_prompt(task_description)
            if skill_context:
                enhanced += skill_context
        
        if include_context:
            user_context = self.get_user_context_prompt()
            if user_context:
                enhanced += user_context
        
        return enhanced


# Global instance for easy access
_skill_memory: Optional[SkillMemory] = None


def get_skill_memory() -> SkillMemory:
    """Get the global skill memory instance."""
    global _skill_memory
    if _skill_memory is None:
        _skill_memory = SkillMemory()
    return _skill_memory


def enhance_prompt_with_skills(
    base_prompt: str,
    task_description: str,
) -> str:
    """
    Convenience function to enhance a prompt with skills and context.
    
    Args:
        base_prompt: Base prompt to enhance
        task_description: Task description for skill retrieval
        
    Returns:
        Enhanced prompt
    """
    return get_skill_memory().enhance_procedural_memory(
        base_prompt=base_prompt,
        task_description=task_description,
    )
