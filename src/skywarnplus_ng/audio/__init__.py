"""
Audio processing and TTS for SkywarnPlus-NG.
"""

from .tts_engine import AslTTSEngine, GTTSEngine, TTSEngineError
from .manager import AudioManager, AudioManagerError
from .tail_message import TailMessageManager, TailMessageError

__all__ = [
    "AslTTSEngine",
    "GTTSEngine",
    "TTSEngineError",
    "AudioManager",
    "AudioManagerError",
    "TailMessageManager",
    "TailMessageError",
]
