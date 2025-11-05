"""
Audio processing and TTS for SkywarnPlus-NG.
"""

from .tts_engine import GTTSEngine, PiperTSEngine, TTSEngineError
from .manager import AudioManager, AudioManagerError
from .tail_message import TailMessageManager, TailMessageError

__all__ = [
    "GTTSEngine",
    "PiperTSEngine",
    "TTSEngineError", 
    "AudioManager",
    "AudioManagerError",
    "TailMessageManager",
    "TailMessageError",
]
