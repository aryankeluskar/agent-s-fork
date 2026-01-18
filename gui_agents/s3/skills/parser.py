"""
Workflow Parser for Agent-S

Parses LLM-generated workflow documentation (log.md) into structured Skill objects
using LLM-based extraction for robust handling of varied formats.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Optional, Dict

from .models import (
    Skill, Step, Parameter, FailureMode, SkillMetadata,
    ActionType, UserContext, ContextType
)


PARSING_PROMPT = """You are a workflow document parser. Extract structured data from the given workflow documentation.

Parse the following markdown document and extract ALL information into the exact JSON schema below. Be thorough - extract every step, parameter, and detail present in the document.

CRITICAL RULES:
1. Extract ALL steps - do not skip any steps mentioned in the document
2. For each step, extract: number, title, action description, location coordinates (if present), UI element, purpose, expected result, action mapping
3. Infer action_type from the action description: "click", "type", "hotkey", "drag", "scroll", "wait", or "sequence"
4. For location coordinates, extract as [x, y] array if present (e.g., "(594, 466)" becomes [594, 466])
5. If a field is not present in the document, use null or empty array/object as appropriate
6. Parse ALL table rows for parameters, failure modes, and user context
7. Infer preconditions from prerequisites (what must be true before workflow can run)
8. Infer postconditions from the workflow outcome (what state changes after workflow completes)

JSON Schema to return:
{{
  "name": "Workflow name (from title)",
  "summary": "Executive summary text",
  "prerequisites": ["list of prerequisite strings"],
  "parameters": [
    {{
      "name": "parameter name",
      "param_type": "parameter type",
      "example": "example value", 
      "description": "parameter description"
    }}
  ],
  "steps": [
    {{
      "number": 1,
      "title": "Step title",
      "action_description": "What action to perform",
      "location": [x, y] or null,
      "ui_element": "UI element description or null",
      "purpose": "Why this step is needed",
      "expected_result": "What should happen after this step",
      "action_mapping": "Event mapping if present",
      "action_type": "click|type|hotkey|drag|scroll|wait|sequence"
    }}
  ],
  "visual_landmarks": {{
    "(x, y)": "landmark description"
  }},
  "timing_delays": {{
    "description": seconds_as_number
  }},
  "failure_modes": [
    {{
      "failure": "failure description",
      "likelihood": "Low|Medium|High|Very Low",
      "recovery": "recovery steps"
    }}
  ],
  "variations": ["list of alternative approaches"],
  "automation_suitability": 5,
  "operating_system": "The OS this workflow runs on (e.g., macOS, Windows, Linux)",
  "applications": ["list of application names used in this workflow"],
  "preconditions": ["list of conditions that must be true before workflow runs, e.g., 'user_authenticated', 'app_installed:chrome', 'file_exists:/path/to/file'"],
  "postconditions": ["list of conditions that become true after workflow completes, e.g., 'file_created', 'app_opened', 'data_submitted', 'clipboard_set'"],
  "user_context": [
    {{
      "key": "context key",
      "value": "context value",
      "context_type": "preference|url|entity|credential|pattern|style",
      "application": "app name",
      "description": "what this context means"
    }}
  ]
}}

DOCUMENT TO PARSE:
---
{content}
---

