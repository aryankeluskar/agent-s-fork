"""
Data Models for Agent-S Skills System

Defines the structured representations of workflows, steps, parameters,
and user context learned from screen recordings.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from enum import Enum


class ContextType(Enum):
    """Types of user context that can be extracted from recordings."""
    CREDENTIAL = "credential"  # Account URLs, usernames (NOT passwords)
    PREFERENCE = "preference"  # User's preferred settings, formats, styles
    ENTITY = "entity"          # People, organizations the user interacts with
    PATTERN = "pattern"        # Recurring behaviors, templates, default choices
    URL = "url"                # Important URLs the user accesses
    STYLE = "style"            # Documentation style, naming conventions


class ActionType(Enum):
    """Types of actions in workflow steps."""
    CLICK = "click"
    TYPE = "type"
    HOTKEY = "hotkey"
    DRAG = "drag"
    SCROLL = "scroll"
    WAIT = "wait"
    SEQUENCE = "sequence"


@dataclass
class UserContext:
    """
    User-specific context extracted from recordings.
    
    Represents reusable knowledge about the user's accounts, preferences,
    and patterns that can be applied to future tasks.
    """
    key: str                           # Context identifier (e.g., "canvas_url")
    value: str                         # Context value (e.g., "https://canvas.asu.edu")
    context_type: ContextType          # Type of context
    application: str = ""              # Associated application (e.g., "Chrome")
    description: str = ""              # Human-readable description
    source_skill_id: str = ""          # ID of skill this was extracted from
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "key": self.key,
            "value": self.value,
            "context_type": self.context_type.value,
            "application": self.application,
            "description": self.description,
            "source_skill_id": self.source_skill_id,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "UserContext":
        """Create from dictionary."""
        return cls(
            key=data["key"],
            value=data["value"],
            context_type=ContextType(data["context_type"]),
            application=data.get("application", ""),
            description=data.get("description", ""),
            source_skill_id=data.get("source_skill_id", ""),
        )


@dataclass
class Step:
    """
    A single step in a workflow.
    
    Represents an atomic action with coordinates, expected results,
    and metadata for reliable automation.
    """
    number: int                        # Step number (1-indexed)
    title: str                         # Step title
    action_description: str            # Detailed action description
    location: Optional[Tuple[int, int]] = None  # Screen coordinates (x, y)
    ui_element: Optional[str] = None   # UI element description
    purpose: str = ""                  # Why this step is necessary
    expected_result: str = ""          # What should happen after this step
    action_mapping: str = ""           # Which recorded actions this maps to
    action_type: Optional[ActionType] = None  # Type of action
    
    def to_embedding_text(self) -> str:
        """Generate text for embedding/search."""
        parts = [f"Step {self.number}: {self.title}"]
        if self.action_description:
            parts.append(f"Action: {self.action_description}")
        if self.ui_element:
            parts.append(f"UI Element: {self.ui_element}")
        if self.purpose:
            parts.append(f"Purpose: {self.purpose}")
        return " | ".join(parts)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "number": self.number,
            "title": self.title,
            "action_description": self.action_description,
            "location": list(self.location) if self.location else None,
            "ui_element": self.ui_element,
            "purpose": self.purpose,
            "expected_result": self.expected_result,
            "action_mapping": self.action_mapping,
            "action_type": self.action_type.value if self.action_type else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Step":
        """Create from dictionary."""
        return cls(
            number=data["number"],
            title=data["title"],
            action_description=data["action_description"],
            location=tuple(data["location"]) if data.get("location") else None,
            ui_element=data.get("ui_element"),
            purpose=data.get("purpose", ""),
            expected_result=data.get("expected_result", ""),
            action_mapping=data.get("action_mapping", ""),
            action_type=ActionType(data["action_type"]) if data.get("action_type") else None,
        )


@dataclass
class Parameter:
    """A configurable parameter in a workflow."""
    name: str                          # Parameter name
    param_type: str                    # Type (String, Integer, URL, etc.)
    example: str                       # Example value from recording
    description: str                   # Description of the parameter
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "type": self.param_type,
            "example": self.example,
            "description": self.description,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Parameter":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            param_type=data.get("type", ""),
            example=data.get("example", ""),
            description=data.get("description", ""),
        )


@dataclass
class FailureMode:
    """A potential failure mode in a workflow."""
    failure: str                       # Description of the failure
    likelihood: str                    # Low, Medium, High, Very Low
    recovery: str                      # Recovery steps
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "failure": self.failure,
            "likelihood": self.likelihood,
            "recovery": self.recovery,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "FailureMode":
        """Create from dictionary."""
        return cls(
            failure=data["failure"],
            likelihood=data.get("likelihood", ""),
            recovery=data.get("recovery", ""),
        )


@dataclass
class SkillMetadata:
    """Metadata about a skill's source and compatibility."""
    operating_system: str = ""         # OS this skill was recorded on
    applications: List[str] = field(default_factory=list)  # Apps used
    automation_suitability: int = 0    # 1-10 rating
    source_file: str = ""              # Path to source log.md
    video_path: Optional[str] = None   # Path to source video
    recording_id: str = ""             # ID of source recording
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "operating_system": self.operating_system,
            "applications": self.applications,
            "automation_suitability": self.automation_suitability,
            "source_file": self.source_file,
            "video_path": self.video_path,
            "recording_id": self.recording_id,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "SkillMetadata":
        """Create from dictionary."""
        return cls(
            operating_system=data.get("operating_system", ""),
            applications=data.get("applications", []),
            automation_suitability=data.get("automation_suitability", 0),
            source_file=data.get("source_file", ""),
            video_path=data.get("video_path"),
            recording_id=data.get("recording_id", ""),
        )


