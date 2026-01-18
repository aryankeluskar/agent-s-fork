"""
Recording Module for Agent-S

Provides screen recording capabilities with event capture for learning workflows.
Records mouse/keyboard events alongside screen video for later analysis and skill extraction.
"""

from .recorder import Recorder, get_recordings_dir, get_latest_recording
from .convert_events import load_events, convert_events, simplify_events
from .analyze import analyze_recording
from .post_recording import PostRecordingPipeline, process_recording

__all__ = [
    # Recorder
    "Recorder",
    "get_recordings_dir",
    "get_latest_recording",
    # Event conversion
    "load_events",
    "convert_events", 
    "simplify_events",
    # Analysis
    "analyze_recording",
    # Pipeline
    "PostRecordingPipeline",
    "process_recording",
]
