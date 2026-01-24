"""
Configuration management for SkywarnPlus-NG.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from ruamel.yaml import YAML

logger = logging.getLogger(__name__)


class NWSApiConfig(BaseModel):
    """NWS API configuration."""

    base_url: str = Field("https://api.weather.gov", description="NWS API base URL")
    timeout: int = Field(30, description="Request timeout in seconds")
    user_agent: str = Field("SkywarnPlus-NG", description="User agent for API requests")


class CountyConfig(BaseModel):
    """County configuration."""

    code: str = Field(..., description="County code (e.g., TXC039)")
    name: Optional[str] = Field(None, description="County name")
    enabled: bool = Field(True, description="Enable alerts for this county")
    audio_file: Optional[str] = Field(None, description="Audio file for county name (e.g., 'Galveston.wav')")


class CourtesyToneConfig(BaseModel):
    """Courtesy tone configuration."""

    enabled: bool = Field(False, description="Enable automatic courtesy tone switching")
    tone_dir: Path = Field(Path("SOUNDS/TONES"), description="Directory where tone files are stored")
    tones: Dict[str, Dict[str, str]] = Field(
        default_factory=dict,
        description="Mapping of CT keys to Normal/WX tone files (e.g., {'ct1': {'Normal': 'Boop.ulaw', 'WX': 'Stardust.ulaw'}})"
    )
    ct_alerts: List[str] = Field(
        default_factory=list,
        description="List of alert events that trigger WX mode (glob patterns supported)"
    )


class IDChangeConfig(BaseModel):
    """ID change configuration."""

    enabled: bool = Field(False, description="Enable automatic ID changing")
    id_dir: Path = Field(Path("SOUNDS/ID"), description="Directory where ID files are stored")
    normal_id: str = Field("NORMALID.ulaw", description="Audio file for normal mode ID")
    wx_id: str = Field("WXID.ulaw", description="Audio file for WX mode ID")
    rpt_id: str = Field("RPTID.ulaw", description="Audio file that Asterisk uses as ID")
    id_alerts: List[str] = Field(
        default_factory=list,
        description="List of alert events that trigger WX mode (glob patterns supported)"
    )


class NodeConfig(BaseModel):
    """Node configuration with optional per-node county monitoring."""

    number: int = Field(..., description="Node number")
    counties: Optional[List[str]] = Field(None, description="County codes this node monitors (e.g., ['TXC039', 'TXC201']). If null/empty, node monitors all enabled counties.")


class AsteriskConfig(BaseModel):
    """Asterisk configuration."""

    enabled: bool = Field(True, description="Enable Asterisk integration")
    nodes: List[int | NodeConfig] = Field(default_factory=list, description="Target node numbers or node configurations with per-node counties")
    audio_delay: int = Field(0, description="Audio delay in milliseconds")
    playback_mode: str = Field("local", description="Playback mode: 'local' (default) or 'global' for rpt playback")
    courtesy_tones: CourtesyToneConfig = Field(default_factory=CourtesyToneConfig, description="Courtesy tone configuration")
    id_change: IDChangeConfig = Field(default_factory=IDChangeConfig, description="ID change configuration")
    
    def get_nodes_list(self) -> List[int]:
        """Get list of all node numbers regardless of format."""
        result = []
        for node in self.nodes:
            if isinstance(node, int):
                result.append(node)
            elif isinstance(node, NodeConfig):
                result.append(node.number)
            elif isinstance(node, dict):
                result.append(node.get('number', node.get('node', 0)))
        return result
    
    def get_node_config(self, node_number: int) -> Optional[NodeConfig]:
        """Get configuration for a specific node."""
        for node in self.nodes:
            if isinstance(node, NodeConfig) and node.number == node_number:
                return node
            elif isinstance(node, dict) and node.get('number') == node_number:
                return NodeConfig(**node)
        return None
    
    def get_counties_for_node(self, node_number: int) -> Optional[List[str]]:
        """Get county codes for a specific node. Returns None if node monitors all counties."""
        node_config = self.get_node_config(node_number)
        if node_config and node_config.counties:
            return node_config.counties
        return None


class TTSConfig(BaseModel):
    """Text-to-Speech configuration."""

    engine: str = Field("gtts", description="TTS engine to use: 'gtts' or 'piper'")
    language: str = Field("en", description="Language code (for gTTS)")
    tld: str = Field("com", description="Top-level domain for gTTS")
    slow: bool = Field(False, description="Slow down speech (for gTTS)")
    # Piper-specific settings
    model_path: Optional[str] = Field(None, description="Path to Piper TTS model file (.onnx)")
    speed: float = Field(1.0, description="Speech speed/rate for Piper TTS (1.0 = normal, >1.0 = faster, <1.0 = slower)")
    output_format: str = Field("wav", description="Output audio format")
    sample_rate: int = Field(22050, description="Sample rate in Hz")
    bit_rate: int = Field(128, description="Bit rate in kbps")


class AudioConfig(BaseModel):
    """Audio configuration."""

    sounds_path: Path = Field(Path("SOUNDS"), description="Path to sounds directory")
    alert_sound: str = Field("Duncecap.wav", description="Alert sound file")
    all_clear_sound: str = Field("Triangles.wav", description="All clear sound file")
    separator_sound: str = Field("Woodblock.wav", description="Alert separator sound")
    tts: TTSConfig = Field(default_factory=TTSConfig, description="TTS configuration")
    temp_dir: Path = Field(Path("/tmp/skywarnplus-ng-audio"), description="Temporary audio directory")


class FilteringConfig(BaseModel):
    """Alert filtering configuration."""

    max_alerts: int = Field(99, description="Maximum number of alerts to process")
    blocked_events: List[str] = Field(default_factory=list, description="Globally blocked events")
    say_alert_blocked: List[str] = Field(default_factory=list, description="Events blocked from voice announcement")
    tail_message_blocked: List[str] = Field(default_factory=list, description="Events blocked from tail message")


class AlertConfig(BaseModel):
    """Alert behavior configuration."""

    say_alert: bool = Field(True, description="Enable voice announcements")
    say_all_clear: bool = Field(True, description="Enable all-clear announcements")
    tail_message: bool = Field(True, description="Enable tail messages")
    tail_message_path: Optional[Path] = Field(None, description="Path for tail message file (default: /var/lib/skywarnplus-ng/data/wx-tail.wav)")
    tail_message_suffix: Optional[str] = Field(None, description="Optional suffix audio file to append to tail message")
    tail_message_counties: bool = Field(False, description="Include county names in tail message")
    with_county_names: bool = Field(False, description="Include county names in announcements")
    time_type: str = Field("onset", description="Time type: 'onset' or 'effective'")
    say_alert_suffix: Optional[str] = Field(None, description="Optional suffix audio file to append to alert announcements")
    say_all_clear_suffix: Optional[str] = Field(None, description="Optional suffix audio file to append to all-clear announcements")
    say_alerts_changed: bool = Field(True, description="Announce alerts when county list changes")
    say_alert_all: bool = Field(False, description="Say all alerts when one changes (requires SayAlertsChanged)")
    with_multiples: bool = Field(False, description="Tag alerts with 'with multiples' if multiple instances exist")


class ScriptConfig(BaseModel):
    """Script configuration for a specific alert type."""

    command: str = Field(..., description="Command to execute")
    args: List[str] = Field(default_factory=list, description="Command arguments")
    timeout: int = Field(30, description="Script timeout in seconds")
    enabled: bool = Field(True, description="Enable this script")
    working_dir: Optional[Path] = Field(None, description="Working directory for script")
    env_vars: Dict[str, str] = Field(default_factory=dict, description="Environment variables")


class AlertScriptMappingConfig(BaseModel):
    """AlertScript mapping configuration."""

    type: str = Field("BASH", description="Command type: BASH or DTMF")
    commands: List[str] = Field(default_factory=list, description="Commands to execute")
    triggers: List[str] = Field(default_factory=list, description="Alert event patterns that trigger this mapping")
    match: str = Field("ANY", description="Match type: ANY (default) or ALL")
    nodes: List[int] = Field(default_factory=list, description="Node numbers for DTMF commands")
    clear_commands: Optional[List[str]] = Field(None, description="Commands to execute when alerts clear")


class ScriptsConfig(BaseModel):
    """Scripts configuration."""

    enabled: bool = Field(True, description="Enable script execution")
    alert_scripts: Dict[str, ScriptConfig] = Field(default_factory=dict, description="Scripts for specific alert types")
    all_clear_script: Optional[ScriptConfig] = Field(None, description="Script for all-clear events")
    default_timeout: int = Field(30, description="Default script timeout in seconds")
    # Enhanced AlertScript configuration (mapping-based)
    alertscript_enabled: bool = Field(False, description="Enable enhanced AlertScript (mapping-based)")
    alertscript_mappings: List[AlertScriptMappingConfig] = Field(
        default_factory=list,
        description="AlertScript mappings (alert patterns to commands)"
    )
    alertscript_active_commands: Optional[List[AlertScriptMappingConfig]] = Field(
        None,
        description="Commands to execute when alerts go from 0 to non-zero"
    )
    alertscript_inactive_commands: Optional[List[AlertScriptMappingConfig]] = Field(
        None,
        description="Commands to execute when alerts go from non-zero to 0"
    )


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = Field("INFO", description="Log level")
    file: Optional[Path] = Field(None, description="Log file path")
    format: str = Field("json", description="Log format: 'json' or 'text'")


class AuthConfig(BaseModel):
    """Authentication configuration."""

    enabled: bool = Field(True, description="Enable authentication for web dashboard")
    username: str = Field("admin", description="Admin username")
    password: str = Field("skywarn123", description="Admin password (change this!)")
    session_timeout_hours: int = Field(24, description="Session timeout in hours")
    secret_key: Optional[str] = Field(None, description="Secret key for session encryption (auto-generated if not set)")


class HttpServerConfig(BaseModel):
    """HTTP server configuration."""

    enabled: bool = Field(True, description="Enable HTTP server")
    host: str = Field("0.0.0.0", description="Server host")
    port: int = Field(8100, description="Server port")
    base_path: str = Field("", description="Base path for reverse proxy (e.g., '/skywarnplus-ng')")
    auth: AuthConfig = Field(default_factory=AuthConfig)


class MetricsConfig(BaseModel):
    """Metrics configuration."""

    enabled: bool = Field(True, description="Enable metrics collection")
    retention_days: int = Field(7, description="Metrics retention in days")


class DatabaseConfig(BaseModel):
    """Database configuration."""

    enabled: bool = Field(True, description="Enable database storage")
    url: Optional[str] = Field(None, description="Database URL (defaults to SQLite)")
    cleanup_interval_hours: int = Field(24, description="Data cleanup interval in hours")
    retention_days: int = Field(30, description="Data retention period in days")
    backup_enabled: bool = Field(False, description="Enable automatic backups")
    backup_interval_hours: int = Field(24, description="Backup interval in hours")


class MonitoringConfig(BaseModel):
    """Monitoring configuration."""

    enabled: bool = Field(True, description="Enable monitoring")
    health_check_interval: int = Field(60, description="Health check interval in seconds")
    http_server: HttpServerConfig = Field(default_factory=HttpServerConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)


class DTMFConfig(BaseModel):
    """DTMF codes configuration."""

    current_alerts: str = Field("*1", description="DTMF code for current alerts")
    alert_by_id: str = Field("*2", description="DTMF code for specific alert by ID")
    all_clear: str = Field("*3", description="DTMF code for all-clear status")
    system_status: str = Field("*4", description="DTMF code for system status")
    help: str = Field("*5", description="DTMF code for help")


class SkyDescribeConfig(BaseModel):
    """SkyDescribe configuration."""

    enabled: bool = Field(True, description="Enable SkyDescribe DTMF system")
    descriptions_dir: Path = Field(Path("/var/lib/skywarnplus-ng/descriptions"), description="Directory for description audio files")
    cleanup_interval_hours: int = Field(24, description="Cleanup interval for old audio files")
    max_file_age_hours: int = Field(48, description="Maximum age of audio files before cleanup")
    dtmf_codes: DTMFConfig = Field(default_factory=DTMFConfig)
    max_words: int = Field(150, description="Maximum words in description")


class PushOverConfig(BaseModel):
    """PushOver notification configuration."""

    enabled: bool = Field(False, description="Enable PushOver notifications")
    api_token: Optional[str] = Field(None, description="PushOver application API token")
    user_key: Optional[str] = Field(None, description="PushOver user key")
    priority: int = Field(0, description="Default priority (-2 to 2, 0 is normal)")
    sound: Optional[str] = Field(None, description="Default sound (None uses device default)")
    timeout_seconds: int = Field(30, description="Request timeout in seconds")
    retry_count: int = Field(3, description="Number of retry attempts")
    retry_delay_seconds: int = Field(5, description="Delay between retries in seconds")


class DevConfig(BaseModel):
    """Development and testing configuration."""

    inject_enabled: bool = Field(False, description="Enable test alert injection (for testing)")
    inject_alerts: List[Dict[str, Any]] = Field(default_factory=list, description="List of test alerts to inject")
    cleanslate: bool = Field(False, description="Clear all cached state on startup")


class AppConfig(BaseSettings):
    """Application configuration."""

    # Core settings
    model_config = SettingsConfigDict(
        env_file=None,  # Disable .env file loading (not needed for YAML-based config)
        env_file_encoding="utf-8",
        extra="allow",
        case_sensitive=False,
    )

    # Application settings
    enabled: bool = Field(True, description="Enable SkywarnPlus-NG")
    config_file: Path = Field(Path("config.yaml"), description="Configuration file path")
    data_dir: Path = Field(Path("/var/lib/skywarnplus-ng/data"), description="Data directory")
    poll_interval: int = Field(60, description="Poll interval in seconds")

    # Component configurations
    nws: NWSApiConfig = Field(default_factory=NWSApiConfig)
    counties: List[CountyConfig] = Field(default_factory=list)
    asterisk: AsteriskConfig = Field(default_factory=AsteriskConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    filtering: FilteringConfig = Field(default_factory=FilteringConfig)
    alerts: AlertConfig = Field(default_factory=AlertConfig)
    scripts: ScriptsConfig = Field(default_factory=ScriptsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    skydescribe: SkyDescribeConfig = Field(default_factory=SkyDescribeConfig)
    pushover: PushOverConfig = Field(default_factory=PushOverConfig)
    dev: DevConfig = Field(default_factory=DevConfig)

    @classmethod
    def from_yaml(cls, config_path = None) -> "AppConfig":
        """Load configuration from YAML file."""
        if config_path is None:
            config_path = Path("config/default.yaml")
        elif isinstance(config_path, str):
            config_path = Path(config_path)
        
        if not config_path.exists():
            # Return default config if file doesn't exist
            config = cls()
            config._normalize_paths(Path.cwd())
            return config
        
        yaml = YAML(typ='safe')
        with open(config_path, 'r') as f:
            yaml_data = yaml.load(f)
        
        # Create config from YAML data
        config = cls(**yaml_data)
        config._normalize_paths(config_path.parent)
        return config

    def get_nodes_for_counties(self, county_codes: List[str]) -> List[int]:
        """
        Get list of node numbers that should receive alerts for the given counties.
        
        Args:
            county_codes: List of county codes from an alert
            
        Returns:
            List of node numbers that monitor any of the specified counties
        """
        if not county_codes:
            return []
        
        result = []
        for node in self.asterisk.nodes:
            if isinstance(node, int):
                # Simple int format means monitor all counties
                result.append(node)
            elif isinstance(node, NodeConfig):
                # Check if node has specific counties configured
                if node.counties:
                    # Node has specific counties - check for overlap
                    if any(county in node.counties for county in county_codes):
                        result.append(node.number)
                else:
                    # Node has no counties specified, monitors all
                    result.append(node.number)
            elif isinstance(node, dict):
                # Dictionary format (for backward compatibility)
                node_number = node.get('number', 0)
                node_counties = node.get('counties')
                if node_counties:
                    if any(county in node_counties for county in county_codes):
                        result.append(node_number)
                else:
                    result.append(node_number)
        
        return list(set(result))  # Remove duplicates
    
    def get_all_monitored_counties(self) -> List[str]:
        """
        Get list of all county codes that should be monitored based on node configurations.
        
        Returns:
            List of unique county codes that at least one node monitors
        """
        monitored = set()
        
        # Check if any node monitors all counties (simple int or NodeConfig with no counties)
        monitors_all = False
        for node in self.asterisk.nodes:
            if isinstance(node, int):
                monitors_all = True
                break
            elif isinstance(node, NodeConfig) and not node.counties:
                monitors_all = True
                break
            elif isinstance(node, dict) and not node.get('counties'):
                monitors_all = True
                break
        
        if monitors_all:
            # At least one node monitors all counties, return all enabled counties
            return [c.code for c in self.counties if c.enabled]
        
        # Otherwise, collect specific counties from node configurations
        for node in self.asterisk.nodes:
            if isinstance(node, NodeConfig) and node.counties:
                monitored.update(node.counties)
            elif isinstance(node, dict) and node.get('counties'):
                monitored.update(node.get('counties'))
        
        # Filter to only enabled counties
        enabled_codes = {c.code for c in self.counties if c.enabled}
        return list(monitored & enabled_codes)
    
    def validate_node_county_mapping(self) -> List[str]:
        """
        Validate node-county configuration and return list of warnings/errors.
        
        Returns:
            List of validation warning messages (empty if all valid)
        """
        warnings = []
        
        if not self.asterisk.nodes:
            return warnings
        
        # Get all enabled county codes
        enabled_counties = {c.code for c in self.counties if c.enabled}
        
        # Get all monitored counties
        monitored_counties = set(self.get_all_monitored_counties())
        
        # Check for enabled counties that no node monitors
        unmonitored = enabled_counties - monitored_counties
        if unmonitored:
            warnings.append(
                f"The following enabled counties are not monitored by any node: {', '.join(sorted(unmonitored))}"
            )
        
        # Check for node configurations referencing invalid counties
        for node in self.asterisk.nodes:
            node_number = None
            node_counties = None
            
            if isinstance(node, NodeConfig):
                node_number = node.number
                node_counties = node.counties
            elif isinstance(node, dict):
                node_number = node.get('number', 'unknown')
                node_counties = node.get('counties')
            
            if node_counties:
                # Check for invalid county codes
                invalid_counties = set(node_counties) - {c.code for c in self.counties}
                if invalid_counties:
                    warnings.append(
                        f"Node {node_number} references invalid county codes: {', '.join(sorted(invalid_counties))}"
                    )
                
                # Check for disabled counties
                disabled_counties = set(node_counties) - enabled_counties
                disabled_counties = disabled_counties - invalid_counties  # Don't double-report invalid ones
                if disabled_counties:
                    warnings.append(
                        f"Node {node_number} monitors disabled counties: {', '.join(sorted(disabled_counties))}"
                    )
        
        return warnings

    def _normalize_paths(self, base_dir: Path) -> None:
        """
        Resolve relative filesystem paths so services started from other working
        directories (e.g., systemd) can still find bundled assets.
        """
        candidate_roots = []
        env_home = os.environ.get("SKYWARNPLUS_NG_HOME")
        if env_home:
            candidate_roots.append(Path(env_home))
        if base_dir:
            candidate_roots.append(base_dir.resolve())
            parent = base_dir.parent
            if parent and parent != base_dir:
                candidate_roots.append(parent.resolve())
        if getattr(self, "data_dir", None):
            candidate_roots.append(self.data_dir.resolve())
            data_parent = self.data_dir.parent
            if data_parent and data_parent != self.data_dir:
                candidate_roots.append(data_parent.resolve())
        candidate_roots.append(Path.cwd())

        def _resolve(path_value: Path) -> Path:
            if not path_value:
                return path_value
            if path_value.is_absolute():
                return path_value
            for root in candidate_roots:
                candidate = (root / path_value).resolve()
                if candidate.exists():
                    return candidate
            # Fall back to the first candidate even if it doesn't exist yet
            return (candidate_roots[0] / path_value).resolve() if candidate_roots else path_value

        try:
            resolved_sounds = _resolve(self.audio.sounds_path)
            if resolved_sounds != self.audio.sounds_path:
                logger.debug(f"Resolved audio.sounds_path to {resolved_sounds}")
                self.audio.sounds_path = resolved_sounds
        except Exception as exc:
            logger.warning(f"Failed to resolve sounds_path '{self.audio.sounds_path}': {exc}")

        try:
            resolved_temp = _resolve(self.audio.temp_dir)
            if resolved_temp != self.audio.temp_dir:
                logger.debug(f"Resolved audio.temp_dir to {resolved_temp}")
                self.audio.temp_dir = resolved_temp
        except Exception as exc:
            logger.warning(f"Failed to resolve temp_dir '{self.audio.temp_dir}': {exc}")
