"""
Audio processing and TTS for SkywarnPlus-NG.
"""

from .manager import AudioManager, AudioManagerError
from .tail_message import TailMessageError, TailMessageManager
from .tts_engine import AslTTSEngine, GTTSEngine, TTSEngineError

__all__ = [
    "AslTTSEngine",
    "AudioManager",
    "AudioManagerError",
    "GTTSEngine",
    "TTSEngineError",
    "TailMessageError",
    "TailMessageManager",
]
