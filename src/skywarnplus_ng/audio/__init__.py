"""
Audio processing and TTS for SkywarnPlus-NG.
"""

from .tts_engine import GTTSEngine, TTSEngineError
from .manager import AudioManager, AudioManagerError

__all__ = [
    "GTTSEngine",
    "TTSEngineError", 
    "AudioManager",
    "AudioManagerError",
]
