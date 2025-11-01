#!/usr/bin/env python3
"""
SkyControl CLI for SkywarnPlus-NG

A command-line script to control SkywarnPlus-NG features without editing config.yaml.
Provides spoken feedback when commands execute.

Usage: skycontrol <command> [value]
Examples:
  skycontrol enable true
  skycontrol sayalert toggle
  skycontrol changect normal
  skycontrol changeid wx
"""

import sys
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from pydub import AudioSegment

from ..core.config import AppConfig
from ..asterisk.manager import AsteriskManager

# Setup logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


# Define valid commands and their configuration paths
VALID_COMMANDS: Dict[str, Dict[str, Any]] = {
    "enable": {
        "config_path": "enabled",
        "true_file": "SWP_137.wav",
        "false_file": "SWP_138.wav",
        "description": "Enable/disable entire SkywarnPlus",
    },
    "sayalert": {
        "config_path": "alerts.say_alert",
        "true_file": "SWP_139.wav",
        "false_file": "SWP_140.wav",
        "description": "Toggle alert announcements",
    },
    "sayallclear": {
        "config_path": "alerts.say_all_clear",
        "true_file": "SWP_141.wav",
        "false_file": "SWP_142.wav",
        "description": "Toggle all-clear announcements",
    },
    "tailmessage": {
        "config_path": "alerts.tail_message",
        "true_file": "SWP_143.wav",
        "false_file": "SWP_144.wav",
        "description": "Toggle tail messages",
    },
    "courtesytone": {
        "config_path": "asterisk.courtesy_tones.enabled",
        "true_file": "SWP_145.wav",
        "false_file": "SWP_146.wav",
        "description": "Toggle courtesy tone changes",
    },
    "idchange": {
        "config_path": "asterisk.id_change.enabled",
        "true_file": "SWP_135.wav",
        "false_file": "SWP_136.wav",
        "description": "Toggle ID changes",
    },
    "alertscript": {
        "config_path": "scripts.enabled",
        "true_file": "SWP_133.wav",
        "false_file": "SWP_134.wav",
        "description": "Toggle AlertScript execution",
    },
    "changect": {
        "config_path": None,  # Special command, not a config toggle
        "true_file": "SWP_131.wav",
        "false_file": "SWP_132.wav",
        "available_values": ["wx", "normal"],
        "description": "Force CT mode (normal or wx)",
    },
    "changeid": {
        "config_path": None,  # Special command, not a config toggle
        "true_file": "SWP_129.wav",
        "false_file": "SWP_130.wav",
        "available_values": ["wx", "normal"],
        "description": "Force ID mode (normal or wx)",
    },
}


def get_config_file(config: AppConfig) -> Path:
    """Get the path to the config file."""
    config_path = config.config_file
    if not config_path.is_absolute():
        config_path = Path("/etc/skywarnplus-ng") / config_path
    return config_path


def load_config(config_path: Path) -> Dict[str, Any]:
    """Load config file using ruamel.yaml to preserve comments."""
    from ruamel.yaml import YAML
    
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, "r") as f:
        return yaml.load(f)


def save_config(config_path: Path, config_data: Dict[str, Any]) -> None:
    """Save config file using ruamel.yaml to preserve comments."""
    from ruamel.yaml import YAML
    
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.default_flow_style = False
    
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)


def set_nested_value(config_data: Dict[str, Any], path: str, value: Any) -> None:
    """Set a nested value in config using dot notation path."""
    keys = path.split(".")
    current = config_data
    
    # Navigate to the parent dict
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    
    # Set the final value
    current[keys[-1]] = value


def get_nested_value(config_data: Dict[str, Any], path: str) -> Any:
    """Get a nested value from config using dot notation path."""
    keys = path.split(".")
    current = config_data
    
    for key in keys:
        if key not in current:
            return None
        current = current[key]
    
    return current


