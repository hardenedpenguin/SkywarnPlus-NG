"""
Command-line interface for SkywarnPlus-NG.
"""

import argparse
import asyncio
import logging
import sys
from rich.console import Console

from .core.config import AppConfig
from .core.application import SkywarnPlusApplication

console = Console()
logger = logging.getLogger(__name__)


def setup_logging():
    """Setup basic logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


async def run_application_with_config(config_path=None):
    """Run the main application with specified config."""
    console.print("[bold green]Starting SkywarnPlus-NG[/bold green]")
    
    # Load configuration from YAML
    config = AppConfig.from_yaml(config_path)
    
    # Show web dashboard info if enabled
    if config.monitoring.enabled and config.monitoring.http_server.enabled:
        console.print(f"[bold blue]Web Dashboard:[/bold blue] http://{config.monitoring.http_server.host}:{config.monitoring.http_server.port}")
        console.print("[dim]Available pages: Dashboard, Alerts, Configuration, Health, Logs, Database, Metrics[/dim]")
        console.print()
    
    # Create and run application
    app = SkywarnPlusApplication(config)
    
    try:
        await app.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutdown requested by user[/yellow]")
    except Exception as e:
        console.print(f"[red]Application error: {e}[/red]")
        logger.exception("Unhandled exception")
        raise
    finally:
        await app.shutdown()


async def test_nws_client_with_config(config_path=None):
    """Test the NWS client with specified config."""
    from .api.nws_client import NWSClient
    
    console.print("[bold blue]Testing NWS API Connection[/bold blue]")
    
    # Load configuration from YAML
    config = AppConfig.from_yaml(config_path)
    
    # Create NWS client
    nws_client = NWSClient(config.nws)
    
    try:
        # Test connection
        await nws_client.test_connection()
        console.print("[green]✓ NWS API connection successful[/green]")
        
        # Test fetching alerts for configured counties
        if config.counties:
            console.print(f"\n[bold]Testing alert fetching for {len(config.counties)} counties:[/bold]")
            
            for county in config.counties[:3]:  # Test first 3 counties
                if county.enabled:
                    console.print(f"  Testing {county.name} ({county.code})...")
                    try:
                        alerts = await nws_client.fetch_alerts_for_zone(county.code)
                        console.print(f"    [green]✓ Found {len(alerts)} alerts[/green]")
                    except Exception as e:
                        console.print(f"    [red]✗ Error: {e}[/red]")
        else:
            console.print("[yellow]⚠ No counties configured for testing[/yellow]")
            
    except Exception as e:
        console.print(f"[red]✗ NWS API connection failed: {e}[/red]")
        raise
    finally:
        await nws_client.close()


async def handle_describe_command(config_path=None, index_or_title=None):
    """Handle SkyDescribe command via CLI (for rpt.conf integration)."""
    if not index_or_title:
        print("ERROR: No alert index or title specified")
        print("Usage: skywarnplus-ng describe <index|title>")
        print("Examples:")
        print("  skywarnplus-ng describe 1          # Describe 1st alert")
        print("  skywarnplus-ng describe 2          # Describe 2nd alert")
        print('  skywarnplus-ng describe "Tornado Warning"  # Describe by title')
        sys.exit(1)
    
    try:
        from .core.config import AppConfig
        from .core.state import ApplicationState
        from .audio.manager import AudioManager
        from .skydescribe.manager import SkyDescribeManager
        from collections import OrderedDict
        
        # Load configuration
        config = AppConfig.from_yaml(config_path)
        
        # Load state to get last_alerts
        state_manager = ApplicationState(state_file=config.data_dir / "state.json")
        state = state_manager.load_state()
        
        # Convert last_alerts to the format expected by describe_by_index_or_title
        # State stores: OrderedDict[str, Dict] (alert_id -> alert_data)
        # describe_by_index_or_title expects: OrderedDict[str, List[Dict]] (alert_title -> list of alert_data)
        raw_last_alerts = state.get('last_alerts', OrderedDict())
        if isinstance(raw_last_alerts, list):
            raw_last_alerts = OrderedDict(raw_last_alerts)
        
        if not raw_last_alerts:
            print("ERROR: No alerts found in state. SkywarnPlus-NG may not be running or no alerts have been processed yet.")
            sys.exit(1)
        
        # Convert format: group by alert title (event field) and convert to lists
        last_alerts = OrderedDict()
        for alert_id, alert_data in raw_last_alerts.items():
            # Handle both dict and list formats
            if isinstance(alert_data, dict):
                alert_title = alert_data.get('event', alert_id)
                if alert_title not in last_alerts:
                    last_alerts[alert_title] = []
                last_alerts[alert_title].append(alert_data)
            elif isinstance(alert_data, list):
                # Already in list format, but we still need to group by title
                for data in alert_data:
                    if isinstance(data, dict):
                        alert_title = data.get('event', alert_id)
                        if alert_title not in last_alerts:
                            last_alerts[alert_title] = []
                        last_alerts[alert_title].append(data)
            else:
                # Unexpected format - skip
                logger.warning(f"Unexpected alert_data format for {alert_id}: {type(alert_data)}")
        
        # Create SkyDescribe manager
        audio_manager = AudioManager(config.audio)
        descriptions_dir = config.skydescribe.descriptions_dir
        describe_manager = SkyDescribeManager(
            audio_manager=audio_manager,
            descriptions_dir=descriptions_dir,
            max_words=config.skydescribe.max_words
        )
        
        # Get asterisk nodes from config
        asterisk_nodes = config.asterisk.nodes if config.asterisk.enabled else None
        
        # Call describe_by_index_or_title
        audio_file = describe_manager.describe_by_index_or_title(
            index_or_title=index_or_title,
            last_alerts=last_alerts,
            asterisk_nodes=asterisk_nodes,
            use_describe_wav=True
        )
        
        if audio_file and audio_file.exists():
            print(f"SUCCESS:{audio_file}")
            sys.exit(0)
        else:
            print("ERROR: Failed to generate description audio")
            sys.exit(1)
            
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


async def handle_dtmf_command_with_config(config_path=None, command=None, alert_id=None):
    """Handle DTMF command with specified config."""
    if not command:
        print("ERROR: No DTMF command specified")
        sys.exit(1)
    
    try:
        from .skydescribe.dtmf_handler import DTMFHandler
        
        # Load configuration from YAML
        config = AppConfig.from_yaml(config_path)
        
        # Create DTMF handler
        dtmf_handler = DTMFHandler(config.dtmf)
        
        # Mock callbacks for CLI usage
        def get_current_alerts():
            # This would normally return current alerts from the running application
            # For CLI usage, we'll return empty list
            return []
        
        def get_system_status():
            # This would normally return system status from the running application
            # For CLI usage, we'll return mock status
            return {
                "status": "running",
                "nws_connected": True,
                "audio_available": True,
                "asterisk_available": True,
                "uptime_seconds": 0
            }
        
        def get_alert_by_id(alert_id):
            # This would normally look up from the running application
            # For CLI usage, we'll return None
            return None
        
        dtmf_handler.set_callbacks(get_current_alerts, get_system_status, get_alert_by_id)
        
        # Map command names to DTMF codes
        command_map = {
            'current_alerts': '1',
            'system_status': '2', 
            'alert_details': '3'
        }
        
        if command not in command_map:
            print(f"ERROR: Unknown command '{command}'")
            sys.exit(1)
        
        # Process DTMF command
        dtmf_code = command_map[command]
        response = await dtmf_handler.process_dtmf_code(f"*{dtmf_code}", alert_id)
        
        if response.success:
            print(f"SUCCESS:{response.audio_file}")
        else:
            print(f"ERROR:{response.message}")
            
    except Exception as e:
        print(f"ERROR: {str(e)}")
        sys.exit(1)


def create_parser():
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        description="SkywarnPlus-NG Weather Alert System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s run --config config/default.yaml    Run the main application
  %(prog)s test-nws                           Test NWS API connection
  %(prog)s describe 1                         Generate description for 1st alert (for rpt.conf)
  %(prog)s describe "Tornado Warning"         Generate description by alert title
  %(prog)s dtmf current_alerts                Test DTMF command
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Run command
    run_parser = subparsers.add_parser('run', help='Run the main application')
    run_parser.add_argument('--config', '-c', 
                           help='Configuration file path (default: config/default.yaml)',
                           default='config/default.yaml')
    
    # Test NWS command
    test_nws_parser = subparsers.add_parser('test-nws', help='Test NWS API connection')
    test_nws_parser.add_argument('--config', '-c',
                                help='Configuration file path (default: config/default.yaml)',
                                default='config/default.yaml')
    
    # Describe command (for rpt.conf integration)
    describe_parser = subparsers.add_parser('describe', help='Generate SkyDescribe audio for an alert (for rpt.conf integration)')
    describe_parser.add_argument('--config', '-c',
                                help='Configuration file path (default: config/default.yaml)',
                                default='config/default.yaml')
    describe_parser.add_argument('index_or_title',
                                help='Alert index (1-based) or alert title to describe')
    
    # DTMF command
    dtmf_parser = subparsers.add_parser('dtmf', help='Test DTMF commands')
    dtmf_parser.add_argument('--config', '-c',
                            help='Configuration file path (default: config/default.yaml)',
                            default='config/default.yaml')
    dtmf_parser.add_argument('dtmf_command', 
                            choices=['current_alerts', 'system_status', 'alert_details'],
                            help='DTMF command to test')
    dtmf_parser.add_argument('--alert-id', help='Alert ID for alert_details command')
    
    return parser


def main():
    """Main entry point."""
    setup_logging()
    
    parser = create_parser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        if args.command == 'run':
            asyncio.run(run_application_with_config(args.config))
        elif args.command == 'test-nws':
            asyncio.run(test_nws_client_with_config(args.config))
        elif args.command == 'describe':
            asyncio.run(handle_describe_command(args.config, args.index_or_title))
        elif args.command == 'dtmf':
            asyncio.run(handle_dtmf_command_with_config(args.config, args.dtmf_command, args.alert_id))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Unhandled exception")
        sys.exit(1)


if __name__ == "__main__":
    main()
