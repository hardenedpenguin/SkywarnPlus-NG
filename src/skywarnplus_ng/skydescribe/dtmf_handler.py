"""
DTMF Handler - Handles DTMF code processing and Asterisk integration.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from enum import Enum

from .manager import SkyDescribeManager, DescriptionAudio

logger = logging.getLogger(__name__)


class DTMFCode(str, Enum):
    """DTMF codes for SkyDescribe functionality."""
    CURRENT_ALERTS = "*1"
    ALERT_BY_ID = "*2"
    ALL_CLEAR = "*3"
    SYSTEM_STATUS = "*4"
    HELP = "*5"


@dataclass
class DTMFResponse:
    """Response to a DTMF code."""
    code: str
    success: bool
    message: str
    audio_file: Optional[str] = None
    duration_seconds: Optional[float] = None


class DTMFHandler:
    """Handles DTMF code processing and response generation."""
    
    def __init__(self, sky_describe_manager: SkyDescribeManager, dtmf_codes: Optional[Dict[str, str]] = None):
        """
        Initialize DTMF handler.
        
        Args:
            sky_describe_manager: SkyDescribe manager instance
            dtmf_codes: Dictionary of DTMF codes (optional, uses defaults if not provided)
        """
        self.sky_describe_manager = sky_describe_manager
        
        # Set up DTMF codes (use provided or defaults)
        self.dtmf_codes = dtmf_codes or {
            "current_alerts": "*1",
            "alert_by_id": "*2", 
            "all_clear": "*3",
            "system_status": "*4",
            "help": "*5"
        }
        
        # Callback functions for getting current data
        self.get_current_alerts: Optional[Callable[[], List[Any]]] = None
        self.get_system_status: Optional[Callable[[], Dict[str, Any]]] = None
        self.get_alert_by_id: Optional[Callable[[str], Optional[Any]]] = None
        
        # DTMF code handlers
        self._handlers = {
            "current_alerts": self._handle_current_alerts,
            "alert_by_id": self._handle_alert_by_id,
            "all_clear": self._handle_all_clear,
            "system_status": self._handle_system_status,
            "help": self._handle_help
        }
    
    def set_callbacks(
        self,
        get_current_alerts: Callable[[], List[Any]],
        get_system_status: Callable[[], Dict[str, Any]],
        get_alert_by_id: Callable[[str], Optional[Any]]
    ) -> None:
        """
        Set callback functions for getting current data.
        
        Args:
            get_current_alerts: Function to get current active alerts
            get_system_status: Function to get system status
            get_alert_by_id: Function to get alert by ID
        """
        self.get_current_alerts = get_current_alerts
        self.get_system_status = get_system_status
        self.get_alert_by_id = get_alert_by_id
    
    async def process_dtmf_code(self, code: str, additional_digits: str = "") -> DTMFResponse:
        """
        Process a DTMF code and return appropriate response.
        
        Args:
            code: DTMF code (e.g., "*1", "*2", "*9", "**1")
            additional_digits: Additional digits for codes that need them (e.g., alert ID for alert_by_id)
            
        Returns:
            DTMFResponse with audio file path and metadata
        """
        try:
            # Find which command this code maps to
            command = None
            for cmd, dtmf_code in self.dtmf_codes.items():
                if code == dtmf_code:
                    command = cmd
                    break
            
            if not command:
                return DTMFResponse(
                    code=code,
                    success=False,
                    message=f"Invalid DTMF code: {code}. Available codes: {list(self.dtmf_codes.values())}"
                )
            
            # Get handler for this command
            handler = self._handlers.get(command)
            if not handler:
                return DTMFResponse(
                    code=code,
                    success=False,
                    message=f"No handler for command: {command}"
                )
            
            # Process the code
            return await handler(additional_digits)
            
        except Exception as e:
            logger.error(f"Error processing DTMF code {code}: {e}")
            return DTMFResponse(
                code=code,
                success=False,
                message=f"Error processing DTMF code: {str(e)}"
            )
    
    async def _handle_current_alerts(self, additional_digits: str) -> DTMFResponse:
        """Handle *1 - Current alerts."""
        try:
            if not self.get_current_alerts:
                return DTMFResponse(
                    code=DTMFCode.CURRENT_ALERTS.value,
                    success=False,
                    message="Current alerts callback not set"
                )
            
            # Get current alerts
            alerts = self.get_current_alerts()
            
            # Generate description audio
            desc_audio = await self.sky_describe_manager.generate_current_alerts_description(alerts)
            
            if not desc_audio:
                return DTMFResponse(
                    code=DTMFCode.CURRENT_ALERTS.value,
                    success=False,
                    message="Failed to generate current alerts description"
                )
            
            return DTMFResponse(
                code=DTMFCode.CURRENT_ALERTS.value,
                success=True,
                message=f"Current alerts description generated",
                audio_file=str(desc_audio.file_path),
                duration_seconds=desc_audio.duration_seconds
            )
            
        except Exception as e:
            logger.error(f"Error handling current alerts DTMF: {e}")
            return DTMFResponse(
                code=DTMFCode.CURRENT_ALERTS.value,
                success=False,
                message=f"Error generating current alerts: {str(e)}"
            )
    
    async def _handle_alert_by_id(self, additional_digits: str) -> DTMFResponse:
        """Handle *2 - Alert by ID."""
        try:
            if not additional_digits:
                return DTMFResponse(
                    code=DTMFCode.ALERT_BY_ID.value,
                    success=False,
                    message="Alert ID required. Use *2 followed by 4-digit alert ID"
                )
            
            if not self.get_alert_by_id:
                return DTMFResponse(
                    code=DTMFCode.ALERT_BY_ID.value,
                    success=False,
                    message="Alert lookup callback not set"
                )
            
            # Get alert by ID
            alert = self.get_alert_by_id(additional_digits)
            if not alert:
                return DTMFResponse(
                    code=DTMFCode.ALERT_BY_ID.value,
                    success=False,
                    message=f"Alert not found: {additional_digits}"
                )
            
            # Generate description audio
            desc_audio = await self.sky_describe_manager.generate_description_audio(alert)
            
            if not desc_audio:
                return DTMFResponse(
                    code=DTMFCode.ALERT_BY_ID.value,
                    success=False,
                    message=f"Failed to generate description for alert {additional_digits}"
                )
            
            return DTMFResponse(
                code=DTMFCode.ALERT_BY_ID.value,
                success=True,
                message=f"Alert {additional_digits} description generated",
                audio_file=str(desc_audio.file_path),
                duration_seconds=desc_audio.duration_seconds
            )
            
        except Exception as e:
            logger.error(f"Error handling alert by ID DTMF: {e}")
            return DTMFResponse(
                code=DTMFCode.ALERT_BY_ID.value,
                success=False,
                message=f"Error generating alert description: {str(e)}"
            )
    
    async def _handle_all_clear(self, additional_digits: str) -> DTMFResponse:
        """Handle *3 - All clear."""
        try:
            # Generate all-clear description
            desc_audio = await self.sky_describe_manager.generate_all_clear_description()
            
            if not desc_audio:
                return DTMFResponse(
                    code=DTMFCode.ALL_CLEAR.value,
                    success=False,
                    message="Failed to generate all-clear description"
                )
            
            return DTMFResponse(
                code=DTMFCode.ALL_CLEAR.value,
                success=True,
                message="All-clear description generated",
                audio_file=str(desc_audio.file_path),
                duration_seconds=desc_audio.duration_seconds
            )
            
        except Exception as e:
            logger.error(f"Error handling all-clear DTMF: {e}")
            return DTMFResponse(
                code=DTMFCode.ALL_CLEAR.value,
                success=False,
                message=f"Error generating all-clear: {str(e)}"
            )
    
    async def _handle_system_status(self, additional_digits: str) -> DTMFResponse:
        """Handle *4 - System status."""
        try:
            if not self.get_system_status:
                return DTMFResponse(
                    code=DTMFCode.SYSTEM_STATUS.value,
                    success=False,
                    message="System status callback not set"
                )
            
            # Get system status
            status = self.get_system_status()
            
            # Generate status description
            desc_audio = await self.sky_describe_manager.generate_system_status_description(status)
            
            if not desc_audio:
                return DTMFResponse(
                    code=DTMFCode.SYSTEM_STATUS.value,
                    success=False,
                    message="Failed to generate system status description"
                )
            
            return DTMFResponse(
                code=DTMFCode.SYSTEM_STATUS.value,
                success=True,
                message="System status description generated",
                audio_file=str(desc_audio.file_path),
                duration_seconds=desc_audio.duration_seconds
            )
            
        except Exception as e:
            logger.error(f"Error handling system status DTMF: {e}")
            return DTMFResponse(
                code=DTMFCode.SYSTEM_STATUS.value,
                success=False,
                message=f"Error generating system status: {str(e)}"
            )
    
    async def _handle_help(self, additional_digits: str) -> DTMFResponse:
        """Handle help - Help."""
        try:
            # Build help text with configured DTMF codes
            help_text = (
                "SkywarnPlus-NG DTMF Commands: "
                f"{self.dtmf_codes['current_alerts']} for current weather alerts. "
                f"{self.dtmf_codes['alert_by_id']} followed by 4-digit alert ID for specific alert details. "
                f"{self.dtmf_codes['all_clear']} for all-clear status. "
                f"{self.dtmf_codes['system_status']} for system status. "
                f"{self.dtmf_codes['help']} for this help message. "
                "All commands use rpt localplay to play audio files."
            )
            
            # Generate help audio
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"help_{timestamp}.wav"
            output_path = self.sky_describe_manager.descriptions_dir / filename
            
            audio_path = self.sky_describe_manager.audio_manager.tts_engine.synthesize(help_text, output_path)
            
            if not audio_path or not audio_path.exists():
                return DTMFResponse(
                    code=DTMFCode.HELP.value,
                    success=False,
                    message="Failed to generate help audio"
                )
            
            duration = self.sky_describe_manager.audio_manager.tts_engine.get_audio_duration(audio_path)
            
            return DTMFResponse(
                code=DTMFCode.HELP.value,
                success=True,
                message="Help audio generated",
                audio_file=str(audio_path),
                duration_seconds=duration
            )
            
        except Exception as e:
            logger.error(f"Error handling help DTMF: {e}")
            return DTMFResponse(
                code=DTMFCode.HELP.value,
                success=False,
                message=f"Error generating help: {str(e)}"
            )
    
    def get_available_codes(self) -> List[str]:
        """Get list of available DTMF codes."""
        return list(self.dtmf_codes.values())
    
    def get_code_description(self, code: str) -> str:
        """Get description of what a DTMF code does."""
        descriptions = {
            "current_alerts": "Play current active weather alerts",
            "alert_by_id": "Play specific alert details (requires 4-digit ID)",
            "all_clear": "Play all-clear status message",
            "system_status": "Play system status information",
            "help": "Play this help message"
        }
        
        # Find which command this code maps to
        command = None
        for cmd, dtmf_code in self.dtmf_codes.items():
            if code == dtmf_code:
                command = cmd
                break
        
        return descriptions.get(command, "Unknown DTMF code")
    
    def get_code_mapping(self) -> Dict[str, str]:
        """Get mapping of DTMF codes to their functions."""
        return {
            self.dtmf_codes["current_alerts"]: "Current active weather alerts",
            self.dtmf_codes["alert_by_id"]: "Specific alert details (requires 4-digit ID)",
            self.dtmf_codes["all_clear"]: "All-clear status message",
            self.dtmf_codes["system_status"]: "System status information",
            self.dtmf_codes["help"]: "Help and available commands"
        }
