"""
Agent-S Voice Module

Voice-activated assistant with:
- Wake word detection (openwakeword)
- Speech transcription (Wispr Flow API)
- Transparent overlay UI (PyQt5)
"""

from .assistant import VoiceAssistant
from .transcriber import WisprTranscriber
from .overlay import TransparentOverlay

__all__ = [
    "VoiceAssistant",
    "WisprTranscriber", 
    "TransparentOverlay",
]
