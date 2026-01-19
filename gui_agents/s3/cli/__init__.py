"""
Agent-S CLI Package

Unified command-line interface for Agent-S:
- run: Execute the GUI agent
- record: Record workflows for skill learning
- voice: Voice-activated assistant
- skills: Manage learned skills
"""

from .main import main

__all__ = ["main"]
