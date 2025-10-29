"""
Enhanced logging utilities for SkywarnPlus-NG.
"""

import logging
import logging.handlers
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
import structlog
from structlog.stdlib import LoggerFactory

from ..core.config import LoggingConfig


class SkywarnPlusFormatter(logging.Formatter):
    """Custom formatter for SkywarnPlus-NG logs."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with structured data."""
        # Extract structured data from record
        extra_data = {}
        for key, value in record.__dict__.items():
            if key not in {
                'name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                'filename', 'module', 'lineno', 'funcName', 'created',
                'msecs', 'relativeCreated', 'thread', 'threadName',
                'processName', 'process', 'getMessage', 'exc_info',
                'exc_text', 'stack_info'
            }:
                extra_data[key] = value

        # Create structured log entry
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }

        # Add extra data if present
        if extra_data:
            log_entry['data'] = extra_data

        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = {
                'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                'message': str(record.exc_info[1]) if record.exc_info[1] else None,
                'traceback': self.formatException(record.exc_info) if record.exc_info else None,
            }

        return json.dumps(log_entry, default=str)


class PerformanceLogger:
    """Logger for performance metrics."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self._metrics: Dict[str, Any] = {}

    def start_timer(self, operation: str) -> str:
        """Start timing an operation."""
        timer_id = f"{operation}_{datetime.now(timezone.utc).timestamp()}"
        self._metrics[timer_id] = {
            'operation': operation,
            'start_time': datetime.now(timezone.utc),
            'status': 'running'
        }
        return timer_id

    def end_timer(self, timer_id: str, success: bool = True, **extra_data) -> None:
        """End timing an operation and log the result."""
        if timer_id not in self._metrics:
            self.logger.warning(f"Timer {timer_id} not found")
            return

        metric = self._metrics[timer_id]
        end_time = datetime.now(timezone.utc)
        duration_ms = (end_time - metric['start_time']).total_seconds() * 1000

        self.logger.info(
            f"Operation completed: {metric['operation']}",
            extra={
                'operation': metric['operation'],
                'duration_ms': round(duration_ms, 2),
                'success': success,
                'end_time': end_time.isoformat(),
                **extra_data
            }
        )

        # Remove from active metrics
        del self._metrics[timer_id]

    def log_metric(self, name: str, value: Any, unit: str = None, **extra_data) -> None:
        """Log a performance metric."""
        self.logger.info(
            f"Performance metric: {name}",
            extra={
                'metric_name': name,
                'metric_value': value,
                'metric_unit': unit,
                **extra_data
            }
        )


class AlertLogger:
    """Specialized logger for alert processing events."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def log_alert_received(self, alert_id: str, alert_type: str, area: str, **extra_data) -> None:
        """Log when an alert is received."""
        self.logger.info(
            f"Alert received: {alert_type}",
            extra={
                'event_type': 'alert_received',
                'alert_id': alert_id,
                'alert_type': alert_type,
                'alert_area': area,
                **extra_data
            }
        )

    def log_alert_processed(self, alert_id: str, alert_type: str, success: bool, 
                          processing_time_ms: float, **extra_data) -> None:
        """Log when an alert is processed."""
        self.logger.info(
            f"Alert processed: {alert_type}",
            extra={
                'event_type': 'alert_processed',
                'alert_id': alert_id,
                'alert_type': alert_type,
                'success': success,
                'processing_time_ms': processing_time_ms,
                **extra_data
            }
        )

    def log_alert_announced(self, alert_id: str, alert_type: str, nodes: list, **extra_data) -> None:
        """Log when an alert is announced."""
        self.logger.info(
            f"Alert announced: {alert_type}",
            extra={
                'event_type': 'alert_announced',
                'alert_id': alert_id,
                'alert_type': alert_type,
                'nodes_announced': nodes,
                **extra_data
            }
        )

    def log_script_executed(self, alert_id: str, script_name: str, success: bool, 
                          execution_time_ms: float, **extra_data) -> None:
        """Log when a script is executed."""
        self.logger.info(
            f"Script executed: {script_name}",
            extra={
                'event_type': 'script_executed',
                'alert_id': alert_id,
                'script_name': script_name,
                'success': success,
                'execution_time_ms': execution_time_ms,
                **extra_data
            }
        )

    def log_all_clear(self, **extra_data) -> None:
        """Log all-clear event."""
        self.logger.info(
            "All clear - no active alerts",
            extra={
                'event_type': 'all_clear',
                **extra_data
            }
        )


def setup_logging(config: LoggingConfig) -> tuple[logging.Logger, PerformanceLogger, AlertLogger]:
    """
    Setup enhanced logging for SkywarnPlus-NG.

    Args:
        config: Logging configuration

    Returns:
        Tuple of (main_logger, performance_logger, alert_logger)
    """
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Create main logger
    logger = logging.getLogger('skywarnplus_ng')
    logger.setLevel(getattr(logging, config.level.upper()))

    # Clear existing handlers
    logger.handlers.clear()

    # Create formatter
    if config.format == 'json':
        formatter = SkywarnPlusFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (if configured)
    if config.file:
        file_path = Path(config.file)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Use rotating file handler
        file_handler = logging.handlers.RotatingFileHandler(
            file_path,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Create specialized loggers
    performance_logger = PerformanceLogger(logger)
    alert_logger = AlertLogger(logger)

    logger.info("Logging system initialized", extra={
        'log_level': config.level,
        'log_format': config.format,
        'log_file': str(config.file) if config.file else None
    })

    return logger, performance_logger, alert_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(f'skywarnplus_ng.{name}')
