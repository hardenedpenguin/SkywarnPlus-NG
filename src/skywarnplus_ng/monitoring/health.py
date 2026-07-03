"""
Health monitoring and status reporting for SkywarnPlus-NG.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

from .. import __version__ as APP_VERSION
from ..core.config import AppConfig
from ..api.nws_client import NWSClient
from ..audio.manager import AudioManager
from ..asterisk.manager import AsteriskManager
from ..utils.script_manager import ScriptManager


class ComponentStatus(str, Enum):
    """Status of a system component."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Health status of a component."""

    name: str
    status: ComponentStatus
    message: str
    last_check: datetime
    response_time_ms: Optional[float] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class HealthStatus:
    """Overall system health status."""

    overall_status: ComponentStatus
    timestamp: datetime
    uptime_seconds: float
    version: str
    components: List[ComponentHealth]
    metrics: Dict[str, Any]


def rollup_overall_status(statuses: List[ComponentStatus]) -> ComponentStatus:
    """Derive overall status from components, ignoring non-applicable UNKNOWN checks."""
    actionable = [status for status in statuses if status != ComponentStatus.UNKNOWN]
    if not actionable:
        return ComponentStatus.UNKNOWN
    if ComponentStatus.UNHEALTHY in actionable:
        return ComponentStatus.UNHEALTHY
    if ComponentStatus.DEGRADED in actionable:
        return ComponentStatus.DEGRADED
    if all(status == ComponentStatus.HEALTHY for status in actionable):
        return ComponentStatus.HEALTHY
    return ComponentStatus.UNKNOWN


