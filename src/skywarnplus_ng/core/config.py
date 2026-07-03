"""
Configuration management for SkywarnPlus-NG.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from ruamel.yaml import YAML

logger = logging.getLogger(__name__)


def _empty_str_to_none(value: Any) -> Any:
    """Coerce blank form/YAML strings to None for optional fields."""
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def _empty_str_to_int(value: Any, default: int) -> int:
    """Coerce blank form/YAML strings to a default integer."""
    if value is None:
        return default
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return default
        return int(stripped)
    return int(value)


class ConfigError(Exception):
    """Raised when configuration cannot be loaded or is invalid."""

    pass


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
    audio_file: Optional[str] = Field(
        None, description="Audio file for county name (e.g., 'Galveston.wav')"
    )


class CourtesyToneConfig(BaseModel):
    """Courtesy tone configuration."""

    enabled: bool = Field(False, description="Enable automatic courtesy tone switching")
    tone_dir: Path = Field(
        Path("SOUNDS/TONES"), description="Directory where tone files are stored"
    )
    tones: Dict[str, Dict[str, str]] = Field(
        default_factory=dict,
        description="Mapping of CT keys to Normal/WX tone files (e.g., {'ct1': {'Normal': 'Boop.ulaw', 'WX': 'Stardust.ulaw'}})",
    )
    ct_alerts: List[str] = Field(
        default_factory=list,
        description="List of alert events that trigger WX mode (glob patterns supported)",
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
        description="List of alert events that trigger WX mode (glob patterns supported)",
    )


class NodeConfig(BaseModel):
    """Node configuration with optional per-node county monitoring."""

    number: int = Field(..., description="Node number")
    counties: Optional[List[str]] = Field(
        None,
        description="County codes this node monitors (e.g., ['TXC039', 'TXC201']). If null/empty, node monitors all enabled counties.",
    )
    gps_controlled: bool = Field(
        False,
        description="When true and gpsd has a valid fix, this node monitors only the GPS-resolved county.",
    )
    gps_only: bool = Field(
        False,
        description="When true (requires gps_controlled), use GPS county only; no static fallback when GPS is inactive. "
        "Also implied when gps_controlled is true and counties is empty or omitted.",
    )


class GpsdConfig(BaseModel):
    """gpsd integration for mobile county monitoring."""

    enabled: bool = Field(False, description="Enable gpsd-based mobile county detection")
    host: str = Field("127.0.0.1", description="gpsd host")
    port: int = Field(2947, description="gpsd JSON port")
    stale_seconds: int = Field(
        900,
        ge=60,
        description="Revert to static counties when no fresh fix within this many seconds",
    )
    min_accuracy_meters: Optional[float] = Field(
        2000,
        description="Reject fixes with horizontal error above this value (null disables)",
    )
    hysteresis_polls: int = Field(
        3,
        ge=1,
        description="Consecutive polls required before switching GPS county",
    )
    connect_timeout_seconds: int = Field(5, ge=1, description="Timeout connecting to gpsd")

    @field_validator("min_accuracy_meters", mode="before")
    @classmethod
    def _coerce_min_accuracy(cls, value: Any) -> Any:
        return _empty_str_to_none(value)


class AsteriskConfig(BaseModel):
    """Asterisk configuration."""

    enabled: bool = Field(True, description="Enable Asterisk integration")
    nodes: List[int | NodeConfig] = Field(
        default_factory=list,
        description="Target node numbers or node configurations with per-node counties",
    )
    audio_delay: int = Field(0, description="Audio delay in milliseconds")
    playback_mode: str = Field(
        "local", description="Playback mode: 'local' (default) or 'global' for rpt playback"
    )
    courtesy_tones: CourtesyToneConfig = Field(
        default_factory=CourtesyToneConfig, description="Courtesy tone configuration"
    )
    id_change: IDChangeConfig = Field(
        default_factory=IDChangeConfig, description="ID change configuration"
    )

    def get_nodes_list(self) -> List[int]:
        """Get list of all node numbers regardless of format."""
        result = []
        for node in self.nodes:
            if isinstance(node, int):
                result.append(node)
            elif isinstance(node, NodeConfig):
                result.append(node.number)
            elif isinstance(node, dict):
                result.append(node.get("number", node.get("node", 0)))
        return result

    def get_node_config(self, node_number: int) -> Optional[NodeConfig]:
        """Get configuration for a specific node."""
        for node in self.nodes:
            if isinstance(node, NodeConfig) and node.number == node_number:
                return node
            elif isinstance(node, dict) and node.get("number") == node_number:
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

    engine: str = Field(
        "asl-tts",
        description="TTS engine: 'asl-tts' (ASL3 Piper CLI, default) or 'gtts' (cloud)",
    )
    language: str = Field("en", description="Language code (for gTTS)")
    tld: str = Field("com", description="Top-level domain for gTTS")
    slow: bool = Field(False, description="Slow down speech (for gTTS)")
    # asl-tts settings (asl3-tts package; voices in /var/lib/piper-tts)
    voice: Optional[str] = Field(
        "en_US-amy-low.onnx",
        description="Piper voice filename for asl-tts -v (e.g. en_US-amy-low.onnx)",
    )
    voices_dir: str = Field(
        "/var/lib/piper-tts",
        description="Directory containing Piper .onnx voice models (ASL3 convention)",
    )
    asl_tts_binary: str = Field("asl-tts", description="Path or name of the asl-tts CLI binary")
    node_number: Optional[int] = Field(
        None,
        description="AllStar node number passed to asl-tts -n (defaults to first configured node or 1)",
    )
    model_path: Optional[str] = Field(
        None,
        description="Legacy Piper path; migrated to voice filename when engine was piper",
    )
    speed: float = Field(
        1.0,
        description="Deprecated (embedded Piper only); ignored for asl-tts",
    )
    output_format: str = Field("ulaw", description="Output audio format")
    sample_rate: int = Field(8000, description="Sample rate in Hz")
    bit_rate: int = Field(128, description="Bit rate in kbps")

    @field_validator("engine", mode="before")
    @classmethod
    def normalize_engine(cls, value: Any) -> str:
        if not isinstance(value, str):
            return value
        normalized = value.strip().lower().replace("_", "-")
        if normalized == "piper":
            return "asl-tts"
        if normalized == "asltts":
            return "asl-tts"
        return normalized

    @field_validator("voice", mode="before")
    @classmethod
    def normalize_voice(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    def model_post_init(self, __context: Any) -> None:
        if not self.voice and self.model_path:
            object.__setattr__(self, "voice", Path(str(self.model_path)).name)
        if not self.voice:
            object.__setattr__(self, "voice", "en_US-amy-low.onnx")


class AudioConfig(BaseModel):
    """Audio configuration."""

    sounds_path: Path = Field(Path("SOUNDS"), description="Path to sounds directory")
    alert_sound: str = Field("Duncecap.wav", description="Alert sound file")
    all_clear_sound: str = Field("Triangles.wav", description="All clear sound file")
    separator_sound: str = Field("Woodblock.wav", description="Alert separator sound")
    tts: TTSConfig = Field(default_factory=TTSConfig, description="TTS configuration")
    temp_dir: Path = Field(
        Path("/tmp/skywarnplus-ng-audio"), description="Temporary audio directory"
    )


class FilteringConfig(BaseModel):
    """Alert filtering configuration."""

    max_alerts: int = Field(99, description="Maximum number of alerts to process")
    blocked_events: List[str] = Field(default_factory=list, description="Globally blocked events")
    say_alert_blocked: List[str] = Field(
        default_factory=list, description="Events blocked from voice announcement"
    )
    tail_message_blocked: List[str] = Field(
        default_factory=list, description="Events blocked from tail message"
    )


class QuietHoursConfig(BaseModel):
    """Suppress voice announcements during local quiet hours."""

    enabled: bool = Field(False, description="Enable quiet hours voice suppression")
    start: str = Field("01:00", description="Local start time (HH:MM)")
    end: str = Field("06:00", description="Local end time (HH:MM)")
    timezone: Optional[str] = Field(
        None,
        description="IANA timezone (defaults to system local timezone)",
    )
    allow_severe: bool = Field(
        True,
        description="Still announce Severe/Extreme severity alerts during quiet hours",
    )

    @field_validator("timezone", mode="before")
    @classmethod
    def _coerce_timezone(cls, value: Any) -> Any:
        return _empty_str_to_none(value)


class AlertConfig(BaseModel):
    """Alert behavior configuration."""

    say_alert: bool = Field(True, description="Enable voice announcements")
    say_all_clear: bool = Field(True, description="Enable all-clear announcements")
    tail_message: bool = Field(True, description="Enable tail messages")
    tail_message_path: Optional[Path] = Field(
        None,
        description="Path for tail message file (default: /var/lib/skywarnplus-ng/data/wx-tail.wav)",
    )
    tail_message_suffix: Optional[str] = Field(
        None, description="Optional suffix audio file to append to tail message"
    )
    tail_message_counties: bool = Field(False, description="Include county names in tail message")
    with_county_names: bool = Field(False, description="Include county names in announcements")
    time_type: str = Field("onset", description="Time type: 'onset' or 'effective'")
    say_alert_suffix: Optional[str] = Field(
        None, description="Optional suffix audio file to append to alert announcements"
    )
    say_all_clear_suffix: Optional[str] = Field(
        None, description="Optional suffix audio file to append to all-clear announcements"
    )
    say_alerts_changed: bool = Field(True, description="Announce alerts when county list changes")
    say_alert_all: bool = Field(
        False, description="Say all alerts when one changes (requires SayAlertsChanged)"
    )
    with_multiples: bool = Field(
        False, description="Tag alerts with 'with multiples' if multiple instances exist"
    )
    quiet_hours: QuietHoursConfig = Field(
        default_factory=QuietHoursConfig, description="Quiet hours playback policy"
    )
    announcement_hold_minutes: int = Field(
        0,
        ge=0,
        le=240,
        description="Suppress re-announcing the same event+counties within this many minutes (0=off)",
    )


def _migrate_legacy_geo_hazard_position(yaml_data: dict) -> None:
    """Move per-hazard position settings into geo_hazard_position (backward compat)."""
    ghp = yaml_data.get("geo_hazard_position")
    if ghp is None:
        ghp = {}
        yaml_data["geo_hazard_position"] = ghp
    elif not isinstance(ghp, dict):
        return

    def _is_empty(val: Any) -> bool:
        return val is None or (isinstance(val, str) and val.strip() == "")

    for section_key in ("nhc", "earthquake", "wildfire"):
        section = yaml_data.get(section_key)
        if not isinstance(section, dict):
            continue
        for field in ("use_gps_position", "static_lat", "static_lon"):
            legacy = section.pop(field, None)
            if _is_empty(legacy):
                continue
            if field == "use_gps_position":
                if "use_gps_position" not in ghp:
                    ghp["use_gps_position"] = legacy
            elif _is_empty(ghp.get(field)):
                ghp[field] = legacy


class GeoHazardPositionConfig(BaseModel):
    """Shared monitoring position for geo hazards (NHC, USGS, wildfire)."""

    use_gps_position: bool = Field(
        True,
        description="Use gpsd position when available; otherwise static_lat/static_lon",
    )
    static_lat: Optional[float] = Field(
        None, description="Fallback latitude when GPS is slow or unavailable"
    )
    static_lon: Optional[float] = Field(
        None, description="Fallback longitude when GPS is slow or unavailable"
    )

    @field_validator("static_lat", "static_lon", mode="before")
    @classmethod
    def _coerce_static_coords(cls, value: Any) -> Any:
        return _empty_str_to_none(value)


class NhcConfig(BaseModel):
    """National Hurricane Center tropical cyclone monitoring."""

    enabled: bool = Field(False, description="Enable NHC tropical cyclone voice advisories")
    feed_path: str = Field(
        "/gis-at.xml",
        description="NHC GIS RSS path (e.g. /gis-at.xml Atlantic, /gis-ep.xml East Pacific, /gis-cp.xml Central Pacific)",
    )
    poll_interval_minutes: int = Field(
        60,
        ge=5,
        le=360,
        description="Minimum minutes between NHC feed fetches",
    )
    max_distance_miles: int = Field(
        1000,
        ge=50,
        le=5000,
        description="Only announce storms within this distance of your position",
    )
    max_advisory_age_hours: int = Field(
        4,
        ge=1,
        le=48,
        description="Ignore advisories older than this",
    )
    hurricanes_only: bool = Field(
        False,
        description="Only announce hurricanes (skip tropical storms/depressions)",
    )
    max_announcements_per_cycle: int = Field(
        3,
        ge=1,
        le=20,
        description="Maximum cyclone voice announcements per poll cycle",
    )


class EarthquakeConfig(BaseModel):
    """USGS earthquake monitoring near a monitoring position."""

    enabled: bool = Field(False, description="Enable USGS earthquake monitoring")
    announce_enabled: bool = Field(
        True,
        description="Voice announcements on repeater for new earthquakes (requires enabled)",
    )
    poll_interval_minutes: int = Field(
        10,
        ge=1,
        le=360,
        description="Minimum minutes between USGS earthquake fetches",
    )
    min_magnitude: float = Field(
        3.5,
        ge=0.0,
        le=10.0,
        description="Minimum earthquake magnitude to announce",
    )
    max_distance_miles: int = Field(
        75,
        ge=1,
        le=5000,
        description="Only announce earthquakes within this distance",
    )
    lookback_hours: int = Field(
        24,
        ge=1,
        le=168,
        description="How far back to query USGS for recent events",
    )
    max_event_age_hours: int = Field(
        6,
        ge=1,
        le=168,
        description="Only announce earthquakes newer than this many hours",
    )
    announce_history_on_enable: bool = Field(
        False,
        description="When false, mark existing feed events as announced without voice on first enable",
    )
    max_announcements_per_cycle: int = Field(
        3,
        ge=1,
        le=20,
        description="Maximum earthquake voice announcements per poll cycle",
    )
    ignore_automatic_below: Optional[float] = Field(
        None,
        ge=0.0,
        le=10.0,
        description="Skip automatic-status events below this magnitude (null=announce all)",
    )

    @field_validator("ignore_automatic_below", mode="before")
    @classmethod
    def _coerce_earthquake_optional_fields(cls, value: Any) -> Any:
        return _empty_str_to_none(value)


class WildfireConfig(BaseModel):
    """NIFC WFIGS wildfire incident monitoring near a monitoring position."""

    enabled: bool = Field(False, description="Enable wildfire incident monitoring")
    announce_enabled: bool = Field(
        True,
        description="Voice announcements on repeater for new wildfires (requires enabled)",
    )
    poll_interval_minutes: int = Field(
        15,
        ge=5,
        le=360,
        description="Minimum minutes between WFIGS wildfire fetches",
    )
    max_distance_miles: int = Field(
        50,
        ge=1,
        le=5000,
        description="Only announce wildfires within this distance",
    )
    min_acres: float = Field(
        250,
        ge=0,
        description="Minimum fire size in acres to announce",
    )
    exclude_prescribed: bool = Field(
        True,
        description="Skip prescribed burns",
    )
    max_discovery_age_hours: int = Field(
        48,
        ge=1,
        le=720,
        description="Only announce fires discovered within this many hours",
    )
    announce_history_on_enable: bool = Field(
        False,
        description="When false, mark existing feed incidents as announced without voice on first enable",
    )
    max_announcements_per_cycle: int = Field(
        3,
        ge=1,
        le=20,
        description="Maximum wildfire voice announcements per poll cycle",
    )


class TsunamiConfig(BaseModel):
    """NWS tsunami alert monitoring at the geo-hazard position."""

    enabled: bool = Field(False, description="Enable NWS tsunami alert monitoring")
    announce_enabled: bool = Field(
        True,
        description="Voice announcements on repeater for new tsunami alerts (requires enabled)",
    )
    poll_interval_minutes: int = Field(
        2,
        ge=1,
        le=60,
        description="Minimum minutes between NWS tsunami fetches",
    )
    min_level: str = Field(
        "warning",
        description="Minimum tsunami level to announce: warning, advisory, or watch",
    )

    @field_validator("min_level")
    @classmethod
    def validate_min_level(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        allowed = {"watch", "advisory", "warning", "statement"}
        if normalized not in allowed:
            raise ValueError(f"min_level must be one of: {', '.join(sorted(allowed))}")
        return normalized

    announce_history_on_enable: bool = Field(
        False,
        description="When false, mark existing feed alerts as announced without voice on first enable",
    )
    max_announcements_per_cycle: int = Field(
        2,
        ge=1,
        le=20,
        description="Maximum tsunami voice announcements per poll cycle",
    )


class SpaceWeatherConfig(BaseModel):
    """NOAA SWPC space weather alert monitoring (global, not position-based)."""

    enabled: bool = Field(False, description="Enable SWPC space weather monitoring")
    announce_enabled: bool = Field(
        True,
        description="Voice announcements on repeater for new space weather alerts (requires enabled)",
    )
    poll_interval_minutes: int = Field(
        5,
        ge=1,
        le=60,
        description="Minimum minutes between SWPC alert fetches",
    )
    min_geomagnetic_scale: int = Field(
        0,
        ge=0,
        le=5,
        description="Minimum G-scale (0=any, 1=G1+, etc.)",
    )
    min_radio_blackout_scale: int = Field(
        0,
        ge=0,
        le=5,
        description="Minimum R-scale (0=any, 1=R1+, etc.)",
    )
    min_solar_radiation_scale: int = Field(
        0,
        ge=0,
        le=5,
        description="Minimum S-scale (0=any, 1=S1+, etc.)",
    )
    announce_watches: bool = Field(True, description="Announce SWPC watches")
    announce_warnings: bool = Field(True, description="Announce SWPC warnings")
    announce_alerts: bool = Field(True, description="Announce SWPC alerts")
    announce_summaries: bool = Field(False, description="Announce SWPC summary products")
    announce_history_on_enable: bool = Field(
        False,
        description="When false, mark existing feed alerts as announced without voice on first enable",
    )
    max_announcements_per_cycle: int = Field(
        2,
        ge=1,
        le=20,
        description="Maximum space weather voice announcements per poll cycle",
    )


class VolcanoConfig(BaseModel):
    """USGS volcano notice (VONA) monitoring near the geo-hazard position."""

    enabled: bool = Field(False, description="Enable USGS volcano notice monitoring")
    announce_enabled: bool = Field(
        True,
        description="Voice announcements on repeater for new volcano notices (requires enabled)",
    )
    poll_interval_minutes: int = Field(
        15,
        ge=5,
        le=360,
        description="Minimum minutes between USGS volcano fetches",
    )
    max_distance_miles: int = Field(
        150,
        ge=1,
        le=5000,
        description="Only announce volcano notices within this distance",
    )
    min_color_code: str = Field(
        "orange",
        description="Minimum aviation color code: green, yellow, orange, or red",
    )

    @field_validator("min_color_code")
    @classmethod
    def validate_min_color_code(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        allowed = {"green", "yellow", "orange", "red", "unassigned"}
        if normalized not in allowed:
            raise ValueError(f"min_color_code must be one of: {', '.join(sorted(allowed))}")
        return normalized

    observatories: List[str] = Field(
        default_factory=list,
        description="Optional observatory filter (empty = all); USGS codes: AVO, CALVO, CVO, HVO, NMI, YVO",
    )
    lookback_days: int = Field(
        7,
        ge=1,
        le=30,
        description="Days of VONA history to fetch from USGS",
    )
    announce_history_on_enable: bool = Field(
        False,
        description="When false, mark existing feed notices as announced without voice on first enable",
    )
    max_announcements_per_cycle: int = Field(
        2,
        ge=1,
        le=20,
        description="Maximum volcano voice announcements per poll cycle",
    )


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
    triggers: List[str] = Field(
        default_factory=list, description="Alert event patterns that trigger this mapping"
    )
    match: str = Field("ANY", description="Match type: ANY (default) or ALL")
    nodes: List[int] = Field(default_factory=list, description="Node numbers for DTMF commands")
    clear_commands: Optional[List[str]] = Field(
        None, description="Commands to execute when alerts clear"
    )


class ScriptsConfig(BaseModel):
    """Scripts configuration."""

    enabled: bool = Field(True, description="Enable script execution")
    alert_scripts: Dict[str, ScriptConfig] = Field(
        default_factory=dict, description="Scripts for specific alert types"
    )
    all_clear_script: Optional[ScriptConfig] = Field(
        None, description="Script for all-clear events"
    )
    default_timeout: int = Field(30, description="Default script timeout in seconds")
    # Enhanced AlertScript configuration (mapping-based)
    alertscript_enabled: bool = Field(
        False, description="Enable enhanced AlertScript (mapping-based)"
    )
    alertscript_mappings: List[AlertScriptMappingConfig] = Field(
        default_factory=list, description="AlertScript mappings (alert patterns to commands)"
    )
    alertscript_active_commands: Optional[List[AlertScriptMappingConfig]] = Field(
        None, description="Commands to execute when alerts go from 0 to non-zero"
    )
    alertscript_inactive_commands: Optional[List[AlertScriptMappingConfig]] = Field(
        None, description="Commands to execute when alerts go from non-zero to 0"
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
    secret_key: Optional[str] = Field(
        None, description="Secret key for session encryption (auto-generated if not set)"
    )
    secure_cookies: bool = Field(
        False,
        description="Set Secure on session cookies (enable when dashboard is only served over HTTPS)",
    )
    cookie_secure_auto: bool = Field(
        True,
        description="When secure_cookies is false, add Secure if X-Forwarded-Proto is https",
    )
    public_status_api: bool = Field(
        True,
        description="Allow unauthenticated GET /api/status (supermon-ng); other public dashboard reads are always open",
    )


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


class UpdateCheckConfig(BaseModel):
    """Advisory check for newer releases on GitHub (no auto-update)."""

    enabled: bool = Field(
        True,
        description="If true, periodically check GitHub releases and show an in-dashboard notice when a newer version exists (set false to opt out)",
    )
    interval_hours: int = Field(
        24,
        ge=1,
        le=168,
        description="Minimum hours between checks (cached; avoids hammering the GitHub API)",
    )
    github_repo: str = Field(
        "hardenedpenguin/SkywarnPlus-NG",
        description="GitHub owner/repo for https://api.github.com/repos/{owner}/{repo}/releases/latest",
    )


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
    update_check: UpdateCheckConfig = Field(default_factory=UpdateCheckConfig)


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
    descriptions_dir: Path = Field(
        Path("/var/lib/skywarnplus-ng/descriptions"),
        description="Directory for description audio files",
    )
    cleanup_interval_hours: int = Field(24, description="Cleanup interval for old audio files")
    max_file_age_hours: int = Field(48, description="Maximum age of audio files before cleanup")
    dtmf_codes: DTMFConfig = Field(default_factory=DTMFConfig)
    max_words: int = Field(150, description="Maximum words in description")


class NotificationEmailConfig(BaseModel):
    """SMTP email notification settings (Notifications tab)."""

    provider: str = Field(
        "gmail", description="Email provider preset (gmail, outlook, custom, etc.)"
    )
    smtp_server: str = Field("", description="SMTP server hostname")
    smtp_port: int = Field(587, description="SMTP port")
    use_tls: bool = Field(True, description="Use STARTTLS")
    use_ssl: bool = Field(False, description="Use SSL/TLS from connect")
    username: str = Field("", description="SMTP username / from address")
    password: Optional[str] = Field(None, description="SMTP password or app password")
    from_name: str = Field("SkywarnPlus-NG", description="Display name for From header")

    @field_validator("smtp_port", mode="before")
    @classmethod
    def _coerce_smtp_port(cls, value: Any) -> int:
        return _empty_str_to_int(value, 587)

    @field_validator("password", mode="before")
    @classmethod
    def _coerce_password(cls, value: Any) -> Any:
        return _empty_str_to_none(value)


class NotificationWebhookConfig(BaseModel):
    """Global webhook URLs (Slack, Teams, generic)."""

    slack_url: Optional[str] = Field(None, description="Slack incoming webhook URL")
    teams_url: Optional[str] = Field(None, description="Microsoft Teams webhook URL")
    generic_url: Optional[str] = Field(None, description="Generic HTTPS webhook URL")

    @field_validator("slack_url", "teams_url", "generic_url", mode="before")
    @classmethod
    def _coerce_webhook_urls(cls, value: Any) -> Any:
        return _empty_str_to_none(value)


class NotificationPushConfig(BaseModel):
    """FCM push notification settings."""

    fcm_server_key: Optional[str] = Field(None, description="Firebase Cloud Messaging server key")
    fcm_project_id: Optional[str] = Field(None, description="Firebase project ID")

    @field_validator("fcm_server_key", "fcm_project_id", mode="before")
    @classmethod
    def _coerce_push_fields(cls, value: Any) -> Any:
        return _empty_str_to_none(value)


class NotificationSmsConfig(BaseModel):
    """Twilio SMS settings for subscriber text alerts."""

    enabled: bool = Field(False, description="Enable subscriber SMS via Twilio")
    account_sid: Optional[str] = Field(None, description="Twilio Account SID")
    auth_token: Optional[str] = Field(None, description="Twilio Auth Token")
    from_number: Optional[str] = Field(
        None, description="Twilio sender phone number (E.164, e.g. +15551234567)"
    )
    max_length: int = Field(160, description="Maximum SMS body length")
    all_clear_enabled: bool = Field(False, description="Send SMS on all-clear events")

    @field_validator("account_sid", "auth_token", "from_number", mode="before")
    @classmethod
    def _coerce_sms_optional_strings(cls, value: Any) -> Any:
        return _empty_str_to_none(value)

    @field_validator("max_length", mode="before")
    @classmethod
    def _coerce_sms_max_length(cls, value: Any) -> int:
        return _empty_str_to_int(value, 160)


class NotificationDeliveryConfig(BaseModel):
    """Delivery queue tuning."""

    max_concurrent: int = Field(10, description="Max concurrent outbound deliveries")
    timeout_seconds: int = Field(30, description="Per-delivery timeout in seconds")
    max_retries: int = Field(3, description="Max retry attempts for failed deliveries")
    retry_delay: int = Field(5, description="Initial retry delay in seconds")

    @field_validator(
        "max_concurrent", "timeout_seconds", "max_retries", "retry_delay", mode="before"
    )
    @classmethod
    def _coerce_delivery_ints(cls, value: Any, info) -> int:
        defaults = {
            "max_concurrent": 10,
            "timeout_seconds": 30,
            "max_retries": 3,
            "retry_delay": 5,
        }
        return _empty_str_to_int(value, defaults.get(info.field_name, 0))


class NotificationsConfig(BaseModel):
    """Dashboard Notifications tab settings."""

    email: NotificationEmailConfig = Field(default_factory=NotificationEmailConfig)
    webhook: NotificationWebhookConfig = Field(default_factory=NotificationWebhookConfig)
    push: NotificationPushConfig = Field(default_factory=NotificationPushConfig)
    sms: NotificationSmsConfig = Field(default_factory=NotificationSmsConfig)
    delivery: NotificationDeliveryConfig = Field(default_factory=NotificationDeliveryConfig)


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
    inject_alerts: List[Dict[str, Any]] = Field(
        default_factory=list, description="List of test alerts to inject"
    )
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
    dashboard_setup_complete: bool = Field(
        False,
        description="Set true after initial configuration is saved from the dashboard",
    )

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
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    dev: DevConfig = Field(default_factory=DevConfig)
    gpsd: GpsdConfig = Field(default_factory=GpsdConfig)
    geo_hazard_position: GeoHazardPositionConfig = Field(
        default_factory=GeoHazardPositionConfig,
        description="Shared gpsd/static position for NHC, USGS, wildfire, tsunami, and volcano monitoring",
    )
    nhc: NhcConfig = Field(default_factory=NhcConfig)
    earthquake: EarthquakeConfig = Field(default_factory=EarthquakeConfig)
    wildfire: WildfireConfig = Field(default_factory=WildfireConfig)
    tsunami: TsunamiConfig = Field(default_factory=TsunamiConfig)
    space_weather: SpaceWeatherConfig = Field(default_factory=SpaceWeatherConfig)
    volcano: VolcanoConfig = Field(default_factory=VolcanoConfig)

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_geo_position(cls, data: Any) -> Any:
        if isinstance(data, dict):
            _migrate_legacy_geo_hazard_position(data)
        return data

    @classmethod
    def from_yaml(cls, config_path=None) -> "AppConfig":
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

        try:
            yaml = YAML(typ="safe")
            with open(config_path, "r") as f:
                yaml_data = yaml.load(f)
        except OSError as e:
            raise ConfigError(f"Cannot read config file {config_path}: {e}") from e
        except Exception as e:
            raise ConfigError(f"Invalid YAML in {config_path}: {e}") from e

        if not isinstance(yaml_data, dict):
            raise ConfigError(
                f"Config file {config_path} must contain a YAML mapping (dict), got {type(yaml_data).__name__}"
            )

        try:
            config = cls(**yaml_data)
        except Exception as e:
            raise ConfigError(f"Invalid configuration in {config_path}: {e}") from e

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
                node_number = node.get("number", 0)
                node_counties = node.get("counties")
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
            elif isinstance(node, dict) and not node.get("counties"):
                monitors_all = True
                break

        if monitors_all:
            # At least one node monitors all counties, return all enabled counties
            return [c.code for c in self.counties if c.enabled]

        # Otherwise, collect specific counties from node configurations
        for node in self.asterisk.nodes:
            if isinstance(node, NodeConfig) and node.counties:
                monitored.update(node.counties)
            elif isinstance(node, dict) and node.get("counties"):
                monitored.update(node.get("counties"))

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
        gps_controlled_nodes: List[int] = []
        for node in self.asterisk.nodes:
            node_number = None
            node_counties = None
            gps_controlled = False
            gps_only = False

            if isinstance(node, NodeConfig):
                node_number = node.number
                node_counties = node.counties
                gps_controlled = node.gps_controlled
                gps_only = node.gps_only
            elif isinstance(node, dict):
                node_number = node.get("number", "unknown")
                node_counties = node.get("counties")
                gps_controlled = bool(node.get("gps_controlled", False))
                gps_only = bool(node.get("gps_only", False))

            if gps_only and not gps_controlled:
                warnings.append(f"Node {node_number} has gps_only set but is not gps_controlled")
            if gps_only and node_counties:
                warnings.append(
                    f"Node {node_number} has gps_only set; static counties are ignored for fallback"
                )

            if gps_controlled and isinstance(node_number, int):
                gps_controlled_nodes.append(node_number)

            if node_counties:
                # Check for invalid county codes
                invalid_counties = set(node_counties) - {c.code for c in self.counties}
                if invalid_counties:
                    warnings.append(
                        f"Node {node_number} references invalid county codes: {', '.join(sorted(invalid_counties))}"
                    )

                # Check for disabled counties
                disabled_counties = set(node_counties) - enabled_counties
                disabled_counties = (
                    disabled_counties - invalid_counties
                )  # Don't double-report invalid ones
                if disabled_counties:
                    warnings.append(
                        f"Node {node_number} monitors disabled counties: {', '.join(sorted(disabled_counties))}"
                    )

        if len(gps_controlled_nodes) > 1:
            warnings.append(
                "Multiple nodes are marked gps_controlled; only one GPS-controlled node is supported: "
                + ", ".join(str(n) for n in sorted(gps_controlled_nodes))
            )
        if self.gpsd.enabled and not gps_controlled_nodes:
            warnings.append("gpsd is enabled but no node is marked gps_controlled")
        if gps_controlled_nodes and not self.gpsd.enabled:
            warnings.append(
                f"Node(s) {', '.join(str(n) for n in sorted(gps_controlled_nodes))} "
                "are gps_controlled but gpsd.enabled is false"
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

        try:
            ct_dir = getattr(self.asterisk.courtesy_tones, "tone_dir", None)
            if ct_dir:
                resolved_ct = _resolve(Path(ct_dir))
                self.asterisk.courtesy_tones.tone_dir = str(resolved_ct)
        except Exception as exc:
            logger.debug("Could not resolve courtesy tone directory: %s", exc)

        try:
            id_dir = getattr(self.asterisk.id_change, "id_dir", None)
            if id_dir:
                resolved_id = _resolve(Path(id_dir))
                self.asterisk.id_change.id_dir = str(resolved_id)
        except Exception as exc:
            logger.debug("Could not resolve ID change directory: %s", exc)

        try:
            nodes = self.get_nodes_list()
            if self.audio.tts.node_number is None:
                self.audio.tts.node_number = nodes[0] if nodes else 1
        except Exception as exc:
            logger.debug("Could not resolve default TTS node number: %s", exc)
