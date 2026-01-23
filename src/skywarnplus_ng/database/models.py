"""
Database models for SkywarnPlus-NG.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, 
    Float, JSON, Index, UniqueConstraint, ForeignKey
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid

Base = declarative_base()


class AlertRecord(Base):
    """Database model for weather alerts."""
    
    __tablename__ = "alerts"
    
    # Primary key
    id = Column(String, primary_key=True)  # NWS alert ID
    
    # Alert details
    event = Column(String, nullable=False, index=True)
    headline = Column(Text)
    description = Column(Text)
    instruction = Column(Text)
    
    # Alert classification
    severity = Column(String, nullable=False, index=True)
    urgency = Column(String, nullable=False)
    certainty = Column(String, nullable=False)
    status = Column(String, nullable=False)
    category = Column(String, nullable=False)
    
    # Timestamps
    sent_time = Column(DateTime, nullable=False, index=True)
    effective_time = Column(DateTime, nullable=False, index=True)
    onset_time = Column(DateTime, index=True)
    expires_time = Column(DateTime, nullable=False, index=True)
    ends_time = Column(DateTime, index=True)
    
    # Geographic information
    area_desc = Column(Text, nullable=False)
    geocode = Column(JSON)  # List of geocodes
    county_codes = Column(JSON)  # List of county codes
    
    # Sender information
    sender = Column(String, nullable=False)
    sender_name = Column(String, nullable=False)
    
    # Processing information
    processed_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    announced = Column(Boolean, default=False, index=True)
    script_executed = Column(Boolean, default=False, index=True)
    announcement_nodes = Column(JSON)  # List of nodes that announced this alert
    
    # Additional metadata
    additional_data = Column(JSON)
    
    # Indexes for common queries
    __table_args__ = (
        Index('idx_alerts_event_severity', 'event', 'severity'),
        Index('idx_alerts_effective_expires', 'effective_time', 'expires_time'),
        Index('idx_alerts_processed_announced', 'processed_at', 'announced'),
    )


class MetricRecord(Base):
    """Database model for system metrics."""
    
    __tablename__ = "metrics"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Metric details
    metric_name = Column(String, nullable=False, index=True)
    metric_value = Column(Float, nullable=False)
    metric_unit = Column(String)
    
    # Timestamp
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    
    # Additional metadata
    additional_data = Column(JSON)
    
    # Indexes for common queries
    __table_args__ = (
        Index('idx_metrics_name_timestamp', 'metric_name', 'timestamp'),
        Index('idx_metrics_timestamp', 'timestamp'),
    )


class HealthCheckRecord(Base):
    """Database model for health check results."""
    
    __tablename__ = "health_checks"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Health check details
    overall_status = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    uptime_seconds = Column(Float, nullable=False)
    
    # Component status (stored as JSON)
    components = Column(JSON, nullable=False)
    
    # Additional metadata
    additional_data = Column(JSON)
    
    # Indexes for common queries
    __table_args__ = (
        Index('idx_health_status_timestamp', 'overall_status', 'timestamp'),
        Index('idx_health_timestamp', 'timestamp'),
    )


class ScriptExecutionRecord(Base):
    """Database model for script execution logs."""
    
    __tablename__ = "script_executions"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Script execution details
    script_type = Column(String, nullable=False, index=True)  # 'alert' or 'all_clear'
    command = Column(String, nullable=False)
    args = Column(JSON)  # List of arguments
    
    # Execution results
    success = Column(Boolean, nullable=False, index=True)
    return_code = Column(Integer)
    execution_time_ms = Column(Float)
    error_message = Column(Text)
    output = Column(Text)
    
    # Timestamps
    started_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    completed_at = Column(DateTime, index=True)
    
    # Alert reference (if applicable)
    alert_id = Column(String, ForeignKey('alerts.id'), index=True)
    alert_event = Column(String, index=True)
    
    # Additional metadata
    additional_data = Column(JSON)
    
    # Indexes for common queries
    __table_args__ = (
        Index('idx_script_type_success', 'script_type', 'success'),
        Index('idx_script_started_at', 'started_at'),
        Index('idx_script_alert_id', 'alert_id'),
    )


class ConfigurationRecord(Base):
    """Database model for configuration history."""
    
    __tablename__ = "configurations"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Configuration details
    config_name = Column(String, nullable=False, index=True)
    config_version = Column(String, nullable=False)
    config_data = Column(JSON, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    applied_at = Column(DateTime, index=True)
    
    # User information
    created_by = Column(String)
    applied_by = Column(String)
    
    # Status
    is_active = Column(Boolean, default=False, index=True)
    
    # Additional metadata
    additional_data = Column(JSON)
    
    # Indexes for common queries
    __table_args__ = (
        Index('idx_config_name_version', 'config_name', 'config_version'),
        Index('idx_config_active', 'is_active'),
        Index('idx_config_created_at', 'created_at'),
    )


class AlertAnalytics(Base):
    """Database model for alert analytics and statistics."""
    
    __tablename__ = "alert_analytics"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Time period
    period_start = Column(DateTime, nullable=False, index=True)
    period_end = Column(DateTime, nullable=False, index=True)
    period_type = Column(String, nullable=False, index=True)  # 'hour', 'day', 'week', 'month'
    
    # Alert statistics
    total_alerts = Column(Integer, default=0)
    alerts_by_type = Column(JSON)  # {event_type: count}
    alerts_by_severity = Column(JSON)  # {severity: count}
    alerts_by_county = Column(JSON)  # {county_code: count}
    
    # Processing statistics
    announcements_sent = Column(Integer, default=0)
    scripts_executed = Column(Integer, default=0)
    scripts_failed = Column(Integer, default=0)
    
    # Performance metrics
    avg_processing_time_ms = Column(Float)
    avg_announcement_time_ms = Column(Float)
    avg_script_execution_time_ms = Column(Float)
    
    # Timestamps
    calculated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    
    # Additional metadata
    additional_data = Column(JSON)
    
    # Indexes for common queries
    __table_args__ = (
        Index('idx_analytics_period', 'period_start', 'period_end'),
        Index('idx_analytics_type_period', 'period_type', 'period_start'),
        Index('idx_analytics_calculated_at', 'calculated_at'),
    )
