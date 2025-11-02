"""
Core application logic for SkywarnPlus-NG.
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any, Set

from .config import AppConfig
from .state import ApplicationState
from .models import WeatherAlert, AlertStatus
from ..api.nws_client import NWSClient, NWSClientError
from ..audio.manager import AudioManager, AudioManagerError
from ..audio.tail_message import TailMessageManager, TailMessageError
from ..asterisk.manager import AsteriskManager, AsteriskError
from ..asterisk.courtesy_tone import CourtesyToneManager, CourtesyToneError
from ..asterisk.id_change import IDChangeManager, IDChangeError
from ..utils.script_manager import ScriptManager, ScriptExecutionError
from ..utils.alertscript import AlertScriptManager
from ..utils.logging import setup_logging, PerformanceLogger, AlertLogger
from ..monitoring.health import HealthMonitor
from ..database.manager import DatabaseManager, DatabaseError
from ..web.server import WebDashboard
from ..processing.pipeline import AlertProcessingPipeline, ProcessingStage
from ..processing.filters import FilterChain, GeographicFilter, TimeFilter, SeverityFilter, CustomRuleFilter
from ..processing.deduplication import AlertDeduplicator, DuplicateDetectionStrategy
from ..processing.prioritization import AlertPrioritizer
from ..processing.validation import AlertValidator
from ..processing.workflows import WorkflowEngine, AlertWorkflow, WorkflowStep, ResponseAction, ActionType
from ..processing.analytics import AlertAnalytics

logger = logging.getLogger(__name__)


class SkywarnPlusApplication:
    """Main application class for SkywarnPlus-NG."""

    def __init__(self, config: AppConfig):
        """
        Initialize the application.

        Args:
            config: Application configuration
        """
        self.config = config
        self.state_manager = ApplicationState(
            state_file=config.data_dir / "state.json"
        )
        self.nws_client: Optional[NWSClient] = None
        self.audio_manager: Optional[AudioManager] = None
        self.tail_message_manager: Optional[TailMessageManager] = None
        self.asterisk_manager: Optional[AsteriskManager] = None
        self.courtesy_tone_manager: Optional[CourtesyToneManager] = None
        self.id_change_manager: Optional[IDChangeManager] = None
        self.script_manager: Optional[ScriptManager] = None
        self.alertscript_manager: Optional[AlertScriptManager] = None
        self._previous_alert_events: Set[str] = set()  # Track previous alert events for transitions
        self.health_monitor: Optional[HealthMonitor] = None
        self.database_manager: Optional[DatabaseManager] = None
        self.performance_logger: Optional[PerformanceLogger] = None
        self.alert_logger: Optional[AlertLogger] = None
        self.web_dashboard: Optional[WebDashboard] = None
        self.alert_pipeline: Optional[AlertProcessingPipeline] = None
        self.filter_chain: Optional[FilterChain] = None
        self.deduplicator: Optional[AlertDeduplicator] = None
        self.prioritizer: Optional[AlertPrioritizer] = None
        self.validator: Optional[AlertValidator] = None
        self.workflow_engine: Optional[WorkflowEngine] = None
        self.analytics: Optional[AlertAnalytics] = None
        self.running = False
        self._shutdown_event = asyncio.Event()
        self._start_time = datetime.now(timezone.utc)

    async def initialize(self) -> None:
        """Initialize the application components."""
        # Setup enhanced logging first
        _, self.performance_logger, self.alert_logger = setup_logging(self.config.logging)
        logger.info("Initializing SkywarnPlus-NG application")

        # Initialize NWS client
        self.nws_client = NWSClient(self.config.nws)
        
        # Test NWS connection
        if not await self.nws_client.test_connection():
            logger.warning("NWS API connection test failed - continuing anyway")
        else:
            logger.info("NWS API connection test successful")

        # Initialize audio manager
        try:
            self.audio_manager = AudioManager(self.config.audio)
            logger.info("Audio manager initialized successfully")
        except AudioManagerError as e:
            logger.error(f"Failed to initialize audio manager: {e}")
            logger.warning("Audio features will be disabled")
            self.audio_manager = None

        # Initialize tail message manager
        if self.audio_manager and self.config.alerts.tail_message:
            try:
                # Determine tail message file path
                if self.config.alerts.tail_message_path:
                    tail_message_path = self.config.alerts.tail_message_path
                else:
                    tail_message_path = self.config.data_dir / "wx-tail.wav"
                
                self.tail_message_manager = TailMessageManager(
                    audio_config=self.config.audio,
                    alert_config=self.config.alerts,
                    filtering_config=self.config.filtering,
                    tail_message_path=tail_message_path,
                    audio_delay_ms=self.config.asterisk.audio_delay,
                    with_county_names=self.config.alerts.tail_message_counties,
                    suffix_file=self.config.alerts.tail_message_suffix
                )
                logger.info(f"Tail message manager initialized (path: {tail_message_path})")
            except Exception as e:
                logger.error(f"Failed to initialize tail message manager: {e}")
                logger.warning("Tail message features will be disabled")
                self.tail_message_manager = None
        else:
            logger.info("Tail messages disabled in configuration")

        # Initialize Asterisk manager
        if self.config.asterisk.enabled:
            try:
                self.asterisk_manager = AsteriskManager(self.config.asterisk)
                
                # Test Asterisk connection
                if await self.asterisk_manager.test_connection():
                    logger.info("Asterisk manager initialized successfully")
                else:
                    logger.warning("Asterisk connection test failed - continuing anyway")
            except AsteriskError as e:
                logger.error(f"Failed to initialize Asterisk manager: {e}")
                logger.warning("Asterisk features will be disabled")
                self.asterisk_manager = None
        else:
            logger.info("Asterisk integration disabled in configuration")

        # Initialize courtesy tone manager
        if self.config.asterisk.courtesy_tones.enabled:
            try:
                self.courtesy_tone_manager = CourtesyToneManager(
                    enabled=self.config.asterisk.courtesy_tones.enabled,
                    tone_dir=self.config.asterisk.courtesy_tones.tone_dir,
                    tones_config=self.config.asterisk.courtesy_tones.tones,
                    ct_alerts=self.config.asterisk.courtesy_tones.ct_alerts,
                    state_manager=self.state_manager
                )
                logger.info("Courtesy tone manager initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize courtesy tone manager: {e}")
                logger.warning("Courtesy tone features will be disabled")
                self.courtesy_tone_manager = None
        else:
            logger.info("Courtesy tone switching disabled in configuration")

        # Initialize ID change manager
        if self.config.asterisk.id_change.enabled:
            try:
                self.id_change_manager = IDChangeManager(
                    enabled=self.config.asterisk.id_change.enabled,
                    id_dir=self.config.asterisk.id_change.id_dir,
                    normal_id=self.config.asterisk.id_change.normal_id,
                    wx_id=self.config.asterisk.id_change.wx_id,
                    rpt_id=self.config.asterisk.id_change.rpt_id,
                    id_alerts=self.config.asterisk.id_change.id_alerts,
                    state_manager=self.state_manager
                )
                logger.info("ID change manager initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize ID change manager: {e}")
                logger.warning("ID change features will be disabled")
                self.id_change_manager = None
        else:
            logger.info("ID changing disabled in configuration")

        # Initialize script manager
        if self.config.scripts.enabled:
            try:
                self.script_manager = ScriptManager(self.config.scripts)
                logger.info("Script manager initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize script manager: {e}")
                logger.warning("Script execution will be disabled")
                self.script_manager = None
        else:
            logger.info("Script execution disabled in configuration")

        # Initialize enhanced AlertScript manager
        if self.config.scripts.alertscript_enabled:
            try:
                # Convert mapping configs to dict format
                mappings = [mapping.model_dump() for mapping in self.config.scripts.alertscript_mappings]
                active_commands = None
                inactive_commands = None
                
                if self.config.scripts.alertscript_active_commands:
                    active_commands = [cmd.model_dump() for cmd in self.config.scripts.alertscript_active_commands]
                if self.config.scripts.alertscript_inactive_commands:
                    inactive_commands = [cmd.model_dump() for cmd in self.config.scripts.alertscript_inactive_commands]
                
                self.alertscript_manager = AlertScriptManager(
                    enabled=True,
                    mappings=mappings,
                    active_commands=active_commands,
                    inactive_commands=inactive_commands,
                    asterisk_path=Path("/usr/sbin/asterisk")
                )
                logger.info("Enhanced AlertScript manager initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize AlertScript manager: {e}")
                logger.warning("AlertScript features will be disabled")
                self.alertscript_manager = None
        else:
            logger.info("Enhanced AlertScript disabled in configuration")

        # Initialize database manager
        if self.config.database.enabled:
            try:
                self.database_manager = DatabaseManager(self.config)
                await self.database_manager.initialize()
                logger.info("Database manager initialized successfully")
            except DatabaseError as e:
                logger.error(f"Failed to initialize database manager: {e}")
                logger.warning("Database features will be disabled")
                self.database_manager = None
        else:
            logger.info("Database storage disabled in configuration")

        # Initialize health monitor
        self.health_monitor = HealthMonitor(self.config, self._start_time)
        self.health_monitor.set_components(
            nws_client=self.nws_client,
            audio_manager=self.audio_manager,
            asterisk_manager=self.asterisk_manager,
            script_manager=self.script_manager,
            database_manager=self.database_manager
        )
        logger.info("Health monitor initialized")

        # Initialize web dashboard
        if self.config.monitoring.enabled and self.config.monitoring.http_server.enabled:
            try:
                self.web_dashboard = WebDashboard(self, self.config)
                await self.web_dashboard.start(
                    host=self.config.monitoring.http_server.host,
                    port=self.config.monitoring.http_server.port
                )
                logger.info("Web dashboard initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize web dashboard: {e}")
                logger.warning("Web dashboard will be disabled")
                self.web_dashboard = None
        else:
            logger.info("Web dashboard disabled in configuration")

        # Initialize alert processing pipeline
        try:
            self._initialize_processing_pipeline()
            logger.info("Alert processing pipeline initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize processing pipeline: {e}")
            logger.warning("Alert processing pipeline will be disabled")
            self.alert_pipeline = None

        # Handle cleanslate mode
        if self.config.dev.cleanslate:
            logger.info("DEV: Cleanslate mode enabled, clearing cached state")
            self.state_manager.clear_state()
        
        # Load initial state
        self.state = self.state_manager.load_state()
        logger.info("Application initialized successfully")

    def _initialize_processing_pipeline(self) -> None:
        """Initialize the alert processing pipeline components."""
        # Initialize analytics
        self.analytics = AlertAnalytics()
        
        # Initialize filter chain
        self.filter_chain = FilterChain("MainFilterChain")
        
        # Add geographic filter
        geo_filter = GeographicFilter(
            name="GeographicFilter",
            enabled=True,
            allowed_counties=[c.code for c in self.config.counties if c.enabled],
            blocked_counties=[]
        )
        self.filter_chain.add_filter(geo_filter)
        
        # Add time filter
        time_filter = TimeFilter(
            name="TimeFilter",
            enabled=True,
            business_hours_only=False,
            weekdays_only=False,
            time_window_hours=24
        )
        self.filter_chain.add_filter(time_filter)
        
        # Add severity filter
        severity_filter = SeverityFilter(
            name="SeverityFilter",
            enabled=True,
            min_severity=None,  # Accept all severities
            blocked_severities=[]
        )
        self.filter_chain.add_filter(severity_filter)
        
        # Initialize deduplicator
        self.deduplicator = AlertDeduplicator(
            strategy=DuplicateDetectionStrategy.HYBRID,
            similarity_threshold=0.8,
            time_window_minutes=30
        )
        
        # Initialize prioritizer
        self.prioritizer = AlertPrioritizer()
        
        # Initialize validator
        self.validator = AlertValidator(
            min_confidence_threshold=0.6,
            enable_cross_validation=True,
            enable_anomaly_detection=True,
            enable_consistency_checks=True
        )
        
        # Initialize workflow engine
        self.workflow_engine = WorkflowEngine()
        
        # Create default workflow for severe alerts
        severe_workflow = self._create_severe_alert_workflow()
        self.workflow_engine.register_workflow(severe_workflow)
        
        # Initialize processing pipeline
        self.alert_pipeline = AlertProcessingPipeline()
        
        # Add processors to pipeline
        from ..processing.pipeline import AlertProcessor
        
        # Filter processor
        class FilterProcessor(AlertProcessor):
            def __init__(self, filter_chain: FilterChain):
                super().__init__("FilterProcessor")
                self.filter_chain = filter_chain
            
            async def process(self, context):
                result = self.filter_chain.filter_alert(context.alert)
                if not result.passed:
                    context.metadata["filtered"] = True
                    context.metadata["filter_reason"] = result.reason
                return context
        
        # Deduplication processor
        class DeduplicationProcessor(AlertProcessor):
            def __init__(self, deduplicator: AlertDeduplicator):
                super().__init__("DeduplicationProcessor")
                self.deduplicator = deduplicator
            
            async def process(self, context):
                # This would be called on a batch of alerts
                # For now, just pass through
                return context
        
        # Prioritization processor
        class PrioritizationProcessor(AlertProcessor):
            def __init__(self, prioritizer: AlertPrioritizer):
                super().__init__("PrioritizationProcessor")
                self.prioritizer = prioritizer
            
            async def process(self, context):
                priority_score = self.prioritizer.prioritize_alert(context.alert)
                context.metadata["priority_score"] = priority_score.total_score
                context.metadata["priority_level"] = priority_score.priority_level.value
                return context
        
        # Validation processor
        class ValidationProcessor(AlertProcessor):
            def __init__(self, validator: AlertValidator):
                super().__init__("ValidationProcessor")
                self.validator = validator
            
            async def process(self, context):
                validation_result = self.validator.validate_alert(context.alert)
                context.metadata["validation_status"] = validation_result.status.value
                context.metadata["confidence_score"] = validation_result.confidence_score
                return context
        
        # Workflow processor
        class WorkflowProcessor(AlertProcessor):
            def __init__(self, workflow_engine: WorkflowEngine):
                super().__init__("WorkflowProcessor")
                self.workflow_engine = workflow_engine
            
            async def process(self, context):
                executions = await self.workflow_engine.execute_workflows(context.alert)
                context.metadata["workflow_executions"] = len(executions)
                return context
        
        # Add processors to pipeline
        self.alert_pipeline.add_processor(
            FilterProcessor(self.filter_chain), 
            ProcessingStage.FILTERED
        )
        self.alert_pipeline.add_processor(
            DeduplicationProcessor(self.deduplicator), 
            ProcessingStage.DEDUPLICATED
        )
        self.alert_pipeline.add_processor(
            PrioritizationProcessor(self.prioritizer), 
            ProcessingStage.PRIORITIZED
        )
        self.alert_pipeline.add_processor(
            ValidationProcessor(self.validator), 
            ProcessingStage.VALIDATED
        )
        self.alert_pipeline.add_processor(
            WorkflowProcessor(self.workflow_engine), 
            ProcessingStage.WORKFLOW_EXECUTED
        )
    
    def _create_severe_alert_workflow(self) -> AlertWorkflow:
        """Create a default workflow for severe alerts."""
        # Create workflow steps
        notification_step = WorkflowStep(
            step_id="notification",
            name="Send Notifications",
            description="Send notifications for severe alerts",
            actions=[
                ResponseAction(
                    action_id="email_notification",
                    action_type=ActionType.NOTIFICATION,
                    name="Email Notification",
                    description="Send email notification",
                    parameters={"type": "email", "priority": "high"}
                ),
                ResponseAction(
                    action_id="sms_notification",
                    action_type=ActionType.NOTIFICATION,
                    name="SMS Notification",
                    description="Send SMS notification",
                    parameters={"type": "sms", "priority": "high"}
                )
            ],
            conditions=[
                {"type": "severity_gte", "severity": "Severe"}
            ]
        )
        
        escalation_step = WorkflowStep(
            step_id="escalation",
            name="Escalate Alert",
            description="Escalate severe alerts to management",
            actions=[
                ResponseAction(
                    action_id="management_escalation",
                    action_type=ActionType.ESCALATION,
                    name="Management Escalation",
                    description="Escalate to management team",
                    parameters={"escalation_level": "management"}
                )
            ],
            conditions=[
                {"type": "severity_equals", "severity": "Extreme"}
            ]
        )
        
        # Create workflow
        workflow = AlertWorkflow(
            workflow_id="severe_alert_workflow",
            name="Severe Alert Workflow",
            description="Workflow for processing severe weather alerts",
            trigger_conditions=[
                {"type": "severity_gte", "severity": "Severe"}
            ],
            steps=[notification_step, escalation_step],
            enabled=True
        )
        
        return workflow

    async def shutdown(self) -> None:
        """Shutdown the application gracefully."""
        logger.info("Shutting down SkywarnPlus-NG application")
        
        self.running = False
        self._shutdown_event.set()
        
        # Close database connections
        if self.database_manager:
            await self.database_manager.close()
        
        # Stop web dashboard
        if self.web_dashboard:
            await self.web_dashboard.stop()
        
        if self.nws_client:
            await self.nws_client.close()
        
        # Save final state
        self.state_manager.save_state(self.state)
        logger.info("Application shutdown complete")

    async def run(self) -> None:
        """Run the main application loop."""
        await self.initialize()
        
        # Set up signal handlers for graceful shutdown
        self._setup_signal_handlers()
        
        self.running = True
        logger.info(f"Starting main loop with {self.config.poll_interval}s poll interval")
        
        try:
            while self.running:
                await self._poll_cycle()
                
                # Wait for next poll or shutdown signal
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(), 
                        timeout=self.config.poll_interval
                    )
                    break  # Shutdown signal received
                except asyncio.TimeoutError:
                    pass  # Continue to next poll cycle
                    
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
        finally:
            await self.shutdown()

    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating shutdown")
            # Signal the shutdown event instead of creating a task from signal handler
            # Signal handlers run in a different thread context, so we use an Event
            # that the main loop is already waiting on
            self._shutdown_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def _poll_cycle(self) -> None:
        """Execute one polling cycle."""
        logger.debug("Starting poll cycle")
        
        try:
            # Update poll time
            self.state_manager.update_poll_time(self.state)
            
            # Get county codes from configuration
            county_codes = [county.code for county in self.config.counties if county.enabled]
            if not county_codes:
                logger.warning("No enabled counties configured")
                return

            # Fetch alerts from NWS
            current_alerts = await self._fetch_alerts(county_codes)
            
            # Process alerts
            await self._process_alerts(current_alerts)
            
            # Clean up old alerts
            self.state_manager.cleanup_old_alerts(self.state)
            
            # Update tail message if enabled
            if self.tail_message_manager:
                try:
                    self.tail_message_manager.update_tail_message(current_alerts)
                except Exception as e:
                    logger.error(f"Error updating tail message: {e}")
            
            # Update courtesy tones if enabled
            if self.courtesy_tone_manager:
                try:
                    self.courtesy_tone_manager.update_courtesy_tones(current_alerts)
                except Exception as e:
                    logger.error(f"Error updating courtesy tones: {e}")
            
            # Update ID if enabled
            if self.id_change_manager:
                try:
                    self.id_change_manager.update_id(current_alerts)
                except Exception as e:
                    logger.error(f"Error updating ID: {e}")
            
            # Process enhanced AlertScript mappings
            if self.alertscript_manager:
                try:
                    processed_events = await self.alertscript_manager.process_alerts(
                        current_alerts,
                        self._previous_alert_events
                    )
                    self._previous_alert_events = processed_events
                except Exception as e:
                    logger.error(f"Error processing AlertScript mappings: {e}")
            
            # Clean up old audio files
            if self.audio_manager:
                self.audio_manager.cleanup_old_audio()
            
            # Save state
            self.state_manager.save_state(self.state)
            
            # Broadcast status update via WebSocket
            if self.web_dashboard:
                await self.web_dashboard.broadcast_update('status_update', self.get_status())
            
            logger.debug(f"Poll cycle complete - {len(current_alerts)} alerts processed")
            
        except Exception as e:
            logger.error(f"Error in poll cycle: {e}", exc_info=True)

    async def _fetch_alerts(self, county_codes: List[str]) -> List[WeatherAlert]:
        """
        Fetch alerts from NWS API or generate test alerts.

        Args:
            county_codes: List of county codes to fetch alerts for

        Returns:
            List of current alerts
        """
        if not self.nws_client:
            logger.error("NWS client not initialized")
            return []

        try:
            # Check for test injection mode
            if self.config.dev.inject_enabled:
                logger.info("DEV: Test alert injection enabled, generating tornado warning test alert")
                # Auto-generate a tornado warning for all configured counties
                if county_codes:
                    tornado_alert_config = [{
                        "Title": "Tornado Warning",
                        "CountyCodes": county_codes
                    }]
                    injected_alerts = self.nws_client.generate_inject_alerts(
                        tornado_alert_config,
                        county_codes
                    )
                    logger.info(f"Generated {len(injected_alerts)} test tornado warning alerts for {len(county_codes)} counties")
                    return injected_alerts
                else:
                    logger.warning("DEV: No counties configured, cannot generate test alert")
                    return []
            
            # Fetch alerts for all counties concurrently
            alerts = await self.nws_client.fetch_alerts_for_zones(county_codes)
            
            # Filter to only active alerts
            active_alerts = self.nws_client.filter_active_alerts(
                alerts, 
                time_type=self.config.alerts.time_type
            )
            
            logger.info(f"Fetched {len(active_alerts)} active alerts from {len(county_codes)} counties")
            return active_alerts
            
        except NWSClientError as e:
            logger.error(f"Failed to fetch alerts: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching alerts: {e}", exc_info=True)
            return []

    async def _process_alerts(self, current_alerts: List[WeatherAlert]) -> None:
        """
        Process alerts and determine what actions to take.

        Args:
            current_alerts: List of current active alerts
        """
        # Apply processing pipeline if available
        if self.alert_pipeline and current_alerts:
            try:
                # Process alerts through the pipeline
                processing_results = await self.alert_pipeline.process_alerts(current_alerts)
                
                # Update analytics
                if self.analytics:
                    for result in processing_results:
                        if result.processed:
                            self.analytics.add_alert(result.alert, result.processing_time_ms)
                        else:
                            self.analytics.add_error("processing_failed")
                
                # Filter out alerts that were filtered by the pipeline
                processed_alerts = [
                    result.alert for result in processing_results
                    if result.processed and not result.metadata.get("filtered", False)
                ]
            except Exception as e:
                logger.error(f"Alert processing pipeline failed: {e}")
                processed_alerts = current_alerts
        else:
            processed_alerts = current_alerts
        
        # Get new and expired alerts
        new_alerts = self.state_manager.get_new_alerts(self.state, processed_alerts)
        expired_alerts = self.state_manager.get_expired_alerts(self.state, processed_alerts)
        
        # Detect county changes (for SayAlertsChanged)
        alerts_with_county_changes = []
        if self.config.alerts.say_alerts_changed:
            alerts_with_county_changes = self.state_manager.detect_county_changes(
                self.state, processed_alerts
            )
        
        # Update active alerts
        current_alert_ids = [alert.id for alert in processed_alerts]
        self.state_manager.update_active_alerts(self.state, current_alert_ids)
        
        # Process new alerts
        if new_alerts:
            await self._handle_new_alerts(new_alerts)
        
        # Process alerts with county changes (SayAlertsChanged)
        if alerts_with_county_changes:
            if self.config.alerts.say_alert_all:
                # Say all alerts when one changes
                await self._handle_alerts_with_changes(processed_alerts)
            else:
                # Only say the alerts that changed
                await self._handle_alerts_with_changes(alerts_with_county_changes)
        
        # Process expired alerts
        if expired_alerts:
            await self._handle_expired_alerts(expired_alerts)
        
        # Check for all-clear scenario
        if not processed_alerts and self.state.get('active_alerts'):
            await self._handle_all_clear()

    async def _handle_new_alerts(self, new_alerts: List[WeatherAlert], all_current_alerts: Optional[List[WeatherAlert]] = None) -> None:
        """
        Handle newly discovered alerts.

        Args:
            new_alerts: List of new alerts
            all_current_alerts: Optional list of all current alerts (for multiples detection)
        """
        logger.info(f"Processing {len(new_alerts)} new alerts")
        
        for alert in new_alerts:
            # Start performance timer for this alert
            timer_id = self.performance_logger.start_timer(f"alert_processing_{alert.id}") if self.performance_logger else None
            alert_start_time = datetime.now(timezone.utc)
            
            try:
                # Log alert received
                self.alert_logger.log_alert_received(
                    alert.id, alert.event, alert.area_desc,
                    severity=alert.severity.value,
                    urgency=alert.urgency.value,
                    certainty=alert.certainty.value
                ) if self.alert_logger else logger.info(f"New alert detected: {alert.event} (ID: {alert.id})")
                
                # Add to state
                self.state_manager.add_alert(self.state, alert)
                
                # Check if alert should be announced
                announcement_nodes = []
                if self._should_announce_alert(alert):
                    announcement_nodes = await self._announce_alert(alert)
                    if announcement_nodes:
                        self.state_manager.mark_alert_announced(self.state, alert.id)
                
                # Execute alert script
                if self.script_manager:
                    script_success = await self.script_manager.execute_alert_script(alert)
                    if script_success:
                        self.state_manager.mark_alert_script_triggered(self.state, alert.id)
                        logger.info(f"Alert script executed successfully for: {alert.event}")
                    else:
                        logger.warning(f"Alert script failed for: {alert.event}")
                
                # Send PushOver notification if enabled
                if self.config.pushover.enabled and self.config.pushover.api_token and self.config.pushover.user_key:
                    try:
                        from ..notifications.pushover import PushOverNotifier, PushOverConfig
                        pushover_config = PushOverConfig(
                            api_token=self.config.pushover.api_token,
                            user_key=self.config.pushover.user_key,
                            enabled=True,
                            priority=self.config.pushover.priority,
                            sound=self.config.pushover.sound,
                            timeout_seconds=self.config.pushover.timeout_seconds,
                            retry_count=self.config.pushover.retry_count,
                            retry_delay_seconds=self.config.pushover.retry_delay_seconds
                        )
                        async with PushOverNotifier(pushover_config) as pushover:
                            result = await pushover.send_alert_push(alert)
                            if result.get("success", False):
                                logger.info(f"PushOver notification sent for alert: {alert.event}")
                            else:
                                logger.warning(f"PushOver notification failed: {result.get('error', 'Unknown error')}")
                    except Exception as e:
                        logger.error(f"Failed to send PushOver notification: {e}")
                
                # Log alert processing completion
                processing_time = (datetime.now(timezone.utc) - alert_start_time).total_seconds() * 1000
                self.alert_logger.log_alert_processed(
                    alert.id, alert.event, True, processing_time,
                    severity=alert.severity.value,
                    area=alert.area_desc
                ) if self.alert_logger else logger.info(f"Processed new alert: {alert.event} ({alert.severity.value})")
                
                # Store alert in database
                if self.database_manager:
                    try:
                        await self.database_manager.store_alert(
                            alert=alert,
                            announced=self._should_announce_alert(alert),
                            script_executed=script_success if self.script_manager else False,
                            announcement_nodes=announcement_nodes
                        )
                    except DatabaseError as e:
                        logger.error(f"Failed to store alert in database: {e}")
                
                # Broadcast alert update via WebSocket
                if self.web_dashboard:
                    # Use mode='json' to ensure datetime objects are serialized as ISO strings
                    await self.web_dashboard.broadcast_update('alerts_update', [alert.model_dump(mode='json')])
                
            except Exception as e:
                processing_time = (datetime.now(timezone.utc) - alert_start_time).total_seconds() * 1000
                self.alert_logger.log_alert_processed(
                    alert.id, alert.event, False, processing_time,
                    error=str(e)
                ) if self.alert_logger else logger.error(f"Error processing alert {alert.event}: {e}")
                raise
            finally:
                # End performance timer
                if timer_id and self.performance_logger:
                    self.performance_logger.end_timer(timer_id, success=True)

    async def _handle_expired_alerts(self, expired_alert_ids: List[str]) -> None:
        """
        Handle expired alerts.

        Args:
            expired_alert_ids: List of expired alert IDs
        """
        logger.info(f"Processing {len(expired_alert_ids)} expired alerts")
        
        for alert_id in expired_alert_ids:
            # Clean up audio files for this alert
            if self.audio_manager:
                try:
                    audio_cleaned = self.audio_manager.cleanup_alert_audio(alert_id)
                    if audio_cleaned > 0:
                        logger.debug(f"Cleaned up {audio_cleaned} audio file(s) for expired alert {alert_id}")
                except Exception as e:
                    logger.warning(f"Failed to clean up audio files for alert {alert_id}: {e}")
            
            # Clean up description files for this alert
            # Note: SkyDescribeManager may not always be initialized, so we clean up files directly
            try:
                from ..skydescribe.manager import SkyDescribeManager
                descriptions_dir = self.config.descriptions_dir
                if descriptions_dir.exists():
                    # Use the cleanup method if we have access to SkyDescribeManager
                    # Otherwise, we'll clean up files directly via glob pattern matching
                    import fnmatch
                    cleaned_desc_count = 0
                    for file_path in descriptions_dir.iterdir():
                        if file_path.is_file():
                            try:
                                filename = file_path.name
                                # Match pattern: desc_{alert_id}_*
                                if fnmatch.fnmatch(filename, f"desc_{alert_id}_*"):
                                    file_path.unlink()
                                    cleaned_desc_count += 1
                                    logger.debug(f"Cleaned up description file for alert {alert_id}: {file_path}")
                            except OSError as e:
                                logger.warning(f"Failed to clean up description file {file_path}: {e}")
                    if cleaned_desc_count > 0:
                        logger.debug(f"Cleaned up {cleaned_desc_count} description file(s) for expired alert {alert_id}")
            except Exception as e:
                logger.debug(f"Could not clean up description files (SkyDescribe may not be enabled): {e}")
            
            # Remove alert from state
            self.state_manager.remove_alert(self.state, alert_id)
            logger.debug(f"Removed expired alert: {alert_id}")

    async def _handle_all_clear(self) -> None:
        """Handle all-clear scenario (no active alerts)."""
        # Log all-clear event
        self.alert_logger.log_all_clear() if self.alert_logger else logger.info("All clear - no active weather alerts")
        
        if self.config.alerts.say_all_clear:
            await self._announce_all_clear()
        
        # Execute all-clear script
        if self.script_manager:
            script_success = await self.script_manager.execute_all_clear_script()
            if script_success:
                logger.info("All-clear script executed successfully")
            else:
                logger.warning("All-clear script failed")
        
        # Send PushOver all-clear notification if enabled
        if self.config.pushover.enabled and self.config.pushover.api_token and self.config.pushover.user_key:
            try:
                from ..notifications.pushover import PushOverNotifier, PushOverConfig
                pushover_config = PushOverConfig(
                    api_token=self.config.pushover.api_token,
                    user_key=self.config.pushover.user_key,
                    enabled=True,
                    priority=self.config.pushover.priority,
                    sound=self.config.pushover.sound,
                    timeout_seconds=self.config.pushover.timeout_seconds,
                    retry_count=self.config.pushover.retry_count,
                    retry_delay_seconds=self.config.pushover.retry_delay_seconds
                )
                async with PushOverNotifier(pushover_config) as pushover:
                    county_names = [county.name for county in self.config.counties]
                    result = await pushover.send_all_clear(county_names)
                    if result.get("success", False):
                        logger.info("PushOver all-clear notification sent")
                    else:
                        logger.warning(f"PushOver all-clear notification failed: {result.get('error', 'Unknown error')}")
            except Exception as e:
                logger.error(f"Failed to send PushOver all-clear notification: {e}")
        
        self.state_manager.update_all_clear_time(self.state)
        
        # Clear active alerts
        self.state_manager.update_active_alerts(self.state, [])

    def _should_announce_alert(self, alert: WeatherAlert) -> bool:
        """
        Determine if an alert should be announced.

        Args:
            alert: Alert to check

        Returns:
            True if alert should be announced
        """
        # Check if alerts are enabled
        if not self.config.alerts.say_alert:
            return False
        
        # Check if this event type is blocked from announcement
        for blocked_event in self.config.filtering.say_alert_blocked:
            if self._matches_pattern(alert.event, blocked_event):
                logger.debug(f"Alert {alert.event} blocked from announcement by pattern: {blocked_event}")
                return False
        
        return True


    def _matches_pattern(self, text: str, pattern: str) -> bool:
        """
        Check if text matches a glob pattern.

        Args:
            text: Text to match
            pattern: Glob pattern

        Returns:
            True if text matches pattern
        """
        import fnmatch
        return fnmatch.fnmatch(text, pattern)

    def _get_county_audio_files(self, county_codes: List[str]) -> List[str]:
        """
        Get county audio file names for given county codes.

        Args:
            county_codes: List of county codes

        Returns:
            List of county audio file names (filtered to only those configured and enabled)
        """
        county_audio_files = []
        county_code_map = {county.code: county for county in self.config.counties}
        
        logger.debug(f"Getting county audio files for codes: {county_codes}")
        for county_code in county_codes:
            if county_code in county_code_map:
                county_config = county_code_map[county_code]
                logger.debug(f"County {county_code}: enabled={county_config.enabled}, audio_file={county_config.audio_file}")
                # Only include county audio if the county is enabled and has an audio file
                if county_config.enabled and county_config.audio_file:
                    county_audio_files.append(county_config.audio_file)
                    logger.debug(f"Added county audio file for {county_code}: {county_config.audio_file}")
            else:
                logger.debug(f"County code {county_code} not found in configuration")
        
        logger.debug(f"Returning {len(county_audio_files)} county audio files: {county_audio_files}")
        return county_audio_files

    def _has_multiple_instances(self, alert: WeatherAlert) -> bool:
        """
        Check if there are multiple instances of the same alert type.

        Args:
            alert: Alert to check

        Returns:
            True if multiple instances exist
        """
        # Check current alerts in state for same event type
        alerts_by_event = {}
        for alert_data in self.state.get('last_alerts', {}).values():
            event = alert_data.get('event')
            if event == alert.event:
                if event not in alerts_by_event:
                    alerts_by_event[event] = []
                alerts_by_event[event].append(alert_data)
        
        # Also check active alerts
        current_alerts = self.state.get('active_alerts', [])
        for alert_id in current_alerts:
            if alert_id in self.state.get('last_alerts', {}):
                alert_data = self.state['last_alerts'][alert_id]
                event = alert_data.get('event')
                if event == alert.event and alert_id != alert.id:
                    if event not in alerts_by_event:
                        alerts_by_event[event] = []
                    alerts_by_event[event].append(alert_data)
        
        # Check if we have multiple unique instances (different descriptions or end times)
        if alert.event in alerts_by_event:
            instances = alerts_by_event[alert.event]
            descriptions = {inst.get('description', '') for inst in instances}
            expires = {inst.get('expires', '') for inst in instances}
            
            # Multiple instances if different descriptions or end times
            return len(descriptions) > 1 or len(expires) > 1
        
        return False

    async def _handle_alerts_with_changes(self, alerts: List[WeatherAlert]) -> None:
        """
        Handle alerts where county lists have changed (SayAlertsChanged).

        Args:
            alerts: List of alerts to announce
        """
        logger.info(f"Processing {len(alerts)} alerts with county changes")
        
        for alert in alerts:
            if self._should_announce_alert(alert):
                announcement_nodes = await self._announce_alert(alert)
                if announcement_nodes:
                    self.state_manager.mark_alert_announced(self.state, alert.id)

    async def _announce_alert(self, alert: WeatherAlert) -> List[int]:
        """
        Announce an alert using TTS and Asterisk.
        
        Works for both NWS alerts and test/injected alerts.

        Args:
            alert: Alert to announce (can be NWS or test alert)
            
        Returns:
            List of node numbers where announcement was successful (empty if failed)
        """
        alert_type = "TEST" if alert.status == AlertStatus.TEST else "NWS"
        logger.info(f"Announcing {alert_type} alert: {alert.event} - {alert.area_desc}")
        logger.debug(f"Alert description: {alert.description[:100]}..." if alert.description and len(alert.description) > 100 else f"Alert description: {alert.description}")
        
        if not self.audio_manager:
            logger.warning("Audio manager not available - skipping announcement")
            return []
        
        if not self.asterisk_manager:
            logger.warning("Asterisk manager not available - skipping announcement")
            return []
        
        if not self.config.asterisk.enabled:
            logger.warning("Asterisk integration disabled - skipping announcement")
            return []
        
        if not self.config.asterisk.nodes:
            logger.warning("No Asterisk nodes configured - skipping announcement")
            return []
        
        try:
            # Get county audio files if enabled
            county_audio_files = None
            if self.config.alerts.with_county_names and alert.county_codes:
                county_audio_files = self._get_county_audio_files(alert.county_codes)
            
            # Check for "with multiples" - multiple instances of same alert type
            # Note: We'll check against current alerts from the poll cycle
            with_multiples = False
            if self.config.alerts.with_multiples:
                # Get current alerts from state for comparison
                current_alert_objs = []
                for alert_id in self.state.get('active_alerts', []):
                    if alert_id in self.state.get('last_alerts', {}):
                        alert_data = self.state['last_alerts'][alert_id]
                        # Reconstruct minimal alert for comparison
                        from datetime import datetime
                        current_alert_objs.append({
                            'event': alert_data.get('event'),
                            'description': alert_data.get('description', ''),
                            'expires': alert_data.get('expires', '')
                        })
                # Add current alert to the list
                current_alert_objs.append({
                    'event': alert.event,
                    'description': alert.description,
                    'expires': alert.expires.isoformat()
                })
                
                # Check for multiple unique instances
                same_event = [a for a in current_alert_objs if a['event'] == alert.event]
                if len(same_event) > 1:
                    descriptions = {a['description'] for a in same_event}
                    expires = {a['expires'] for a in same_event}
                    with_multiples = len(descriptions) > 1 or len(expires) > 1
            
            # Generate TTS audio for the alert
            audio_path = self.audio_manager.generate_alert_audio(
                alert,
                suffix_file=self.config.alerts.say_alert_suffix,
                county_audio_files=county_audio_files,
                with_multiples=with_multiples
            )
            if not audio_path:
                logger.error(f"Failed to generate audio for alert: {alert.event}")
                return []
            
            logger.info(f"Generated alert audio: {audio_path}")
            
            # Verify file exists and is readable before attempting playback
            if not audio_path.exists():
                logger.error(f"Audio file does not exist: {audio_path}")
                return []
            
            if audio_path.stat().st_size == 0:
                logger.error(f"Audio file is empty: {audio_path}")
                return []
            
            # Play audio on all configured Asterisk nodes
            successful_nodes = await self.asterisk_manager.play_audio_on_all_nodes(audio_path)
            
            if successful_nodes:
                logger.info(f"Alert audio playing on {len(successful_nodes)} nodes: {successful_nodes}")
                
                # Add audio delay if configured
                if self.config.asterisk.audio_delay > 0:
                    await asyncio.sleep(self.config.asterisk.audio_delay / 1000.0)
                return successful_nodes
            else:
                logger.error(f"Failed to play alert audio on any nodes: {alert.event}")
                return []
            
        except Exception as e:
            logger.error(f"Error announcing alert {alert.event}: {e}", exc_info=True)
            return []

    async def _announce_all_clear(self) -> None:
        """Announce all-clear message using TTS and Asterisk."""
        logger.info("Announcing all-clear message")
        
        if not self.audio_manager:
            logger.warning("Audio manager not available - skipping all-clear announcement")
            return
        
        if not self.asterisk_manager:
            logger.warning("Asterisk manager not available - skipping all-clear announcement")
            return
        
        try:
            # Generate TTS audio for all-clear message
            audio_path = self.audio_manager.generate_all_clear_audio(
                suffix_file=self.config.alerts.say_all_clear_suffix
            )
            if not audio_path:
                logger.error("Failed to generate all-clear audio")
                return
            
            logger.info(f"Generated all-clear audio: {audio_path}")
            
            # Play audio on all configured Asterisk nodes
            successful_nodes = await self.asterisk_manager.play_audio_on_all_nodes(audio_path)
            
            if successful_nodes:
                logger.info(f"All-clear audio playing on {len(successful_nodes)} nodes: {successful_nodes}")
                
                # Add audio delay if configured
                if self.config.asterisk.audio_delay > 0:
                    await asyncio.sleep(self.config.asterisk.audio_delay / 1000.0)
            else:
                logger.error("Failed to play all-clear audio on any nodes")
            
        except Exception as e:
            logger.error(f"Error announcing all-clear: {e}", exc_info=True)


    def get_status(self) -> Dict[str, Any]:
        """
        Get current application status.

        Returns:
            Status dictionary
        """
        # Check if application is fully initialized
        initialized = hasattr(self, 'state') and self.state is not None
        
        status = {
            'running': self.running,
            'initialized': initialized,
            'nws_connected': self.nws_client is not None,
            'audio_available': self.audio_manager is not None,
            'asterisk_available': self.asterisk_manager is not None,
            'asterisk_enabled': self.config.asterisk.enabled,
            'asterisk_nodes': self.config.asterisk.nodes,
            'scripts_available': self.script_manager is not None,
            'scripts_enabled': self.config.scripts.enabled,
            'database_available': self.database_manager is not None,
            'database_enabled': self.config.database.enabled,
            'processing_pipeline_available': self.alert_pipeline is not None,
            'filter_chain_available': self.filter_chain is not None,
            'deduplicator_available': self.deduplicator is not None,
            'prioritizer_available': self.prioritizer is not None,
            'validator_available': self.validator is not None,
            'workflow_engine_available': self.workflow_engine is not None,
            'analytics_available': self.analytics is not None,
            'uptime_seconds': (datetime.now(timezone.utc) - self._start_time).total_seconds(),
        }
        
        # Add state-dependent information only if initialized
        if initialized:
            status.update({
                'last_poll': self.state.get('last_poll'),
                'active_alerts': len(self.state.get('active_alerts', [])),
                'total_alerts': len(self.state.get('last_alerts', {})),
                'last_all_clear': self.state.get('last_all_clear'),
            })
        else:
            status.update({
                'last_poll': None,
                'active_alerts': 0,
                'total_alerts': 0,
                'last_all_clear': None,
            })
        
        # Add script manager status if available
        if self.script_manager:
            try:
                status['script_status'] = self.script_manager.get_script_status()
            except Exception as e:
                logger.error(f"Failed to get script status: {e}")
                status['script_status'] = {}
        
        # Add health summary if available
        if self.health_monitor:
            try:
                status['health_summary'] = self.health_monitor.get_health_summary()
            except Exception as e:
                logger.error(f"Failed to get health summary: {e}")
                status['health_summary'] = {}
        
        # Add processing pipeline statistics if available
        if self.alert_pipeline:
            try:
                status['processing_stats'] = self.alert_pipeline.get_processing_stats()
            except Exception as e:
                logger.error(f"Failed to get processing stats: {e}")
                status['processing_stats'] = {}
        
        # Add analytics summary if available
        if self.analytics:
            try:
                performance_metrics = self.analytics.get_performance_metrics()
                status['performance_metrics'] = {
                    'total_processed': performance_metrics.total_processed,
                    'successful_processing': performance_metrics.successful_processing,
                    'failed_processing': performance_metrics.failed_processing,
                    'average_processing_time_ms': performance_metrics.average_processing_time_ms,
                    'throughput_per_hour': performance_metrics.throughput_per_hour,
                    'error_rate': performance_metrics.error_rate,
                    'uptime_percentage': performance_metrics.uptime_percentage
                }
            except Exception as e:
                logger.error(f"Failed to get performance metrics: {e}")
                status['performance_metrics'] = {}
        
        return status