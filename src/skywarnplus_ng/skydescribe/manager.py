"""
SkyDescribe Manager - Handles generation and management of weather description audio files.
"""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from ..core.models import WeatherAlert
from ..audio.tts_engine import GTTSEngine, TTSEngineError
from ..audio.manager import AudioManager, AudioManagerError

logger = logging.getLogger(__name__)


class SkyDescribeError(Exception):
    """SkyDescribe error."""
    pass


@dataclass
class DescriptionAudio:
    """Description audio file metadata."""
    alert_id: str
    file_path: Path
    created_at: datetime
    duration_seconds: float
    description_text: str


class SkyDescribeManager:
    """Manages weather description audio generation and DTMF functionality."""
    
    def __init__(self, audio_manager: AudioManager, descriptions_dir: Path):
        """
        Initialize SkyDescribe manager.
        
        Args:
            audio_manager: Audio manager for TTS functionality
            descriptions_dir: Directory to store description audio files
        """
        self.audio_manager = audio_manager
        self.descriptions_dir = descriptions_dir
        self.descriptions_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache of generated description audio files
        self._description_cache: Dict[str, DescriptionAudio] = {}
        
        # DTMF code mappings
        self.dtmf_codes = {
            "*1": "current_alerts",
            "*2": "alert_by_id", 
            "*3": "all_clear",
            "*4": "system_status",
            "*5": "help"
        }
    
    async def generate_description_audio(self, alert: WeatherAlert) -> Optional[DescriptionAudio]:
        """
        Generate audio file for alert description.
        
        Args:
            alert: Weather alert to generate description for
            
        Returns:
            DescriptionAudio object or None if generation failed
        """
        try:
            # Check if we already have this description
            if alert.id in self._description_cache:
                cached = self._description_cache[alert.id]
                if cached.file_path.exists():
                    logger.debug(f"Using cached description for alert {alert.id}")
                    return cached
            
            # Create description text
            description_text = self._create_description_text(alert)
            
            # Generate unique filename
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"desc_{alert.id}_{timestamp}.{self.audio_manager.config.tts.output_format}"
            output_path = self.descriptions_dir / filename
            
            # Generate audio using the audio manager's TTS engine
            audio_path = self.audio_manager.tts_engine.synthesize(description_text, output_path)
            
            if not audio_path or not audio_path.exists():
                logger.error(f"Failed to generate description audio for alert {alert.id}")
                return None
            
            # Get audio duration
            duration = self.audio_manager.tts_engine.get_audio_duration(audio_path)
            
            # Create description audio object
            desc_audio = DescriptionAudio(
                alert_id=alert.id,
                file_path=audio_path,
                created_at=datetime.now(timezone.utc),
                duration_seconds=duration,
                description_text=description_text
            )
            
            # Cache the result
            self._description_cache[alert.id] = desc_audio
            
            logger.info(f"Generated description audio for alert {alert.id}: {audio_path}")
            return desc_audio
            
        except Exception as e:
            logger.error(f"Error generating description audio for alert {alert.id}: {e}")
            return None
    
    def _create_description_text(self, alert: WeatherAlert) -> str:
        """
        Create comprehensive description text for alert.
        
        Args:
            alert: Weather alert
            
        Returns:
            Formatted description text
        """
        parts = []
        
        # Alert type and area
        parts.append(f"Weather alert: {alert.event}")
        parts.append(f"Affected area: {alert.area_desc}")
        
        # Add headline if available
        if alert.headline:
            parts.append(f"Headline: {alert.headline}")
        
        # Add full description
        if alert.description:
            parts.append(f"Description: {alert.description}")
        
        # Add instructions if available
        if alert.instruction:
            parts.append(f"Instructions: {alert.instruction}")
        
        # Add timing information
        parts.append(f"Effective: {alert.effective.strftime('%B %d, %Y at %I:%M %p')}")
        parts.append(f"Expires: {alert.expires.strftime('%B %d, %Y at %I:%M %p')}")
        
        # Add severity and urgency
        parts.append(f"Severity: {alert.severity.value}")
        parts.append(f"Urgency: {alert.urgency.value}")
        parts.append(f"Certainty: {alert.certainty.value}")
        
        return ". ".join(parts) + "."
    
    async def generate_current_alerts_description(self, alerts: List[WeatherAlert]) -> Optional[DescriptionAudio]:
        """
        Generate description for all current active alerts.
        
        Args:
            alerts: List of current active alerts
            
        Returns:
            DescriptionAudio object or None if generation failed
        """
        try:
            if not alerts:
                # Generate "no alerts" message
                text = "There are currently no active weather alerts in your area."
            else:
                # Create summary text
                parts = [f"There are currently {len(alerts)} active weather alerts:"]
                
                for i, alert in enumerate(alerts, 1):
                    parts.append(f"Alert {i}: {alert.event} for {alert.area_desc}")
                    if alert.description:
                        # Truncate description for summary
                        desc = alert.description[:200] + "..." if len(alert.description) > 200 else alert.description
                        parts.append(f"Details: {desc}")
                
                text = ". ".join(parts) + "."
            
            # Generate unique filename for current alerts
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"current_alerts_{timestamp}.{self.audio_manager.config.tts.output_format}"
            output_path = self.descriptions_dir / filename
            
            # Generate audio
            audio_path = self.audio_manager.tts_engine.synthesize(text, output_path)
            
            if not audio_path or not audio_path.exists():
                logger.error("Failed to generate current alerts description audio")
                return None
            
            # Get duration
            duration = self.audio_manager.tts_engine.get_audio_duration(audio_path)
            
            # Create description audio object
            desc_audio = DescriptionAudio(
                alert_id="current_alerts",
                file_path=audio_path,
                created_at=datetime.now(timezone.utc),
                duration_seconds=duration,
                description_text=text
            )
            
            logger.info(f"Generated current alerts description: {audio_path}")
            return desc_audio
            
        except Exception as e:
            logger.error(f"Error generating current alerts description: {e}")
            return None
    
    async def generate_all_clear_description(self) -> Optional[DescriptionAudio]:
        """Generate all-clear description audio."""
        try:
            text = "All weather alerts have been cleared. There are no active weather warnings or watches in your area at this time."
            
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"all_clear_{timestamp}.{self.audio_manager.config.tts.output_format}"
            output_path = self.descriptions_dir / filename
            
            audio_path = self.audio_manager.tts_engine.synthesize(text, output_path)
            
            if not audio_path or not audio_path.exists():
                logger.error("Failed to generate all-clear description audio")
                return None
            
            duration = self.audio_manager.tts_engine.get_audio_duration(audio_path)
            
            desc_audio = DescriptionAudio(
                alert_id="all_clear",
                file_path=audio_path,
                created_at=datetime.now(timezone.utc),
                duration_seconds=duration,
                description_text=text
            )
            
            logger.info(f"Generated all-clear description: {audio_path}")
            return desc_audio
            
        except Exception as e:
            logger.error(f"Error generating all-clear description: {e}")
            return None
    
    async def generate_system_status_description(self, status: Dict[str, Any]) -> Optional[DescriptionAudio]:
        """Generate system status description audio."""
        try:
            parts = ["SkywarnPlus-NG System Status"]
            
            if status.get('running', False):
                parts.append("System is running normally")
                parts.append(f"Active alerts: {status.get('active_alerts', 0)}")
                parts.append(f"Uptime: {self._format_uptime(status.get('uptime_seconds', 0))}")
            else:
                parts.append("System is not running")
            
            parts.append("For detailed information, visit the web dashboard")
            
            text = ". ".join(parts) + "."
            
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"system_status_{timestamp}.{self.audio_manager.config.tts.output_format}"
            output_path = self.descriptions_dir / filename
            
            audio_path = self.audio_manager.tts_engine.synthesize(text, output_path)
            
            if not audio_path or not audio_path.exists():
                logger.error("Failed to generate system status description audio")
                return None
            
            duration = self.audio_manager.tts_engine.get_audio_duration(audio_path)
            
            desc_audio = DescriptionAudio(
                alert_id="system_status",
                file_path=audio_path,
                created_at=datetime.now(timezone.utc),
                duration_seconds=duration,
                description_text=text
            )
            
            logger.info(f"Generated system status description: {audio_path}")
            return desc_audio
            
        except Exception as e:
            logger.error(f"Error generating system status description: {e}")
            return None
    
    def cleanup_alert_description(self, alert_id: str) -> int:
        """
        Clean up description audio files for a specific alert ID.
        
        Args:
            alert_id: Alert ID to clean up description files for
            
        Returns:
            Number of files cleaned up
        """
        if not self.descriptions_dir.exists():
            return 0
        
        cleaned_count = 0
        
        # Remove from cache
        if alert_id in self._description_cache:
            cached = self._description_cache[alert_id]
            if cached.file_path.exists():
                try:
                    cached.file_path.unlink()
                    cleaned_count += 1
                    logger.debug(f"Cleaned up cached description file for alert {alert_id}: {cached.file_path}")
                except OSError as e:
                    logger.warning(f"Failed to clean up cached description file {cached.file_path}: {e}")
            del self._description_cache[alert_id]
        
        # Also check for any files matching the pattern (in case cache was cleared)
        import fnmatch
        for file_path in self.descriptions_dir.iterdir():
            if file_path.is_file():
                try:
                    filename = file_path.name
                    # Match pattern: desc_{alert_id}_*
                    if fnmatch.fnmatch(filename, f"desc_{alert_id}_*"):
                        file_path.unlink()
                        cleaned_count += 1
                        logger.debug(f"Cleaned up description file for alert {alert_id}: {file_path}")
                except OSError as e:
                    logger.warning(f"Failed to clean up description file {file_path}: {e}")
        
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} description file(s) for alert {alert_id}")
        
        return cleaned_count
    
    def _format_uptime(self, uptime_seconds: int) -> str:
        """Format uptime in a human-readable way."""
        hours = uptime_seconds // 3600
        minutes = (uptime_seconds % 3600) // 60
        
        if hours > 0:
            return f"{hours} hours and {minutes} minutes"
        else:
            return f"{minutes} minutes"
    
    def get_description_audio(self, alert_id: str) -> Optional[DescriptionAudio]:
        """Get cached description audio by alert ID."""
        return self._description_cache.get(alert_id)
    
    def cleanup_old_descriptions(self, max_age_hours: int = 24) -> int:
        """
        Clean up old description audio files.
        
        Args:
            max_age_hours: Maximum age of files to keep
            
        Returns:
            Number of files cleaned up
        """
        cleaned_count = 0
        cutoff_time = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)
        
        for alert_id, desc_audio in list(self._description_cache.items()):
            if desc_audio.created_at.timestamp() < cutoff_time:
                try:
                    if desc_audio.file_path.exists():
                        desc_audio.file_path.unlink()
                    del self._description_cache[alert_id]
                    cleaned_count += 1
                except Exception as e:
                    logger.warning(f"Failed to clean up description audio {alert_id}: {e}")
        
        logger.info(f"Cleaned up {cleaned_count} old description audio files")
        return cleaned_count