class HealthMonitor:
    """Monitors system health and provides status reporting."""

    def __init__(self, config: AppConfig, start_time: datetime):
        """
        Initialize health monitor.

        Args:
            config: Application configuration
            start_time: Application start time
        """
        self.config = config
        self.start_time = start_time
        self.logger = logging.getLogger(__name__)

        # Component references (set during initialization)
        self.nws_client: Optional[NWSClient] = None
        self.nhc_service = None
        self.earthquake_service = None
        self.wildfire_service = None
        self.mobile_county_service = None
        self.audio_manager: Optional[AudioManager] = None
        self.asterisk_manager: Optional[AsteriskManager] = None
        self.script_manager: Optional[ScriptManager] = None
        self.database_manager = None

        # Health check history
        self._health_history: List[HealthStatus] = []
        self._max_history = 100

    def set_components(
        self,
        nws_client: Optional[NWSClient] = None,
        nhc_service=None,
        earthquake_service=None,
        wildfire_service=None,
        mobile_county_service=None,
        audio_manager: Optional[AudioManager] = None,
        asterisk_manager: Optional[AsteriskManager] = None,
        script_manager: Optional[ScriptManager] = None,
        database_manager=None,
    ) -> None:
        """Set component references for health checking."""
        self.nws_client = nws_client
        self.nhc_service = nhc_service
        self.earthquake_service = earthquake_service
        self.wildfire_service = wildfire_service
        self.mobile_county_service = mobile_county_service
        self.audio_manager = audio_manager
        self.asterisk_manager = asterisk_manager
        self.script_manager = script_manager
        self.database_manager = database_manager

    async def check_nws_health(self) -> ComponentHealth:
        """Check NWS API health."""
        start_time = datetime.now(timezone.utc)

        if not self.nws_client:
            return ComponentHealth(
                name="nws_api",
                status=ComponentStatus.UNKNOWN,
                message="NWS client not initialized",
                last_check=start_time,
            )

        try:
            # Test connection with timeout
            connected = await asyncio.wait_for(self.nws_client.test_connection(), timeout=10.0)

            response_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            if connected:
                return ComponentHealth(
                    name="nws_api",
                    status=ComponentStatus.HEALTHY,
                    message="NWS API connection successful",
                    last_check=start_time,
                    response_time_ms=response_time,
                )
            else:
                return ComponentHealth(
                    name="nws_api",
                    status=ComponentStatus.UNHEALTHY,
                    message="NWS API connection failed",
                    last_check=start_time,
                    response_time_ms=response_time,
                )

        except asyncio.TimeoutError:
            return ComponentHealth(
                name="nws_api",
                status=ComponentStatus.UNHEALTHY,
                message="NWS API connection timeout",
                last_check=start_time,
                response_time_ms=10000.0,
            )
        except Exception as e:
            return ComponentHealth(
                name="nws_api",
                status=ComponentStatus.UNHEALTHY,
                message=f"NWS API error: {e}",
                last_check=start_time,
            )

    async def check_audio_health(self) -> ComponentHealth:
        """Check audio system health."""
        start_time = datetime.now(timezone.utc)

        if not self.audio_manager:
            return ComponentHealth(
                name="audio_system",
                status=ComponentStatus.UNKNOWN,
                message="Audio manager not initialized",
                last_check=start_time,
            )

        try:
            # Check if TTS engine is available
            if hasattr(self.audio_manager, "tts_engine") and self.audio_manager.tts_engine:
                if self.audio_manager.tts_engine.is_available():
                    return ComponentHealth(
                        name="audio_system",
                        status=ComponentStatus.HEALTHY,
                        message="Audio system operational",
                        last_check=start_time,
                    )
                else:
                    return ComponentHealth(
                        name="audio_system",
                        status=ComponentStatus.DEGRADED,
                        message="TTS engine not available",
                        last_check=start_time,
                    )
            else:
                return ComponentHealth(
                    name="audio_system",
                    status=ComponentStatus.DEGRADED,
                    message="TTS engine not configured",
                    last_check=start_time,
                )

        except Exception as e:
            return ComponentHealth(
                name="audio_system",
                status=ComponentStatus.UNHEALTHY,
                message=f"Audio system error: {e}",
                last_check=start_time,
            )

    async def check_asterisk_health(self) -> ComponentHealth:
        """Check Asterisk system health."""
        start_time = datetime.now(timezone.utc)

        if not self.asterisk_manager:
            return ComponentHealth(
                name="asterisk_system",
                status=ComponentStatus.UNKNOWN,
                message="Asterisk manager not initialized",
                last_check=start_time,
            )

        if not self.config.asterisk.enabled:
            return ComponentHealth(
                name="asterisk_system",
                status=ComponentStatus.UNKNOWN,
                message="Asterisk integration disabled",
                last_check=start_time,
            )

        try:
            # Test Asterisk connection
            connected = await asyncio.wait_for(self.asterisk_manager.test_connection(), timeout=5.0)

            response_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            if connected:
                return ComponentHealth(
                    name="asterisk_system",
                    status=ComponentStatus.HEALTHY,
                    message="Asterisk connection successful",
                    last_check=start_time,
                    response_time_ms=response_time,
                    details={
                        "nodes_configured": len(self.config.asterisk.nodes),
                        "nodes": self.config.asterisk.nodes,
                    },
                )
            else:
                return ComponentHealth(
                    name="asterisk_system",
                    status=ComponentStatus.UNHEALTHY,
                    message="Asterisk connection failed",
                    last_check=start_time,
                    response_time_ms=response_time,
                )

        except asyncio.TimeoutError:
            return ComponentHealth(
                name="asterisk_system",
                status=ComponentStatus.UNHEALTHY,
                message="Asterisk connection timeout",
                last_check=start_time,
                response_time_ms=5000.0,
            )
        except Exception as e:
            return ComponentHealth(
                name="asterisk_system",
                status=ComponentStatus.UNHEALTHY,
                message=f"Asterisk error: {e}",
                last_check=start_time,
            )

    async def check_scripts_health(self) -> ComponentHealth:
        """Check script system health."""
        start_time = datetime.now(timezone.utc)

        if not self.script_manager:
            return ComponentHealth(
                name="script_system",
                status=ComponentStatus.UNKNOWN,
                message="Script manager not initialized",
                last_check=start_time,
            )

        if not self.config.scripts.enabled:
            return ComponentHealth(
                name="script_system",
                status=ComponentStatus.UNKNOWN,
                message="Script execution disabled",
                last_check=start_time,
            )

        try:
            # Get script status
            status = self.script_manager.get_script_status()

            return ComponentHealth(
                name="script_system",
                status=ComponentStatus.HEALTHY,
                message="Script system operational",
                last_check=start_time,
                details=status,
            )

        except Exception as e:
            return ComponentHealth(
                name="script_system",
                status=ComponentStatus.UNHEALTHY,
                message=f"Script system error: {e}",
                last_check=start_time,
            )

    async def check_database_health(self) -> ComponentHealth:
        """Check database system health."""
        start_time = datetime.now(timezone.utc)

        if not self.database_manager:
            return ComponentHealth(
                name="database_system",
                status=ComponentStatus.UNKNOWN,
                message="Database manager not initialized",
                last_check=start_time,
            )

        try:
            # Test database connection by getting stats
            stats = await self.database_manager.get_database_stats()

            # Check if we can query the database
            if stats and isinstance(stats, dict):
                return ComponentHealth(
                    name="database_system",
                    status=ComponentStatus.HEALTHY,
                    message="Database connection successful",
                    last_check=start_time,
                    details={
                        "total_alerts": stats.get("total_alerts", 0),
                        "total_analytics": stats.get("total_analytics", 0),
                        "database_size": stats.get("database_size", "unknown"),
                    },
                )
            else:
                return ComponentHealth(
                    name="database_system",
                    status=ComponentStatus.DEGRADED,
                    message="Database responding but stats unavailable",
                    last_check=start_time,
                )

        except Exception as e:
            return ComponentHealth(
                name="database_system",
                status=ComponentStatus.UNHEALTHY,
                message=f"Database health check failed: {str(e)}",
                last_check=start_time,
            )

    async def check_nhc_health(self, state: Optional[Dict[str, Any]] = None) -> ComponentHealth:
        """Check NHC feed and position health when cyclone monitoring is enabled."""
        start_time = datetime.now(timezone.utc)

        if not self.config.nhc.enabled:
            return ComponentHealth(
                name="nhc_api",
                status=ComponentStatus.UNKNOWN,
                message="NHC monitoring disabled",
                last_check=start_time,
            )

        if not self.nhc_service:
            return ComponentHealth(
                name="nhc_api",
                status=ComponentStatus.UNKNOWN,
                message="NHC service not initialized",
                last_check=start_time,
            )

        try:
            result = await asyncio.wait_for(
                self.nhc_service.check_health(state or {}),
                timeout=20.0,
            )
            response_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            details = result.get("details") or {}

            if result.get("ok"):
                return ComponentHealth(
                    name="nhc_api",
                    status=ComponentStatus.HEALTHY,
                    message=str(result.get("message") or "NHC feed OK"),
                    last_check=start_time,
                    response_time_ms=response_time,
                    details=details,
                )

            message = str(result.get("message") or "NHC health check failed")
            # Missing GPS position with gpsd enabled is degraded, not fully unhealthy
            if (
                self.config.geo_hazard_position.use_gps_position
                and self.config.gpsd.enabled
                and "GPS position" in message
            ):
                status = ComponentStatus.DEGRADED
            else:
                status = ComponentStatus.UNHEALTHY

            return ComponentHealth(
                name="nhc_api",
                status=status,
                message=message,
                last_check=start_time,
                response_time_ms=response_time,
                details=details,
            )
        except asyncio.TimeoutError:
            return ComponentHealth(
                name="nhc_api",
                status=ComponentStatus.UNHEALTHY,
                message="NHC health check timeout",
                last_check=start_time,
                response_time_ms=20000.0,
            )
        except Exception as e:
            return ComponentHealth(
                name="nhc_api",
                status=ComponentStatus.UNHEALTHY,
                message=f"NHC error: {e}",
                last_check=start_time,
            )

    async def _check_position_hazard_health(
        self,
        *,
        component_name: str,
        enabled: bool,
        service,
        use_gps_position: bool,
        state: Optional[Dict[str, Any]],
        disabled_message: str,
    ) -> ComponentHealth:
        start_time = datetime.now(timezone.utc)

        if not enabled:
            return ComponentHealth(
                name=component_name,
                status=ComponentStatus.UNKNOWN,
                message=disabled_message,
                last_check=start_time,
            )

        if not service:
            return ComponentHealth(
                name=component_name,
                status=ComponentStatus.UNKNOWN,
                message=f"{component_name} service not initialized",
                last_check=start_time,
            )

        try:
            result = await asyncio.wait_for(
                service.check_health(state or {}),
                timeout=20.0,
            )
            response_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            details = result.get("details") or {}

            if result.get("ok"):
                return ComponentHealth(
                    name=component_name,
                    status=ComponentStatus.HEALTHY,
                    message=str(result.get("message") or f"{component_name} OK"),
                    last_check=start_time,
                    response_time_ms=response_time,
                    details=details,
                )

            message = str(result.get("message") or f"{component_name} health check failed")
            if use_gps_position and self.config.gpsd.enabled and "GPS position" in message:
                status = ComponentStatus.DEGRADED
            elif (
                "No position available" in message and use_gps_position and self.config.gpsd.enabled
            ):
                status = ComponentStatus.DEGRADED
            else:
                status = ComponentStatus.UNHEALTHY

            return ComponentHealth(
                name=component_name,
                status=status,
                message=message,
                last_check=start_time,
                response_time_ms=response_time,
                details=details,
            )
        except asyncio.TimeoutError:
            return ComponentHealth(
                name=component_name,
                status=ComponentStatus.UNHEALTHY,
                message=f"{component_name} health check timeout",
                last_check=start_time,
                response_time_ms=20000.0,
            )
        except Exception as e:
            return ComponentHealth(
                name=component_name,
                status=ComponentStatus.UNHEALTHY,
                message=f"{component_name} error: {e}",
                last_check=start_time,
            )

    async def check_earthquake_health(
        self, state: Optional[Dict[str, Any]] = None
    ) -> ComponentHealth:
        """Check USGS earthquake feed and position health when enabled."""
        return await self._check_position_hazard_health(
            component_name="usgs_api",
            enabled=self.config.earthquake.enabled,
            service=self.earthquake_service,
            use_gps_position=self.config.geo_hazard_position.use_gps_position,
            state=state,
            disabled_message="USGS earthquake monitoring disabled",
        )

    async def check_wildfire_health(
        self, state: Optional[Dict[str, Any]] = None
    ) -> ComponentHealth:
        """Check WFIGS wildfire feed and position health when enabled."""
        return await self._check_position_hazard_health(
            component_name="wfigs_api",
            enabled=self.config.wildfire.enabled,
            service=self.wildfire_service,
            use_gps_position=self.config.geo_hazard_position.use_gps_position,
            state=state,
            disabled_message="Wildfire monitoring disabled",
        )

    async def get_health_status(self, state: Optional[Dict[str, Any]] = None) -> HealthStatus:
        """Get comprehensive health status."""
        start_time = datetime.now(timezone.utc)

        # Check all components concurrently
        check_coroutines = [
            self.check_nws_health(),
            self.check_audio_health(),
            self.check_asterisk_health(),
            self.check_scripts_health(),
            self.check_database_health(),
        ]
        if self.config.nhc.enabled:
            check_coroutines.append(self.check_nhc_health(state))
        if self.config.earthquake.enabled:
            check_coroutines.append(self.check_earthquake_health(state))
        if self.config.wildfire.enabled:
            check_coroutines.append(self.check_wildfire_health(state))

        health_checks = await asyncio.gather(
            *check_coroutines,
            return_exceptions=True,
        )

        # Process results
        components = []
        for check in health_checks:
            if isinstance(check, Exception):
                components.append(
                    ComponentHealth(
                        name="unknown",
                        status=ComponentStatus.UNHEALTHY,
                        message=f"Health check error: {check}",
                        last_check=start_time,
                    )
                )
            else:
                components.append(check)

        # Determine overall status (disabled/uninitialized components are UNKNOWN and ignored)
        overall_status = rollup_overall_status([comp.status for comp in components])

        # Calculate uptime
        uptime = (start_time - self.start_time).total_seconds()

        # Collect metrics
        metrics = {
            "poll_interval": self.config.poll_interval,
            "counties_configured": len([c for c in self.config.counties if c.enabled]),
            "asterisk_enabled": self.config.asterisk.enabled,
            "scripts_enabled": self.config.scripts.enabled,
            "audio_enabled": True,  # Always enabled if audio_manager exists
            "nhc_enabled": self.config.nhc.enabled,
            "earthquake_enabled": self.config.earthquake.enabled,
            "wildfire_enabled": self.config.wildfire.enabled,
            "gpsd_enabled": self.config.gpsd.enabled,
        }

        health_status = HealthStatus(
            overall_status=overall_status,
            timestamp=start_time,
            uptime_seconds=uptime,
            version=APP_VERSION,
            components=components,
            metrics=metrics,
        )

        # Store in history
        self._health_history.append(health_status)
        if len(self._health_history) > self._max_history:
            self._health_history = self._health_history[-self._max_history :]

        return health_status

    def get_health_history(self, limit: int = 10) -> List[HealthStatus]:
        """Get health check history."""
        return self._health_history[-limit:]

    def get_health_summary(self) -> Dict[str, Any]:
        """Get a summary of recent health status."""
        if not self._health_history:
            return {"status": "unknown", "message": "No health checks performed"}

        recent = self._health_history[-1]
        return {
            "status": recent.overall_status.value,
            "timestamp": recent.timestamp.isoformat(),
            "uptime_seconds": recent.uptime_seconds,
            "components": {
                comp.name: {
                    "status": comp.status.value,
                    "message": comp.message,
                    "response_time_ms": comp.response_time_ms,
                }
                for comp in recent.components
            },
        }
