"""
Agent-S MCP Server

Model Context Protocol server for GUI automation with Agent-S.
"""

__version__ = "0.1.0"

from .models import ConfigSchema, TaskState, TaskStatus, TaskResponse, TaskStatusResponse
from .task_manager import TaskManager
from .agent_wrapper import AgentWrapper
from .server import create_server

__all__ = [
    "ConfigSchema",
    "TaskState",
    "TaskStatus",
    "TaskResponse",
    "TaskStatusResponse",
    "TaskManager",
    "AgentWrapper",
    "create_server",
]
