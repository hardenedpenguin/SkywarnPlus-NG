#!/usr/bin/env python3
"""
Generate Asterisk configuration for SkywarnPlus-NG DTMF integration.

This script can generate configuration for both:
1. app_rpt (rpt.conf functions) - for repeater nodes
2. Standard Asterisk (extensions.conf) - for PBX/dialplan integration

Usage:
    python3 scripts/generate_asterisk_config.py --type rpt --output /etc/asterisk/custom/skywarnplus_functions.conf
    python3 scripts/generate_asterisk_config.py --type extensions --output /etc/asterisk/custom/skywarnplus_extensions.conf
"""

import sys
import argparse
from pathlib import Path

# Add the src directory to the path so we can import skywarnplus_ng
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from skywarnplus_ng.core.config import AppConfig


def generate_rpt_functions(config: AppConfig) -> str:
    """
    Generate rpt.conf functions for app_rpt integration.
    
    This creates DTMF commands that work with app_rpt repeater software.
    Commands are executed using the 'cop' (Command OPerator) function class.
    Can be placed in /etc/asterisk/custom/ and included in main rpt.conf.
    """
    dtmf = config.skydescribe.dtmf_codes
    
    content = f"""# SkywarnPlus-NG app_rpt Integration
#
# This file can be placed in /etc/asterisk/custom/skywarnplus_functions.conf
# Then include it in your main rpt.conf with:
# #include /etc/asterisk/custom/skywarnplus_functions.conf
#
# Or add these functions directly to your [functions] stanza in rpt.conf
#
# Usage: *<code> (e.g., *{dtmf.current_alerts} for current alerts)
#
# Generated DTMF codes:
# - Current alerts: *{dtmf.current_alerts}
# - Alert by ID: *{dtmf.alert_by_id}<4-digit-id>
# - All clear: *{dtmf.all_clear}
# - System status: *{dtmf.system_status}
# - Help: *{dtmf.help}

[functions]
; SkywarnPlus-NG DTMF functions for weather alerts
; Add these to your existing [functions] stanza or include this file

{dtmf.current_alerts} = cop,1,skywarnplus-ng dtmf current_alerts
{dtmf.alert_by_id} = cop,2,skywarnplus-ng dtmf alert_by_id
{dtmf.all_clear} = cop,3,skywarnplus-ng dtmf all_clear
{dtmf.system_status} = cop,4,skywarnplus-ng dtmf system_status
{dtmf.help} = cop,5,skywarnplus-ng dtmf help

# Note: The 'cop' (Command OPerator) function executes external commands
# - First parameter: DTMF code (without the * prefix)
# - Second parameter: cop function with unique command ID
# - Third parameter: command to execute
#
# Ensure 'skywarnplus-ng' command is in PATH for the asterisk user
"""
    return content


