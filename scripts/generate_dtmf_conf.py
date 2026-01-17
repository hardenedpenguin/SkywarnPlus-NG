#!/usr/bin/env python3
"""
Generate skydescribe.conf for SkywarnPlus-NG app_rpt integration.

This script generates skydescribe.conf for app_rpt repeater nodes.
Maps DTMF codes 841-849 to describe alerts 1-9 by index.

The configuration is written directly to /etc/asterisk/custom/rpt/skydescribe.conf
with 644 permissions and asterisk:asterisk ownership.

Usage:
    python3 scripts/generate_dtmf_conf.py              # Generate and write to /etc/asterisk/custom/rpt/skydescribe.conf
    python3 scripts/generate_dtmf_conf.py --show       # Show configuration without writing
"""

import sys
import argparse
import os
from pathlib import Path

def generate_skydescribe_rpt() -> str:
    """
    Generate skydescribe.conf for app_rpt integration.
    
    This creates DTMF commands for SkyDescribe functionality, similar to the
    original SkywarnPlus where codes 841-849 map to describe alerts 1-9.
    
    Output goes to /etc/asterisk/custom/rpt/skydescribe.conf
    
    Uses the installation path from install.sh:
    - Installation: /var/lib/skywarnplus-ng
    - Command: /var/lib/skywarnplus-ng/venv/bin/skywarnplus-ng
    """
    # Use the installation path from install.sh
    cmd_path = "/var/lib/skywarnplus-ng/venv/bin/skywarnplus-ng"
    config_path = "/etc/skywarnplus-ng/config.yaml"
    
    content = f""";;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;;;;;;;;;;;;; SkyDescribe ;;;;;;;;;;;;
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;MENU:skydescribe:functions:SkyDescribe weather alert descriptions via DTMF
;
; [functions] overrides for SkyDescribe (SkywarnPlus-NG)
; Maps DTMF codes 841-849 to describe alerts 1-9 by index
; Also supports alert lookup by title via the describe command
;
[functions-skydescribe](!)
841 = cmd,sh -c "cd /tmp && {cmd_path} describe --config {config_path} 1"
842 = cmd,sh -c "cd /tmp && {cmd_path} describe --config {config_path} 2"
843 = cmd,sh -c "cd /tmp && {cmd_path} describe --config {config_path} 3"
844 = cmd,sh -c "cd /tmp && {cmd_path} describe --config {config_path} 4"
845 = cmd,sh -c "cd /tmp && {cmd_path} describe --config {config_path} 5"
846 = cmd,sh -c "cd /tmp && {cmd_path} describe --config {config_path} 6"
847 = cmd,sh -c "cd /tmp && {cmd_path} describe --config {config_path} 7"
848 = cmd,sh -c "cd /tmp && {cmd_path} describe --config {config_path} 8"
849 = cmd,sh -c "cd /tmp && {cmd_path} describe --config {config_path} 9"

"""
    return content


def main():
    """Main entry point."""
    # Fixed output path
    OUTPUT_PATH = Path("/etc/asterisk/custom/rpt/skydescribe.conf")
    
    parser = argparse.ArgumentParser(
        description="Generate skydescribe.conf for SkywarnPlus-NG app_rpt integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate and write to /etc/asterisk/custom/rpt/skydescribe.conf
  %(prog)s
  
  # Show generated config without writing to file
  %(prog)s --show
        """
    )
    parser.add_argument(
        "--show", 
        action="store_true",
        help="Show generated configuration without writing to file"
    )
    
    args = parser.parse_args()
    
    # Generate skydescribe configuration (no config needed - hardcoded paths)
    content = generate_skydescribe_rpt()
    
    # Output the configuration
    if args.show:
        print(content)
    else:
        # Write directly to /etc/asterisk/custom/rpt/skydescribe.conf
        output_path = OUTPUT_PATH
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                f.write(content)
            
            # Set permissions to 644
            os.chmod(output_path, 0o644)
            
            # Set ownership to asterisk:asterisk if possible
            try:
                import pwd
                import grp
                uid = pwd.getpwnam('asterisk').pw_uid
                gid = grp.getgrnam('asterisk').gr_gid
                os.chown(output_path, uid, gid)
                print(f"Configuration written to: {output_path}")
                print(f"Set permissions to 644 and ownership to asterisk:asterisk")
            except (KeyError, PermissionError, OSError) as e:
                # If asterisk user/group doesn't exist or we don't have permission,
                # just print a warning but don't fail
                print(f"Configuration written to: {output_path}")
                print(f"Warning: Could not set ownership to asterisk:asterisk: {e}", file=sys.stderr)
                print(f"You may need to set ownership manually: sudo chown asterisk:asterisk {output_path}", file=sys.stderr)
        except PermissionError:
            print(f"Error: Permission denied writing to {output_path}", file=sys.stderr)
            print("You may need to run with sudo: sudo python3 scripts/generate_dtmf_conf.py", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error writing to {output_path}: {e}", file=sys.stderr)
            sys.exit(1)
    
    # Show usage instructions
    if not args.show:
        print("\nSkyDescribe configuration has been generated and installed.")
        print("\nNext steps:")
        print("1. Enable SkyDescribe for your node via ASL-menu (AllStarLink menu system)")
        print("2. Ensure 'skywarnplus-ng' command is accessible for asterisk user")
        print("3. Test with DTMF codes 841-849 on your repeater to describe alerts 1-9")


if __name__ == "__main__":
    main()
