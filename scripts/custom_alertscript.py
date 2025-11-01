#!/usr/bin/env python3
"""
CustomAlertScript.py for SkywarnPlus-NG

This script allows running AlertScript commands at custom intervals via cron,
rather than only when alerts are first detected. This is useful for repeating
commands periodically, such as SkyDescribe announcements.

Example cron entry:
    0 * * * * /usr/local/bin/skywarnplus-ng/scripts/custom_alertscript.py

You can create multiple copies of this script with different configurations
to execute different commands at different intervals.
"""

import json
import subprocess
import sys
import fnmatch
from pathlib import Path
from typing import Dict, List, Optional
import argparse

# Default paths
DEFAULT_STATE_FILE = Path("/var/lib/skywarnplus-ng/state.json")
DEFAULT_CONFIG_FILE = Path("/etc/skywarnplus-ng/config.yaml")


def load_state(state_file: Path) -> Optional[Dict]:
    """Load state file."""
    try:
        if not state_file.exists():
            print(f"ERROR: State file not found: {state_file}")
            return None
        
        with open(state_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"ERROR: Failed to load state file: {e}")
        return None


def load_config(config_file: Path) -> Optional[Dict]:
    """Load configuration file."""
    try:
        if not config_file.exists():
            print(f"ERROR: Config file not found: {config_file}")
            return None
        
        from ruamel.yaml import YAML
        yaml = YAML()
        with open(config_file, 'r') as f:
            return yaml.load(f)
    except Exception as e:
        print(f"ERROR: Failed to load config file: {e}")
        return None


def match_trigger(alert_event: str, mappings: List[Dict]) -> List[Dict]:
    """
    Match alert event against trigger patterns.
    
    Args:
        alert_event: Alert event name
        mappings: List of AlertScript mappings
        
    Returns:
        List of matching mappings
    """
    matching_mappings = []
    
    for mapping in mappings:
        triggers = mapping.get('triggers', [])
        match_type = mapping.get('match', 'ANY').upper()
        
        if match_type == 'ALL':
            # All triggers must match
            if all(fnmatch.fnmatch(alert_event, pattern) for pattern in triggers):
                matching_mappings.append(mapping)
        else:
            # ANY trigger matches (default)
            if any(fnmatch.fnmatch(alert_event, pattern) for pattern in triggers):
                matching_mappings.append(mapping)
    
    return matching_mappings


def execute_bash_command(command: str, alert_data: Dict) -> bool:
    """
    Execute a BASH command with placeholder substitution.
    
    Args:
        command: Command string (may contain placeholders)
        alert_data: Alert data for placeholder substitution
        
    Returns:
        True if command executed successfully
    """
    # Substitute placeholders
    command = command.format(
        alert_title=alert_data.get('event', ''),
        alert_id=alert_data.get('id', ''),
        alert_event=alert_data.get('event', ''),
        alert_area=alert_data.get('area_desc', ''),
        alert_counties=','.join(alert_data.get('county_codes', []))
    )
    
    try:
        print(f"Executing BASH command: {command}")
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print(f"Command executed successfully")
            if result.stdout:
                print(f"Output: {result.stdout}")
            return True
        else:
            print(f"Command failed with exit code {result.returncode}")
            if result.stderr:
                print(f"Error: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print(f"Command timed out after 30 seconds")
        return False
    except Exception as e:
        print(f"Error executing command: {e}")
        return False


def execute_dtmf_command(command: str, nodes: List[int], alert_data: Dict) -> bool:
    """
    Execute a DTMF command on Asterisk nodes.
    
    Args:
        command: DTMF command string
        nodes: List of node numbers
        alert_data: Alert data for placeholder substitution
        
    Returns:
        True if all commands executed successfully
    """
    # Substitute placeholders
    command = command.format(
        alert_title=alert_data.get('event', ''),
        alert_id=alert_data.get('id', ''),
        alert_event=alert_data.get('event', ''),
        alert_area=alert_data.get('area_desc', ''),
        alert_counties=','.join(alert_data.get('county_codes', []))
    )
    
    asterisk_path = Path("/usr/sbin/asterisk")
    success = True
    
    for node in nodes:
        dtmf_cmd = f'rpt fun {node} {command}'
        full_cmd = f'sudo -n -u asterisk {asterisk_path} -rx "{dtmf_cmd}"'
        
        try:
            print(f"Executing DTMF command on node {node}: {dtmf_cmd}")
            result = subprocess.run(
                full_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                print(f"DTMF command executed successfully on node {node}")
                if result.stdout:
                    print(f"Output: {result.stdout}")
            else:
                print(f"DTMF command failed on node {node} (exit {result.returncode})")
                if result.stderr:
                    print(f"Error: {result.stderr}")
                success = False
        except subprocess.TimeoutExpired:
            print(f"DTMF command timed out on node {node}")
            success = False
        except Exception as e:
            print(f"Error executing DTMF command on node {node}: {e}")
            success = False
    
    return success


def process_alerts(state: Dict, config: Dict) -> None:
    """
    Process alerts and execute matching commands.
    
    Args:
        state: State dictionary
        config: Configuration dictionary
    """
    # Get AlertScript mappings from config
    scripts_config = config.get('scripts', {})
    if not scripts_config.get('alertscript_enabled', False):
        print("AlertScript is not enabled in configuration")
        return
    
    mappings = scripts_config.get('alertscript_mappings', [])
    if not mappings:
        print("No AlertScript mappings configured")
        return
    
    # Get active alerts from state
    last_alerts = state.get('last_alerts', {})
    active_alert_ids = state.get('active_alerts', [])
    
    if not active_alert_ids:
        print("No active alerts found")
        return
    
    print(f"Found {len(active_alert_ids)} active alerts")
    
    # Process each active alert
    for alert_id in active_alert_ids:
        if alert_id not in last_alerts:
            continue
        
        alert_data = last_alerts[alert_id]
        alert_event = alert_data.get('event', '')
        
        if not alert_event:
            continue
        
        print(f"\nProcessing alert: {alert_event} (ID: {alert_id})")
        
        # Find matching mappings
        matching_mappings = match_trigger(alert_event, mappings)
        
        if not matching_mappings:
            print(f"No matching triggers found for: {alert_event}")
            continue
        
        # Execute commands for each matching mapping
        for mapping in matching_mappings:
            command_type = mapping.get('type', 'BASH').upper()
            commands = mapping.get('commands', [])
            nodes = mapping.get('nodes', [])
            
            if not commands:
                continue
            
            print(f"Found matching mapping: {mapping.get('triggers', [])}")
            
            for command in commands:
                if command_type == 'DTMF':
                    if not nodes:
                        print("Warning: DTMF command specified but no nodes configured")
                        continue
                    execute_dtmf_command(command, nodes, alert_data)
                else:  # BASH
                    execute_bash_command(command, alert_data)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run AlertScript commands for active alerts at custom intervals"
    )
    parser.add_argument(
        '--state-file',
        type=Path,
        default=DEFAULT_STATE_FILE,
        help=f'Path to state file (default: {DEFAULT_STATE_FILE})'
    )
    parser.add_argument(
        '--config-file',
        type=Path,
        default=DEFAULT_CONFIG_FILE,
        help=f'Path to config file (default: {DEFAULT_CONFIG_FILE})'
    )
    
    args = parser.parse_args()
    
    # Load state and config
    state = load_state(args.state_file)
    if not state:
        sys.exit(1)
    
    config = load_config(args.config_file)
    if not config:
        sys.exit(1)
    
    # Process alerts
    process_alerts(state, config)
    
    print("\nCustom AlertScript execution complete")


if __name__ == "__main__":
    main()