Return ONLY valid JSON matching the schema above. No explanations, no markdown code blocks, just the JSON object."""


class WorkflowParser:
    """
    Parses workflow documentation into structured Skill objects.
    
    Uses an LLM to extract structured data from markdown documentation,
    handling variations in formatting and structure robustly.
    """
    
    def __init__(
        self,
        model: str = "openai/gpt-4o-mini",
        api_key: Optional[str] = None,
    ):
        """
        Initialize the parser.
        
        Args:
            model: LLM model to use for parsing
            api_key: OpenRouter API key (or set OPENROUTER_API_KEY env var)
        """
        self.model = model
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        
        self._client = None
    
    @property
    def client(self):
        """Lazily initialize the OpenAI client."""
        if self._client is None and self.api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=self.api_key,
                )
            except ImportError:
                print("Warning: openai package not installed")
        return self._client
    
    def parse_file(self, file_path: Path) -> Optional[Skill]:
        """
        Parse a workflow documentation file into a Skill.
        
        Args:
            file_path: Path to the log.md file
            
        Returns:
            Skill object or None if parsing fails
        """
        if not file_path.exists():
            return None
        
        content = file_path.read_text(encoding="utf-8")
        return self.parse_content(content, source_file=str(file_path))
    
    def parse_content(self, content: str, source_file: str = "") -> Optional[Skill]:
        """
        Parse workflow documentation content into a Skill.
        
        Args:
            content: Markdown content of the workflow documentation
            source_file: Optional source file path for metadata
            
        Returns:
            Skill object or None if parsing fails
        """
        if not self.client:
            print("Warning: No API key available for LLM parsing")
            return self._fallback_parse(content, source_file)
        
        # Generate skill ID from content hash
        skill_id = hashlib.md5(content.encode()).hexdigest()[:12]
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": PARSING_PROMPT.format(content=content)}
                ],
                max_tokens=4000,
                temperature=0.1,
            )
            
            response_text = response.choices[0].message.content
            data = self._extract_json(response_text)
            
            if not data:
                print("Failed to parse LLM response as JSON")
                return self._fallback_parse(content, source_file)
            
            return self._build_skill(data, skill_id, source_file)
            
        except Exception as e:
            print(f"LLM parsing error: {e}")
            return self._fallback_parse(content, source_file)
    
    def _extract_json(self, text: str) -> Optional[Dict]:
        """Extract JSON from LLM response, handling markdown code blocks."""
        text = text.strip()
        
        # Remove markdown code blocks if present
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
        
        # Try to find JSON object in text
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
    
    def _build_skill(self, data: Dict, skill_id: str, source_file: str) -> Skill:
        """Build a Skill object from parsed data."""
        # Build steps
        steps = []
        for s in data.get("steps", []):
            location = None
            if s.get("location") and isinstance(s["location"], list) and len(s["location"]) == 2:
                location = tuple(s["location"])
            
            action_type = None
            if s.get("action_type"):
                try:
                    action_type = ActionType(s["action_type"].lower())
                except ValueError:
                    pass
            
            steps.append(Step(
                number=s.get("number", len(steps) + 1),
                title=s.get("title", ""),
                action_description=s.get("action_description", ""),
                location=location,
                ui_element=s.get("ui_element"),
                purpose=s.get("purpose", ""),
                expected_result=s.get("expected_result", ""),
                action_mapping=s.get("action_mapping", ""),
                action_type=action_type,
            ))
        
        # Build parameters (skip malformed entries)
        parameters = []
        for p in data.get("parameters", []):
            if p.get("name") and not p["name"].startswith(":"):
                parameters.append(Parameter(
                    name=p.get("name", ""),
                    param_type=p.get("param_type", p.get("type", "")),
                    example=p.get("example", ""),
                    description=p.get("description", ""),
                ))
        
        # Build failure modes (skip malformed entries)
        failure_modes = []
        for f in data.get("failure_modes", []):
            if f.get("failure") and not f["failure"].startswith(":"):
                failure_modes.append(FailureMode(
                    failure=f.get("failure", ""),
                    likelihood=f.get("likelihood", ""),
                    recovery=f.get("recovery", ""),
                ))
        
        # Build user context (skip malformed entries)
        user_context = []
        for uc in data.get("user_context", []):
            if uc.get("key") and not uc["key"].startswith(":"):
                try:
                    context_type = ContextType(uc.get("context_type", "preference").lower())
                except ValueError:
                    context_type = ContextType.PREFERENCE
                
                user_context.append(UserContext(
                    key=uc.get("key", ""),
                    value=uc.get("value", ""),
                    context_type=context_type,
                    application=uc.get("application", ""),
                    description=uc.get("description", ""),
                    source_skill_id=skill_id,
                ))
        
        # Build metadata
        recording_id = Path(source_file).parent.name if source_file else ""
        video_path = self._find_video_path(source_file)
        
        metadata = SkillMetadata(
            operating_system=data.get("operating_system", ""),
            applications=data.get("applications", []),
            automation_suitability=data.get("automation_suitability", 5),
            source_file=source_file,
            video_path=video_path,
            recording_id=recording_id,
        )
        
        return Skill(
            id=skill_id,
            name=data.get("name", "Unnamed Workflow"),
            summary=data.get("summary", ""),
            steps=steps,
            parameters=parameters,
            prerequisites=data.get("prerequisites", []),
            preconditions=data.get("preconditions", []),
            postconditions=data.get("postconditions", []),
            visual_landmarks=data.get("visual_landmarks", {}),
            timing_delays=data.get("timing_delays", {}),
            failure_modes=failure_modes,
            variations=data.get("variations", []),
            metadata=metadata,
            user_context=user_context,
        )
    
    def _find_video_path(self, source_file: str) -> Optional[str]:
        """Find video file in the same directory as source file."""
        if not source_file:
            return None
        
        source_path = Path(source_file)
        parent = source_path.parent
        
        video_extensions = {'.mp4', '.webm', '.mov', '.avi', '.mkv', '.m4v'}
        
        for file in parent.iterdir():
            if file.is_file() and file.suffix.lower() in video_extensions:
                return str(file)
        return None
    
    def _fallback_parse(self, content: str, source_file: str) -> Optional[Skill]:
        """
        Fallback parser for when LLM is unavailable.
        
        Extracts basic information using simple text parsing.
        """
        skill_id = hashlib.md5(content.encode()).hexdigest()[:12]
        
        # Extract title
        name = "Unnamed Workflow"
        for line in content.split("\n"):
            if line.startswith("# Workflow:"):
                name = line.replace("# Workflow:", "").strip()
                break
            elif line.startswith("# "):
                name = line[2:].strip()
                break
        
        # Extract summary (first paragraph after title)
        summary = ""
        lines = content.split("\n")
        in_summary = False
        for line in lines:
            if "Summary" in line or "Executive" in line:
                in_summary = True
                continue
            if in_summary and line.strip():
                if line.startswith("#"):
                    break
                summary += line.strip() + " "
        
        return Skill(
            id=skill_id,
            name=name,
            summary=summary.strip(),
            metadata=SkillMetadata(source_file=source_file),
        )
