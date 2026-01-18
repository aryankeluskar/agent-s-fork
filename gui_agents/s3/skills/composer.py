"""
Skill Composer for Agent-S

Composes multiple retrieved skills into unified execution plans using LLM-based
reasoning and intelligent step combination.
"""

import json
import os
from dataclasses import dataclass
from typing import Optional, List

from .models import Skill, Step
from .retriever import SkillRetriever, RetrievalResult


@dataclass
class ComposedPlan:
    """A plan composed from multiple skills."""
    goal: str
    sub_goals: List[str]
    skills_used: List[Skill]
    steps: List[dict]  # Unified step list
    reasoning: str
    confidence: float


# Prompt for decomposing goals into sub-goals
DECOMPOSITION_PROMPT = """You are a task decomposition expert. Given a user goal, break it down into atomic sub-goals that can each be accomplished by a single skill/workflow.

Rules:
1. Each sub-goal should be a single, clear action
2. Order sub-goals logically (dependencies first)
3. Be specific about WHAT needs to happen, not HOW
4. Return ONLY valid JSON

User Goal: {goal}

Available context about the user's system:
- OS: {os_info}
- Available apps: {apps}

Return a JSON object:
{{
  "sub_goals": ["sub-goal 1", "sub-goal 2", ...],
  "reasoning": "brief explanation of the decomposition"
}}"""


# Prompt for composing skills into a unified plan
COMPOSITION_PROMPT = """You are a workflow composition expert. Given a user goal and retrieved skills, create a unified execution plan by intelligently combining the relevant steps.

User Goal: {goal}

Retrieved Skills:
{skills_context}

## CRITICAL RULES

### ALWAYS EXCLUDE these from the plan:
- Recording software actions (any screen recording or capture related actions)
- Post-goal exploration (actions done AFTER the main goal is achieved)
- Meta-actions that are not part of the actual workflow

### ALWAYS INCLUDE in step descriptions:
- Actual URLs (e.g., "Navigate to canvas.asu.edu" not "Navigate to Canvas")
- Actual file paths, dimensions, values from parameters
- Specific application names

### Step Description Quality:
- BAD: "Open browser" → TOO VAGUE
- BAD: "Navigate to website" → MISSING URL
- GOOD: "Navigate to canvas.asu.edu in Brave browser"
- GOOD: "Type 'canvas.asu.edu' in address bar and press Enter"

## Instructions:
1. Filter out recording artifacts and post-goal actions
2. Extract only steps that accomplish the user's goal
3. Include actual parameter values in descriptions (URLs, paths, dimensions)
4. Ensure logical flow
5. Return ONLY valid JSON

Return a JSON object:
{{
  "steps": [
    {{
      "number": 1,
      "description": "Specific action with actual values (e.g., 'Navigate to canvas.asu.edu')",
      "action_type": "click|type|hotkey|sequence|wait",
      "source_skill": "skill name or 'combined'",
      "parameters": {{"url": "canvas.asu.edu"}}
    }}
  ],
  "skills_used": ["skill1", "skill2"],
  "reasoning": "explanation of how skills were combined",
  "confidence": 0.85
}}"""


# Prompt for validating a plan
VALIDATION_PROMPT = """You are a plan validator. Check if this execution plan is valid and will achieve the goal.

Goal: {goal}

Proposed Plan:
{plan}

Check for:
1. Missing steps
2. Incorrect order (dependencies violated)
3. Impossible actions
4. Parameter mismatches

Return a JSON object:
{{
  "is_valid": true/false,
  "issues": ["issue 1", "issue 2"],
  "suggestions": ["fix 1", "fix 2"]
}}"""


# Simple decomposition prompt for fallback
SIMPLE_DECOMPOSE_PROMPT = """Break this goal into separate sub-goals. Return ONLY a JSON array of strings.

Goal: {goal}

Example input: "open browser and search for cats"
Example output: ["open browser", "search for cats"]

Return ONLY a JSON array, no explanation:"""


