"""
Database manager for SkywarnPlus-NG.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from .models import (
    Base, AlertRecord, MetricRecord, HealthCheckRecord, 
    ScriptExecutionRecord, ConfigurationRecord, AlertAnalytics
)
from ..core.models import WeatherAlert
from ..core.config import AppConfig

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Database operation error."""

    pass


class DatabaseManager:
    """Manages database operations for SkywarnPlus-NG."""

    def __init__(self, config: AppConfig):
        """
        Initialize database manager.

        Args:
            config: Application configuration
        """
        self.config = config
        self.engine = None
        self.async_session_factory = None
        self._is_initialized = False

    async def initialize(self, database_url: Optional[str] = None) -> None:
        """
        Initialize database connection and create tables.

        Args:
            database_url: Database URL (defaults to SQLite in data_dir)
        """
        if self._is_initialized:
            return

        try:
            # Default to SQLite if no URL provided
            if not database_url:
                db_path = self.config.data_dir / "skywarnplus_ng.db"
                database_url = f"sqlite+aiosqlite:///{db_path}"

            # Create async engine
            self.engine = create_async_engine(
                database_url,
                echo=False,  # Set to True for SQL debugging
                pool_pre_ping=True,
                pool_recycle=3600,  # Recycle connections every hour
            )

            # Create session factory
            self.async_session_factory = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )

            # Create tables
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            self._is_initialized = True
            logger.info(f"Database initialized: {database_url}")

        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise DatabaseError(f"Database initialization failed: {e}") from e

    async def close(self) -> None:
        """Close database connections."""
        if self.engine:
            await self.engine.dispose()
            self._is_initialized = False
            logger.info("Database connections closed")

    async def get_session(self) -> AsyncSession:
        """Get a database session."""
        if not self._is_initialized:
            raise DatabaseError("Database not initialized")
        return self.async_session_factory()

    async def store_alert(self, alert: WeatherAlert, announced: bool = False, 
                         script_executed: bool = False, announcement_nodes: List[int] = None) -> None:
        """
        Store a weather alert in the database.

        Args:
            alert: Weather alert to store
            announced: Whether the alert was announced
            script_executed: Whether a script was executed
            announcement_nodes: List of nodes that announced this alert
        """
        try:
            async with await self.get_session() as session:
                # Check if alert already exists
                existing = await session.get(AlertRecord, alert.id)
                if existing:
                    # Update existing record
                    existing.announced = announced
                    existing.script_executed = script_executed
                    existing.announcement_nodes = announcement_nodes or []
                    existing.processed_at = datetime.now(timezone.utc)
                else:
                    # Create new record
                    alert_record = AlertRecord(
                        id=alert.id,
                        event=alert.event,
                        headline=alert.headline,
                        description=alert.description,
                        instruction=alert.instruction,
                        severity=alert.severity.value,
                        urgency=alert.urgency.value,
                        certainty=alert.certainty.value,
                        status=alert.status.value,
                        category=alert.category.value,
                        sent_time=alert.sent,
                        effective_time=alert.effective,
                        onset_time=alert.onset,
                        expires_time=alert.expires,
                        ends_time=alert.ends,
                        area_desc=alert.area_desc,
                        geocode=alert.geocode,
                        county_codes=alert.county_codes,
                        sender=alert.sender,
                        sender_name=alert.sender_name,
                        announced=announced,
                        script_executed=script_executed,
                        announcement_nodes=announcement_nodes or [],
                        metadata={
                            "original_alert": alert.model_dump()
                        }
                    )
                    session.add(alert_record)

                await session.commit()
                logger.debug(f"Stored alert: {alert.id}")

        except SQLAlchemyError as e:
            logger.error(f"Failed to store alert {alert.id}: {e}")
            raise DatabaseError(f"Failed to store alert: {e}") from e

    async def get_alert(self, alert_id: str) -> Optional[AlertRecord]:
        """
        Get an alert by ID.

        Args:
            alert_id: Alert ID

        Returns:
            Alert record or None if not found
        """
        try:
            async with await self.get_session() as session:
                return await session.get(AlertRecord, alert_id)
        except SQLAlchemyError as e:
            logger.error(f"Failed to get alert {alert_id}: {e}")
            raise DatabaseError(f"Failed to get alert: {e}") from e

    async def get_recent_alerts(self, limit: int = 100, hours: int = 24) -> List[AlertRecord]:
        """
        Get recent alerts.

        Args:
            limit: Maximum number of alerts to return
            hours: Number of hours to look back

        Returns:
            List of recent alert records
        """
        try:
            async with await self.get_session() as session:
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
                
                result = await session.execute(
                    text("""
                        SELECT * FROM alerts 
                        WHERE processed_at >= :cutoff_time 
                        ORDER BY processed_at DESC 
                        LIMIT :limit
                    """),
                    {"cutoff_time": cutoff_time, "limit": limit}
                )
                
                return result.fetchall()
        except SQLAlchemyError as e:
            logger.error(f"Failed to get recent alerts: {e}")
            raise DatabaseError(f"Failed to get recent alerts: {e}") from e

    async def store_metric(self, name: str, value: float, unit: str = None, 
                          metadata: Dict[str, Any] = None) -> None:
        """
        Store a metric.

        Args:
            name: Metric name
            value: Metric value
            unit: Metric unit
            metadata: Additional metadata
        """
        try:
            async with await self.get_session() as session:
                metric_record = MetricRecord(
                    metric_name=name,
                    metric_value=value,
                    metric_unit=unit,
                    metadata=metadata or {}
                )
                session.add(metric_record)
                await session.commit()
                logger.debug(f"Stored metric: {name} = {value}")

        except SQLAlchemyError as e:
            logger.error(f"Failed to store metric {name}: {e}")
            raise DatabaseError(f"Failed to store metric: {e}") from e

    async def store_health_check(self, overall_status: str, uptime_seconds: float,
                                components: List[Dict[str, Any]], metadata: Dict[str, Any] = None) -> None:
        """
        Store a health check result.

        Args:
            overall_status: Overall system status
            uptime_seconds: System uptime in seconds
            components: List of component statuses
            metadata: Additional metadata
        """
        try:
            async with await self.get_session() as session:
                health_record = HealthCheckRecord(
                    overall_status=overall_status,
                    uptime_seconds=uptime_seconds,
                    components=components,
                    metadata=metadata or {}
                )
                session.add(health_record)
                await session.commit()
                logger.debug(f"Stored health check: {overall_status}")

        except SQLAlchemyError as e:
            logger.error(f"Failed to store health check: {e}")
            raise DatabaseError(f"Failed to store health check: {e}") from e

    async def store_script_execution(self, script_type: str, command: str, args: List[str],
                                   success: bool, return_code: int = None, 
                                   execution_time_ms: float = None, error_message: str = None,
                                   output: str = None, alert_id: str = None, 
                                   alert_event: str = None, metadata: Dict[str, Any] = None) -> None:
        """
        Store a script execution record.

        Args:
            script_type: Type of script ('alert' or 'all_clear')
            command: Command executed
            args: Command arguments
            success: Whether execution was successful
            return_code: Process return code
            execution_time_ms: Execution time in milliseconds
            error_message: Error message if failed
            output: Script output
            alert_id: Associated alert ID
            alert_event: Associated alert event
            metadata: Additional metadata
        """
        try:
            async with await self.get_session() as session:
                script_record = ScriptExecutionRecord(
                    script_type=script_type,
                    command=command,
                    args=args,
                    success=success,
                    return_code=return_code,
                    execution_time_ms=execution_time_ms,
                    error_message=error_message,
                    output=output,
                    alert_id=alert_id,
                    alert_event=alert_event,
                    completed_at=datetime.now(timezone.utc),
                    metadata=metadata or {}
                )
                session.add(script_record)
                await session.commit()
                logger.debug(f"Stored script execution: {command}")

        except SQLAlchemyError as e:
            logger.error(f"Failed to store script execution: {e}")
            raise DatabaseError(f"Failed to store script execution: {e}") from e

    async def get_alert_statistics(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get alert statistics for the specified time period.

        Args:
            hours: Number of hours to analyze

        Returns:
            Dictionary with alert statistics
        """
        try:
            async with await self.get_session() as session:
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
                
                # Get total alerts
                total_result = await session.execute(
                    text("SELECT COUNT(*) as total FROM alerts WHERE processed_at >= :cutoff_time"),
                    {"cutoff_time": cutoff_time}
                )
                total_alerts = total_result.scalar()

                # Get alerts by severity
                severity_result = await session.execute(
                    text("""
                        SELECT severity, COUNT(*) as count 
                        FROM alerts 
                        WHERE processed_at >= :cutoff_time 
                        GROUP BY severity
                    """),
                    {"cutoff_time": cutoff_time}
                )
                alerts_by_severity = dict(severity_result.fetchall())

                # Get alerts by event type
                event_result = await session.execute(
                    text("""
                        SELECT event, COUNT(*) as count 
                        FROM alerts 
                        WHERE processed_at >= :cutoff_time 
                        GROUP BY event
                        ORDER BY count DESC
                        LIMIT 10
                    """),
                    {"cutoff_time": cutoff_time}
                )
                alerts_by_event = dict(event_result.fetchall())

                # Get announcement statistics
                announcement_result = await session.execute(
                    text("""
                        SELECT 
                            COUNT(*) as total_announced,
                            COUNT(CASE WHEN announced = 1 THEN 1 END) as announced_count
                        FROM alerts 
                        WHERE processed_at >= :cutoff_time
                    """),
                    {"cutoff_time": cutoff_time}
                )
                announcement_stats = announcement_result.fetchone()

                return {
                    "period_hours": hours,
                    "total_alerts": total_alerts,
                    "alerts_by_severity": alerts_by_severity,
                    "alerts_by_event": alerts_by_event,
                    "announcement_stats": {
                        "total": announcement_stats[0],
                        "announced": announcement_stats[1]
                    }
                }

        except SQLAlchemyError as e:
            logger.error(f"Failed to get alert statistics: {e}")
            raise DatabaseError(f"Failed to get alert statistics: {e}") from e

    async def cleanup_old_data(self, days: int = 30) -> Dict[str, int]:
        """
        Clean up old data from the database.

        Args:
            days: Number of days of data to keep

        Returns:
            Dictionary with cleanup statistics
        """
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)
            cleanup_stats = {}

            async with await self.get_session() as session:
                # Clean up old alerts
                alert_result = await session.execute(
                    text("DELETE FROM alerts WHERE processed_at < :cutoff_time"),
                    {"cutoff_time": cutoff_time}
                )
                cleanup_stats["alerts_deleted"] = alert_result.rowcount

                # Clean up old metrics
                metric_result = await session.execute(
                    text("DELETE FROM metrics WHERE timestamp < :cutoff_time"),
                    {"cutoff_time": cutoff_time}
                )
                cleanup_stats["metrics_deleted"] = metric_result.rowcount

                # Clean up old health checks
                health_result = await session.execute(
                    text("DELETE FROM health_checks WHERE timestamp < :cutoff_time"),
                    {"cutoff_time": cutoff_time}
                )
                cleanup_stats["health_checks_deleted"] = health_result.rowcount

                # Clean up old script executions
                script_result = await session.execute(
                    text("DELETE FROM script_executions WHERE started_at < :cutoff_time"),
                    {"cutoff_time": cutoff_time}
                )
                cleanup_stats["script_executions_deleted"] = script_result.rowcount

                await session.commit()
                logger.info(f"Cleaned up old data: {cleanup_stats}")

            return cleanup_stats

        except SQLAlchemyError as e:
            logger.error(f"Failed to cleanup old data: {e}")
            raise DatabaseError(f"Failed to cleanup old data: {e}") from e

    async def optimize_database(self) -> Dict[str, Any]:
        """
        Optimize the database by running VACUUM and ANALYZE operations.
        
        Returns:
            Dictionary with optimization results
        """
        try:
            optimization_stats = {}
            
            async with await self.get_session() as session:
                # Get database size before optimization
                if "sqlite" in str(self.engine.url):
                    size_before_result = await session.execute(
                        text("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
                    )
                    size_before = size_before_result.scalar()
                    optimization_stats["size_before_bytes"] = size_before
                    
                    # Run VACUUM to reclaim space and defragment
                    await session.execute(text("VACUUM"))
                    
                    # Run ANALYZE to update query planner statistics
                    await session.execute(text("ANALYZE"))
                    
                    # Get database size after optimization
                    size_after_result = await session.execute(
                        text("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
                    )
                    size_after = size_after_result.scalar()
                    optimization_stats["size_after_bytes"] = size_after
                    optimization_stats["space_saved_bytes"] = size_before - size_after
                    optimization_stats["space_saved_percentage"] = ((size_before - size_after) / size_before * 100) if size_before > 0 else 0
                else:
                    # For non-SQLite databases, just run ANALYZE
                    await session.execute(text("ANALYZE"))
                    optimization_stats["operation"] = "ANALYZE completed"
                
                await session.commit()
                logger.info(f"Database optimization completed: {optimization_stats}")
                
            return optimization_stats
            
        except SQLAlchemyError as e:
            logger.error(f"Failed to optimize database: {e}")
            raise DatabaseError(f"Failed to optimize database: {e}") from e

    async def get_database_stats(self) -> Dict[str, Any]:
        """
        Get database statistics.

        Returns:
            Dictionary with database statistics
        """
        try:
            async with await self.get_session() as session:
                stats = {}

                # Get table counts
                tables = ["alerts", "metrics", "health_checks", "script_executions", "configurations"]
                for table in tables:
                    result = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    stats[f"{table}_count"] = result.scalar()

                # Get database size (SQLite specific)
                if "sqlite" in str(self.engine.url):
                    size_result = await session.execute(
                        text("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
                    )
                    stats["database_size_bytes"] = size_result.scalar()

                return stats

        except SQLAlchemyError as e:
            logger.error(f"Failed to get database stats: {e}")
            raise DatabaseError(f"Failed to get database stats: {e}") from e

    async def backup_database(self, backup_path: Optional[Path] = None) -> Path:
        """
        Create a backup of the database.
        
        Args:
            backup_path: Optional path for backup file (defaults to data_dir/backups/)
            
        Returns:
            Path to the backup file
        """
        try:
            import shutil
            from datetime import datetime
            
            # Determine backup path
            if not backup_path:
                backup_dir = self.config.data_dir / "backups"
                backup_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                backup_path = backup_dir / f"skywarnplus_ng_backup_{timestamp}.db"
            
            # Get the database file path
            if "sqlite" in str(self.engine.url):
                # Extract file path from SQLite URL
                db_url = str(self.engine.url)
                # Handle both sqlite:/// and sqlite+aiosqlite:/// URLs
                db_path = db_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
                db_file = Path(db_path)
                
                if not db_file.exists():
                    raise DatabaseError(f"Database file not found: {db_file}")
                
                # Copy the database file
                shutil.copy2(db_file, backup_path)
                logger.info(f"Database backup created: {backup_path}")
                
                return backup_path
            else:
                # For non-SQLite databases, we'd need to use database-specific backup tools
                raise DatabaseError(f"Backup not supported for database type: {self.engine.url.drivername}")
                
        except Exception as e:
            logger.error(f"Failed to backup database: {e}")
            raise DatabaseError(f"Failed to backup database: {e}") from e
