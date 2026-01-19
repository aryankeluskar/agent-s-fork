"""
GUI Agents - Agent-S

A library for creating general purpose GUI agents using multimodal LLMs.

Agent-S provides:
- GUI automation via Agent-S3 (the SOTA model)
- Workflow recording for skill learning
- Voice-activated assistant
- Skill management and retrieval

Usage:
    # As a CLI tool
    agent_s run --provider openai --model gpt-4o ...
    agent_s record start --name "my workflow"
    agent_s voice start
    agent_s skills search "resize image"

    # As a library
    from gui_agents.s3.agents import AgentS3
    from gui_agents.s3.recording import Recorder
    from gui_agents.s3.voice import VoiceAssistant
"""

__version__ = "0.4.0"

# Re-export main components from s3
from gui_agents.s3.agents.agent_s import AgentS3
from gui_agents.s3.agents.grounding import OSWorldACI

__all__ = [
    "AgentS3",
    "OSWorldACI",
    "__version__",
]