class SkillComposer:
    """
    Composes multiple skills into unified execution plans.
    
    Uses LLM reasoning to:
    1. Decompose complex goals into sub-goals
    2. Retrieve relevant skills for each sub-goal
    3. Intelligently combine steps into a coherent plan
    """
    
    def __init__(
        self,
        retriever: SkillRetriever,
        model: str = "openai/gpt-4o-mini",
        api_key: Optional[str] = None,
    ):
        """
        Initialize the composer.
        
        Args:
            retriever: SkillRetriever instance
            model: LLM model for composition
            api_key: OpenRouter API key
        """
        self.retriever = retriever
        self.model = model
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.context_store = retriever.store.context_store
        
        # Initialize OpenAI client
        if self.api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=self.api_key,
                )
            except ImportError:
                self.client = None
        else:
            self.client = None
    
    def compose_plan(
        self,
        goal: str,
        os_info: str = "",
        available_apps: List[str] = None,
        max_skills: int = 5,
    ) -> ComposedPlan:
        """
        Compose a plan for achieving a goal.
        
        Args:
            goal: User's goal
            os_info: Operating system information
            available_apps: List of available applications
            max_skills: Maximum number of skills to use
            
        Returns:
            ComposedPlan object
        """
        # Decompose goal into sub-goals
        sub_goals = self._decompose_goal(goal, os_info, available_apps or [])
        
        # Retrieve skills for each sub-goal
        all_results: List[RetrievalResult] = []
        for sub_goal in sub_goals:
            results = self.retriever.retrieve_with_steps(
                query=sub_goal,
                n_skills=2,
                n_steps_per_skill=5,
            )
            all_results.extend(results)
        
        # Deduplicate skills
        seen_ids = set()
        unique_results = []
        for r in all_results:
            if r.skill.id not in seen_ids:
                seen_ids.add(r.skill.id)
                unique_results.append(r)
        
        unique_results = unique_results[:max_skills]
        
        # If no skills found, create fallback plan
        if not unique_results:
            return self._create_fallback_plan(goal, sub_goals)
        
        # Compose skills into unified plan
        composed = self._compose_from_skills(goal, sub_goals, unique_results)
        
        return composed
    
    def _decompose_goal(
        self,
        goal: str,
        os_info: str,
        available_apps: List[str],
    ) -> List[str]:
        """Decompose a goal into sub-goals using LLM."""
        if not self.client:
            return [goal]
        
        try:
            prompt = DECOMPOSITION_PROMPT.format(
                goal=goal,
                os_info=os_info or "unknown",
                apps=", ".join(available_apps) if available_apps else "unknown",
            )
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.3,
            )
            
            content = response.choices[0].message.content
            data = self._extract_json(content)
            
            if data and "sub_goals" in data:
                return data["sub_goals"]
        except Exception:
            pass
        
        # Fallback to simple decomposition
        return self._simple_decompose(goal)
    
    def _simple_decompose(self, goal: str) -> List[str]:
        """Simple goal decomposition without LLM."""
        if not self.client:
            return [goal]
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": SIMPLE_DECOMPOSE_PROMPT.format(goal=goal)}],
                max_tokens=200,
                temperature=0.1,
            )
            
            content = response.choices[0].message.content.strip()
            
            # Extract JSON array
            if content.startswith("```"):
                lines = content.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                content = "\n".join(lines)
            
            result = json.loads(content)
            if isinstance(result, list):
                return result
        except Exception:
            pass
        
        return [goal]
    
    def _compose_from_skills(
        self,
        goal: str,
        sub_goals: List[str],
        results: List[RetrievalResult],
    ) -> ComposedPlan:
        """Compose a plan from retrieved skills using LLM."""
        if not self.client:
            return self._simple_compose(goal, sub_goals, results)
        
        try:
            skills_context = self._build_skills_context(results)
            
            prompt = COMPOSITION_PROMPT.format(
                goal=goal,
                skills_context=skills_context,
            )
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.3,
            )
            
            content = response.choices[0].message.content
            data = self._extract_json(content)
            
            if data and "steps" in data:
                skills_used = [
                    r.skill for r in results 
                    if r.skill.name in data.get("skills_used", [])
                ]
                if not skills_used:
                    skills_used = [r.skill for r in results]
                
                return ComposedPlan(
                    goal=goal,
                    sub_goals=sub_goals,
                    skills_used=skills_used,
                    steps=data["steps"],
                    reasoning=data.get("reasoning", ""),
                    confidence=data.get("confidence", 0.7),
                )
        except Exception:
            pass
        
        return self._simple_compose(goal, sub_goals, results)
    
    def _simple_compose(
        self,
        goal: str,
        sub_goals: List[str],
        results: List[RetrievalResult],
    ) -> ComposedPlan:
        """Simple composition without LLM (concatenate steps)."""
        all_steps = []
        skills_used = []
        step_number = 1
        
        for result in results:
            skill = result.skill
            skills_used.append(skill)
            
            for step in skill.steps:
                all_steps.append({
                    "number": step_number,
                    "description": step.action_description or step.title,
                    "action_type": step.action_type.value if step.action_type else "click",
                    "source_skill": skill.name,
                    "location": list(step.location) if step.location else None,
                    "ui_element": step.ui_element,
                })
                step_number += 1
        
        return ComposedPlan(
            goal=goal,
            sub_goals=sub_goals,
            skills_used=skills_used,
            steps=all_steps,
            reasoning="Simple concatenation of retrieved skill steps",
            confidence=0.5,
        )
    
    def _build_skills_context(self, results: List[RetrievalResult]) -> str:
        """Build context string from skills for LLM prompt."""
        context_parts = []
        
        # Include user context if available
        user_context = self.context_store.get_all()
        if user_context:
            ctx_lines = ["## User Context (learned preferences, accounts, patterns)"]
            for ctx in user_context:
                ctx_lines.append(
                    f"- **{ctx.key}**: {ctx.value} ({ctx.context_type.value}, {ctx.application})"
                )
            context_parts.append("\n".join(ctx_lines))
        
        # Include skill information
        for i, result in enumerate(results, 1):
            skill = result.skill
            
            parts = [
                f"### Skill {i}: {skill.name}",
                f"Summary: {skill.summary}",
                f"Match Score: {result.score:.2f}",
            ]
            
            if skill.parameters:
                param_strs = [f"{p.name}={p.example}" for p in skill.parameters]
                parts.append(f"Parameters (user-specific values): {', '.join(param_strs)}")
            
            if skill.preconditions:
                parts.append(f"Preconditions: {', '.join(skill.preconditions)}")
            if skill.postconditions:
                parts.append(f"Postconditions: {', '.join(skill.postconditions)}")
            
            parts.append("Steps:")
            for step in skill.steps[:7]:  # Limit to 7 steps
                step_desc = f"  {step.number}. {step.title}"
                if step.action_description:
                    step_desc += f": {step.action_description[:100]}"
                if step.action_type:
                    step_desc += f" [{step.action_type.value}]"
                if step.location:
                    step_desc += f" at {step.location}"
                parts.append(step_desc)
            
            context_parts.append("\n".join(parts))
        
        return "\n\n".join(context_parts)
    
    def _create_fallback_plan(self, goal: str, sub_goals: List[str]) -> ComposedPlan:
        """Create a fallback plan when no skills match."""
        return ComposedPlan(
            goal=goal,
            sub_goals=sub_goals,
            skills_used=[],
            steps=[{
                "number": 1,
                "description": f"Execute: {goal}",
                "action_type": "sequence",
                "source_skill": "none",
                "parameters": {},
            }],
            reasoning="No matching skills found. Manual execution required.",
            confidence=0.1,
        )
    
    def _extract_json(self, text: str) -> Optional[dict]:
        """Extract JSON from LLM response."""
        text = text.strip()
        
        # Remove markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Find JSON object in text
        start = text.find('{')
        if start == -1:
            return None
        
        brace_count = 0
        end_pos = 0
        for i, char in enumerate(text[start:], start):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_pos = i + 1
                    break
        
        if end_pos > start:
            try:
                return json.loads(text[start:end_pos])
            except json.JSONDecodeError:
                pass
        
        return None
    
    def validate_plan(self, plan: ComposedPlan) -> dict:
        """
        Validate a composed plan.
        
        Args:
            plan: Plan to validate
            
        Returns:
            Dict with is_valid, issues, and suggestions
        """
        if not self.client:
            return {"is_valid": True, "issues": [], "suggestions": []}
        
        try:
            plan_str = json.dumps({
                "goal": plan.goal,
                "steps": plan.steps,
            }, indent=2)
            
            prompt = VALIDATION_PROMPT.format(
                goal=plan.goal,
                plan=plan_str,
            )
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.2,
            )
            
            content = response.choices[0].message.content
            data = self._extract_json(content)
            
            if data:
                return data
        except Exception:
            pass
        
        return {"is_valid": True, "issues": [], "suggestions": []}
    
    def to_agent_plan(self, composed: ComposedPlan) -> List[dict]:
        """
        Convert a composed plan to Agent-S agent plan format.
        
        Args:
            composed: ComposedPlan object
            
        Returns:
            List of step dicts in agent format
        """
        agent_steps = []
        
        for step in composed.steps:
            agent_step = {
                "step": step["number"],
                "description": step["description"],
                "expected_action": step.get("action_type", "click"),
            }
            agent_steps.append(agent_step)
        
        return agent_steps