@dataclass
class Skill:
    """
    A complete workflow skill learned from a recording.
    
    Contains structured information about how to perform a task,
    including steps, parameters, preconditions, and user context.
    """
    id: str                            # Unique skill ID (hash-based)
    name: str                          # Workflow name
    summary: str                       # Executive summary
    steps: List[Step] = field(default_factory=list)
    parameters: List[Parameter] = field(default_factory=list)
    prerequisites: List[str] = field(default_factory=list)  # Required setup
    preconditions: List[str] = field(default_factory=list)  # State requirements
    postconditions: List[str] = field(default_factory=list)  # State after completion
    visual_landmarks: Dict[str, str] = field(default_factory=dict)  # (x,y) -> description
    timing_delays: Dict[str, float] = field(default_factory=dict)  # description -> seconds
    failure_modes: List[FailureMode] = field(default_factory=list)
    variations: List[str] = field(default_factory=list)  # Alternative methods
    metadata: SkillMetadata = field(default_factory=SkillMetadata)
    user_context: List[UserContext] = field(default_factory=list)
    
    def to_summary_embedding_text(self) -> str:
        """Generate short text for embedding/search."""
        apps = ", ".join(self.metadata.applications) if self.metadata.applications else "unknown"
        os_info = self.metadata.operating_system or "unknown"
        return f"[{os_info}] [{apps}] {self.name}: {self.summary}"
    
    def to_full_embedding_text(self) -> str:
        """Generate full text for detailed embedding/search."""
        parts = [self.to_summary_embedding_text()]
        
        if self.parameters:
            param_strs = [f"{p.name}={p.example}" for p in self.parameters]
            parts.append(f"Parameters: {', '.join(param_strs)}")
        
        if self.prerequisites:
            parts.append(f"Prerequisites: {', '.join(self.prerequisites)}")
        
        if self.preconditions:
            parts.append(f"Preconditions: {', '.join(self.preconditions)}")
        
        # Include first few steps
        step_summaries = [
            f"- {s.title}: {s.action_description[:100]}" 
            for s in self.steps[:5] if s.action_description
        ]
        if step_summaries:
            parts.append(f"Steps: {'; '.join(step_summaries)}")
        
        return " | ".join(parts)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "summary": self.summary,
            "steps": [s.to_dict() for s in self.steps],
            "parameters": [p.to_dict() for p in self.parameters],
            "prerequisites": self.prerequisites,
            "preconditions": self.preconditions,
            "postconditions": self.postconditions,
            "visual_landmarks": self.visual_landmarks,
            "timing_delays": self.timing_delays,
            "failure_modes": [f.to_dict() for f in self.failure_modes],
            "variations": self.variations,
            "metadata": self.metadata.to_dict(),
            "user_context": [uc.to_dict() for uc in self.user_context],
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Skill":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            summary=data["summary"],
            steps=[Step.from_dict(s) for s in data.get("steps", [])],
            parameters=[Parameter.from_dict(p) for p in data.get("parameters", [])],
            prerequisites=data.get("prerequisites", []),
            preconditions=data.get("preconditions", []),
            postconditions=data.get("postconditions", []),
            visual_landmarks=data.get("visual_landmarks", {}),
            timing_delays=data.get("timing_delays", {}),
            failure_modes=[FailureMode.from_dict(f) for f in data.get("failure_modes", [])],
            variations=data.get("variations", []),
            metadata=SkillMetadata.from_dict(data.get("metadata", {})),
            user_context=[UserContext.from_dict(uc) for uc in data.get("user_context", [])],
        )
