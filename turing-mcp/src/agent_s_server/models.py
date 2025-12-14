"""
Data models for Agent-S MCP server.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class TaskStatus(str, Enum):
    """Task execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ConfigSchema(BaseModel):
    """Session-level configuration for Agent-S."""
    
    # Main generation model (required)
    model_provider: str = Field(..., description="Provider (openai, anthropic, gemini)")
    model_name: str = Field(..., description="Model name (e.g., gpt-4o)")
    model_api_key: str = Field(..., description="API key for main model")
    model_url: Optional[str] = Field(None, description="Custom base URL")
    model_temperature: Optional[float] = Field(None, description="Temperature for generation model")
    
    # Grounding model (required - for UI coordinate generation)
    ground_provider: str = Field(..., description="Provider (openai, huggingface)")
    ground_model: str = Field(..., description="Model name (e.g., uitars-7b)")
    ground_url: str = Field(..., description="Grounding endpoint URL")
    ground_api_key: Optional[str] = Field(None, description="API key if needed")
    grounding_width: int = Field(1120, description="Screenshot width for grounding model")
    grounding_height: int = Field(1120, description="Screenshot height for grounding model")
    
    # Agent behavior
    enable_reflection: bool = Field(True, description="Enable reflection agent")
    max_steps: int = Field(15, description="Maximum steps per task")
    max_trajectory_length: int = Field(8, description="Maximum trajectory length")
    enable_local_env: bool = Field(False, description="Enable local code execution environment")


class StepInfo(BaseModel):
    """Information about a single execution step."""
    step_number: int
    plan: Optional[str] = None
    reflection: Optional[str] = None
    code: Optional[str] = None
    error: Optional[str] = None
    timestamp: float


class TaskState(BaseModel):
    """State of a running or completed task."""
    task_id: str
    instruction: str
    status: TaskStatus
    current_step: int = 0
    max_steps: int = 15
    steps: List[StepInfo] = Field(default_factory=list)
    latest_screenshot: Optional[str] = None  # Base64 encoded PNG
    error: Optional[str] = None
    created_at: float
    updated_at: float
    completed_at: Optional[float] = None


class TaskResponse(BaseModel):
    """Response for task operations."""
    task_id: str
    status: str
    message: Optional[str] = None


class TaskStatusResponse(BaseModel):
    """Detailed status response."""
    task_id: str
    status: str
    current_step: int
    max_steps: int
    plan_history: List[str]
    latest_screenshot: Optional[str] = None
    error: Optional[str] = None