def play_audio_feedback(
    audio_file: str,
    nodes: list,
    sounds_path: Path,
    asterisk_manager: Optional[AsteriskManager] = None
) -> None:
    """
    Play audio feedback on configured nodes.
    
    Args:
        audio_file: Name of the audio file (e.g., "SWP_137.wav")
        nodes: List of node numbers
        sounds_path: Path to sounds directory
        asterisk_manager: Optional AsteriskManager instance
    """
    if not nodes:
        logger.warning("No nodes configured, cannot play audio feedback")
        return
    
    audio_path = sounds_path / "ALERTS" / audio_file
    
    if not audio_path.exists():
        logger.warning(f"Audio file not found: {audio_path}")
        return
    
    # Remove extension for Asterisk playback
    playback_path = str(audio_path).rsplit('.', 1)[0] if '.' in audio_path.name else str(audio_path)
    
    for node in nodes:
        try:
            # Use direct Asterisk CLI command (simpler for CLI tool)
            subprocess.run(
                [
                    "sudo", "-n", "-u", "asterisk",
                    "/usr/sbin/asterisk", "-rx",
                    f"rpt playback {node} {playback_path}"
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            logger.error(f"Failed to play audio on node {node}: {e}")


def create_silent_tailmessage(tailmessage_path: Path) -> None:
    """
    Create a silent tail message file (100ms silence).
    
    Args:
        tailmessage_path: Path where tail message file should be created
    """
    try:
        tailmessage_path.parent.mkdir(parents=True, exist_ok=True)
        silence = AudioSegment.silent(duration=100)
        converted_silence = silence.set_frame_rate(8000).set_channels(1)
        converted_silence.export(str(tailmessage_path), format="wav")
        logger.info(f"Created silent tail message at {tailmessage_path}")
    except Exception as e:
        logger.error(f"Failed to create silent tail message: {e}")


def handle_changect(config_data: Dict[str, Any], mode: str) -> bool:
    """
    Handle changect command - force CT mode.
    
    Args:
        config_data: Configuration dictionary
        mode: Mode to change to ('normal' or 'wx')
        
    Returns:
        True if changed to wx mode, False if changed to normal mode
    """
    mode = mode.lower()
    if mode not in ["normal", "wx"]:
        print(f"Invalid CT mode: {mode}. Must be 'normal' or 'wx'.")
        sys.exit(1)
    
    # Import managers
    from ..core.config import AppConfig
    from ..asterisk.courtesy_tone import CourtesyToneManager
    from ..core.state import ApplicationState
    
    try:
        # Create a temporary config for CT manager
        app_config = AppConfig(**config_data)
        
        if not app_config.asterisk.courtesy_tones.enabled:
            print("Courtesy tones are not enabled in configuration.")
            sys.exit(1)
        
        # Create state manager
        state_manager = ApplicationState(
            state_file=app_config.data_dir / "state.json"
        )
        
        # Create CT manager
        ct_manager = CourtesyToneManager(
            enabled=True,
            tone_dir=app_config.asterisk.courtesy_tones.tone_dir,
            tones_config=app_config.asterisk.courtesy_tones.tones,
            ct_alerts=app_config.asterisk.courtesy_tones.ct_alerts,
            state_manager=state_manager
        )
        
        # Force the mode
        changed = ct_manager.force_mode(mode)
        if changed:
            print(f"Courtesy tones changed to {mode} mode.")
            return mode == "wx"
        else:
            print(f"Courtesy tones already in {mode} mode.")
            return mode == "wx"
            
    except Exception as e:
        logger.error(f"Failed to change CT mode: {e}")
        print(f"Error: {e}")
        sys.exit(1)


def handle_changeid(config_data: Dict[str, Any], mode: str) -> bool:
    """
    Handle changeid command - force ID mode.
    
    Args:
        config_data: Configuration dictionary
        mode: Mode to change to ('normal' or 'wx')
        sounds_path: Path to sounds directory
        
    Returns:
        True if changed to wx mode, False if changed to normal mode
    """
    mode = mode.upper()  # IDChangeManager expects 'NORMAL' or 'WX'
    if mode not in ["NORMAL", "WX"]:
        mode_lower = mode.lower()
        if mode_lower == "normal":
            mode = "NORMAL"
        elif mode_lower == "wx":
            mode = "WX"
        else:
            print(f"Invalid ID mode: {mode}. Must be 'normal' or 'wx'.")
            sys.exit(1)
    
    # Import managers
    from ..core.config import AppConfig
    from ..asterisk.id_change import IDChangeManager
    from ..core.state import ApplicationState
    
    try:
        # Create a temporary config for ID manager
        app_config = AppConfig(**config_data)
        
        if not app_config.asterisk.id_change.enabled:
            print("ID changing is not enabled in configuration.")
            sys.exit(1)
        
        # Create state manager
        state_manager = ApplicationState(
            state_file=app_config.data_dir / "state.json"
        )
        
        # Create ID manager
        id_manager = IDChangeManager(
            enabled=True,
            id_dir=app_config.asterisk.id_change.id_dir,
            normal_id=app_config.asterisk.id_change.normal_id,
            wx_id=app_config.asterisk.id_change.wx_id,
            rpt_id=app_config.asterisk.id_change.rpt_id,
            id_alerts=app_config.asterisk.id_change.id_alerts,
            state_manager=state_manager
        )
        
        # Force the mode
        changed = id_manager.force_mode(mode)
        if changed:
            print(f"ID changed to {mode} mode.")
            return mode == "WX"
        else:
            print(f"ID already in {mode} mode.")
            return mode == "WX"
            
    except Exception as e:
        logger.error(f"Failed to change ID mode: {e}")
        print(f"Error: {e}")
        sys.exit(1)


def main():
    """Main entry point for SkyControl CLI."""
    if len(sys.argv) < 2:
        print("Usage: skycontrol <command> [value]")
        print("\nAvailable commands:")
        for cmd, info in VALID_COMMANDS.items():
            desc = info.get("description", "")
            print(f"  {cmd:15} - {desc}")
        print("\nExamples:")
        print("  skycontrol enable true")
        print("  skycontrol sayalert toggle")
        print("  skycontrol changect normal")
        print("  skycontrol changeid wx")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    value = sys.argv[2].lower() if len(sys.argv) > 2 else None
    
    # Validate command
    if command not in VALID_COMMANDS:
        print(f"Unknown command: {command}")
        print("Run 'skycontrol' without arguments to see available commands.")
        sys.exit(1)
    
    cmd_info = VALID_COMMANDS[command]
    
    # Handle special commands (changect, changeid)
    if command in ["changect", "changeid"]:
        if value is None:
            print(f"Usage: skycontrol {command} <normal|wx>")
            sys.exit(1)
        
        if value not in cmd_info.get("available_values", []):
            print(f"Invalid value for {command}. Must be one of: {cmd_info['available_values']}")
            sys.exit(1)
        
        # Load config
        try:
            # Try to load config from default location
            config_path = Path("/etc/skywarnplus-ng/config.yaml")
            if not config_path.exists():
                # Try relative path
                config_path = Path("config/default.yaml")
            
            config_data = load_config(config_path)
            
            # Get sounds path
            sounds_path = Path(config_data.get("audio", {}).get("sounds_path", "SOUNDS"))
            if not sounds_path.is_absolute():
                sounds_path = config_path.parent / sounds_path
            
            # Handle the command
            if command == "changect":
                is_wx = handle_changect(config_data, value)
            else:  # changeid
                is_wx = handle_changeid(config_data, value)
            
            # Play audio feedback
            nodes = config_data.get("asterisk", {}).get("nodes", [])
            audio_file = cmd_info["true_file"] if is_wx else cmd_info["false_file"]
            play_audio_feedback(audio_file, nodes, sounds_path)
            
        except Exception as e:
            logger.error(f"Error executing {command}: {e}")
            print(f"Error: {e}")
            sys.exit(1)
        
        sys.exit(0)
    
    # Handle toggle commands
    if value is None:
        print(f"Usage: skycontrol {command} <true|false|toggle>")
        sys.exit(1)
    
    if value not in ["true", "false", "toggle"]:
        print(f"Invalid value: {value}. Must be 'true', 'false', or 'toggle'.")
        sys.exit(1)
    
    # Load config
    try:
        config_path = Path("/etc/skywarnplus-ng/config.yaml")
        if not config_path.exists():
            config_path = Path("config/default.yaml")
        
        config_data = load_config(config_path)
        
        # Get current value
        config_path_str = cmd_info["config_path"]
        current_value = get_nested_value(config_data, config_path_str)
        
        if current_value is None:
            print(f"Configuration path '{config_path_str}' not found in config.")
            sys.exit(1)
        
        # Determine new value
        if value == "toggle":
            new_value = not current_value
        else:
            new_value = value == "true"
        
        # Special handling for tailmessage/enable disable
        tailmessage_was_enabled = config_data.get("alerts", {}).get("tail_message", False)
        
        # Update config
        set_nested_value(config_data, config_path_str, new_value)
        
        # Special handling: create silent tailmessage when disabling
        if command in ["enable", "tailmessage"] and not new_value and tailmessage_was_enabled:
            tailmessage_path = config_data.get("alerts", {}).get("tail_message_path")
            if tailmessage_path:
                create_silent_tailmessage(Path(tailmessage_path))
        
        # Save config
        save_config(config_path, config_data)
        
        print(f"{command} set to {new_value}")
        
        # Play audio feedback
        nodes = config_data.get("asterisk", {}).get("nodes", [])
        audio_file = cmd_info["true_file"] if new_value else cmd_info["false_file"]
        sounds_path = Path(config_data.get("audio", {}).get("sounds_path", "SOUNDS"))
        if not sounds_path.is_absolute():
            sounds_path = config_path.parent / sounds_path
        
        play_audio_feedback(audio_file, nodes, sounds_path)
        
    except Exception as e:
        logger.error(f"Error executing {command}: {e}")
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