def generate_extensions_dialplan(config: AppConfig) -> str:
    """
    Generate extensions.conf dialplan for standard Asterisk integration.
    
    This creates a proper Asterisk dialplan context for DTMF commands.
    """
    dtmf = config.skydescribe.dtmf_codes
    
    content = f"""# SkywarnPlus-NG Asterisk Extensions for extensions.conf
#
# Add this context to your extensions.conf or custom/extensions.conf
# Include this context in your main dialplan where DTMF should be processed
#
# Usage: Include in your dialplan with: include => skywarnplus-ng
# Then users can dial: *<code> (e.g., *{dtmf.current_alerts})
#
# Generated DTMF codes:
# - Current alerts: *{dtmf.current_alerts}
# - Alert by ID: *{dtmf.alert_by_id}<4-digit-id>
# - All clear: *{dtmf.all_clear}
# - System status: *{dtmf.system_status}
# - Help: *{dtmf.help}

[skywarnplus-ng]
; SkywarnPlus-NG DTMF commands for weather information
; Users can dial these codes to hear detailed weather descriptions

; *{dtmf.current_alerts} - Current active weather alerts
exten => *{dtmf.current_alerts},1,NoOp(SkywarnPlus-NG: Current alerts requested)
exten => *{dtmf.current_alerts},n,Set(SKYWARN_CMD=current_alerts)
exten => *{dtmf.current_alerts},n,Goto(skywarnplus_exec,1)

; *{dtmf.alert_by_id} - Specific alert by ID (requires 4-digit alert ID)
; Usage: *{dtmf.alert_by_id}<4-digit-id> (e.g., *{dtmf.alert_by_id}1234)
exten => _*{dtmf.alert_by_id}XXXX,1,NoOp(SkywarnPlus-NG: Alert by ID requested - ${{EXTEN:{len(dtmf.alert_by_id)+1}}})
exten => _*{dtmf.alert_by_id}XXXX,n,Set(SKYWARN_CMD=alert_by_id)
exten => _*{dtmf.alert_by_id}XXXX,n,Set(SKYWARN_ALERT_ID=${{EXTEN:{len(dtmf.alert_by_id)+1}}})
exten => _*{dtmf.alert_by_id}XXXX,n,Goto(skywarnplus_exec,1)

; *{dtmf.all_clear} - All clear status
exten => *{dtmf.all_clear},1,NoOp(SkywarnPlus-NG: All clear requested)
exten => *{dtmf.all_clear},n,Set(SKYWARN_CMD=all_clear)
exten => *{dtmf.all_clear},n,Goto(skywarnplus_exec,1)

; *{dtmf.system_status} - System status
exten => *{dtmf.system_status},1,NoOp(SkywarnPlus-NG: System status requested)
exten => *{dtmf.system_status},n,Set(SKYWARN_CMD=system_status)
exten => *{dtmf.system_status},n,Goto(skywarnplus_exec,1)

; *{dtmf.help} - Help information
exten => *{dtmf.help},1,NoOp(SkywarnPlus-NG: Help requested)
exten => *{dtmf.help},n,Set(SKYWARN_CMD=help)
exten => *{dtmf.help},n,Goto(skywarnplus_exec,1)

[skywarnplus_exec]
; Execute SkywarnPlus-NG command and play audio response
exten => 1,1,NoOp(SkywarnPlus-NG: Executing command ${{SKYWARN_CMD}})
exten => 1,n,Set(SKYWARN_RESPONSE=${{SHELL(skywarnplus-ng dtmf ${{SKYWARN_CMD}} ${{SKYWARN_ALERT_ID}})}})
exten => 1,n,NoOp(SkywarnPlus-NG: Response - ${{SKYWARN_RESPONSE}})

; Check if command was successful
exten => 1,n,GotoIf($["${{SKYWARN_RESPONSE:0:7}}" = "SUCCESS"]?success,1:error,1)

; Success - play the audio file
exten => success,1,NoOp(SkywarnPlus-NG: Command successful, playing audio)
exten => success,n,Set(AUDIO_FILE=${{SKYWARN_RESPONSE:8}})
exten => success,n,GotoIf($["${{AUDIO_FILE}}" = ""]?no_audio,1)
exten => success,n,Playback(${{AUDIO_FILE}})
exten => success,n,Hangup()

; No audio file returned
exten => no_audio,1,NoOp(SkywarnPlus-NG: No audio file to play)
exten => no_audio,n,Playback(silence/1)
exten => no_audio,n,Hangup()

; Error - play error message or silence
exten => error,1,NoOp(SkywarnPlus-NG: Command failed - ${{SKYWARN_RESPONSE}})
exten => error,n,Playback(silence/1)
exten => error,n,Hangup()

; Include this context in your main dialplan:
; [from-internal] ; or your main context
; include => skywarnplus-ng
; ... your other extensions ...
"""
    return content


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate Asterisk configuration for SkywarnPlus-NG DTMF integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate rpt.conf functions for app_rpt (recommended location)
  %(prog)s --type rpt --output /etc/asterisk/custom/skywarnplus_functions.conf
  
  # Generate extensions.conf dialplan for standard Asterisk
  %(prog)s --type extensions --output /etc/asterisk/custom/skywarnplus_extensions.conf
  
  # Show generated config without writing to file
  %(prog)s --type rpt --show
  %(prog)s --type extensions --show
        """
    )
    
    parser.add_argument(
        "--type", 
        choices=["rpt", "extensions"], 
        required=True,
        help="Type of configuration to generate"
    )
    parser.add_argument(
        "--config", 
        default="config/default.yaml",
        help="SkywarnPlus-NG configuration file (default: config/default.yaml)"
    )
    parser.add_argument(
        "--output", 
        help="Output file path"
    )
    parser.add_argument(
        "--show", 
        action="store_true",
        help="Show generated configuration without writing to file"
    )
    
    args = parser.parse_args()
    
    # Load configuration
    try:
        config = AppConfig.from_yaml(args.config)
    except Exception as e:
        print(f"Error loading configuration: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Generate appropriate configuration
    if args.type == "rpt":
        content = generate_rpt_functions(config)
        default_filename = "skywarnplus_functions.conf"
    else:  # extensions
        content = generate_extensions_dialplan(config)
        default_filename = "skywarnplus_extensions.conf"
    
    # Output the configuration
    if args.show:
        print(content)
    elif args.output:
        output_path = Path(args.output)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                f.write(content)
            print(f"Configuration written to: {output_path}")
        except Exception as e:
            print(f"Error writing to {output_path}: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Write to default location
        output_path = Path(default_filename)
        with open(output_path, 'w') as f:
            f.write(content)
        print(f"Configuration written to: {output_path}")
    
    # Show usage instructions
    if args.type == "rpt":
        print("\nFor app_rpt integration:")
        print("1. Place file in /etc/asterisk/custom/skywarnplus_functions.conf")
        print("2. Add to your main rpt.conf: #include /etc/asterisk/custom/skywarnplus_functions.conf")
        print("3. Or copy the [functions] entries to your existing [functions] stanza")
        print("4. Ensure 'skywarnplus-ng' command is in PATH for asterisk user")
        print("5. Test with DTMF codes on your repeater (e.g., *1 for current alerts)")
    else:
        print("\nFor standard Asterisk integration:")
        print("1. Place file in /etc/asterisk/custom/skywarnplus_extensions.conf")
        print("2. Add to your main extensions.conf: #include custom/skywarnplus_extensions.conf")
        print("3. Add 'include => skywarnplus-ng' to your main context")
        print("4. Ensure 'skywarnplus-ng' command is in PATH for asterisk user")
        print("5. Test with DTMF codes from connected phones/devices")


if __name__ == "__main__":
    main()
