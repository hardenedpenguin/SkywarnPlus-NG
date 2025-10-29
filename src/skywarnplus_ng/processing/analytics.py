"""
Alert analytics and reporting system for SkywarnPlus-NG.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import statistics
from collections import defaultdict, Counter

from ..core.models import WeatherAlert, AlertSeverity, AlertUrgency, AlertCertainty

logger = logging.getLogger(__name__)


class AnalyticsPeriod(Enum):
    """Analytics time periods."""
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class TrendDirection(Enum):
    """Trend directions."""
    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"
    VOLATILE = "volatile"


@dataclass
class AlertStatistics:
    """Alert statistics for a time period."""
    
    period_start: datetime
    period_end: datetime
    total_alerts: int
    severity_distribution: Dict[str, int]
    urgency_distribution: Dict[str, int]
    certainty_distribution: Dict[str, int]
    category_distribution: Dict[str, int]
    event_type_distribution: Dict[str, int]
    geographic_distribution: Dict[str, int]
    hourly_distribution: Dict[int, int]
    daily_distribution: Dict[int, int]
    average_processing_time_ms: float
    peak_alert_hour: int
    peak_alert_day: int
    most_common_event: str
    most_common_severity: str
    most_common_urgency: str
    calculated_at: datetime
    
    def __post_init__(self):
        if not self.calculated_at:
            self.calculated_at = datetime.now(timezone.utc)


@dataclass
class TrendAnalysis:
    """Trend analysis for alerts."""
    
    metric_name: str
    current_value: float
    previous_value: float
    change_percentage: float
    trend_direction: TrendDirection
    confidence_level: float
    data_points: List[float]
    period: AnalyticsPeriod
    calculated_at: datetime
    
    def __post_init__(self):
        if not self.calculated_at:
            self.calculated_at = datetime.now(timezone.utc)


@dataclass
class PerformanceMetrics:
    """Performance metrics for alert processing."""
    
    total_processed: int
    successful_processing: int
    failed_processing: int
    average_processing_time_ms: float
    median_processing_time_ms: float
    p95_processing_time_ms: float
    p99_processing_time_ms: float
    throughput_per_hour: float
    error_rate: float
    uptime_percentage: float
    calculated_at: datetime
    
    def __post_init__(self):
        if not self.calculated_at:
            self.calculated_at = datetime.now(timezone.utc)


class AlertAnalytics:
    """Analytics engine for weather alerts."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._alert_history: List[WeatherAlert] = []
        self._processing_times: List[float] = []
        self._error_counts: Dict[str, int] = defaultdict(int)
    
    def add_alert(self, alert: WeatherAlert, processing_time_ms: Optional[float] = None) -> None:
        """Add an alert to the analytics history."""
        self._alert_history.append(alert)
        
        if processing_time_ms is not None:
            self._processing_times.append(processing_time_ms)
        
        # Keep only last 10000 alerts to prevent memory issues
        if len(self._alert_history) > 10000:
            self._alert_history = self._alert_history[-10000:]
        
        if len(self._processing_times) > 10000:
            self._processing_times = self._processing_times[-10000:]
    
    def add_error(self, error_type: str) -> None:
        """Add an error to the analytics."""
        self._error_counts[error_type] += 1
    
    def get_statistics(self, period: AnalyticsPeriod, start_time: Optional[datetime] = None) -> AlertStatistics:
        """
        Get alert statistics for a time period.
        
        Args:
            period: Time period for statistics
            start_time: Start time for statistics (defaults to now - period)
            
        Returns:
            Alert statistics
        """
        if start_time is None:
            start_time = self._get_period_start(period)
        
        end_time = datetime.now(timezone.utc)
        
        # Filter alerts for the period
        period_alerts = [
            alert for alert in self._alert_history
            if start_time <= (alert.sent or alert.effective or datetime.min.replace(tzinfo=timezone.utc)) <= end_time
        ]
        
        if not period_alerts:
            return self._create_empty_statistics(start_time, end_time)
        
        # Calculate distributions
        severity_dist = Counter(alert.severity.value for alert in period_alerts)
        urgency_dist = Counter(alert.urgency.value for alert in period_alerts)
        certainty_dist = Counter(alert.certainty.value for alert in period_alerts)
        category_dist = Counter(alert.category.value for alert in period_alerts)
        event_dist = Counter(alert.event for alert in period_alerts)
        
        # Geographic distribution (by county codes)
        geo_dist = Counter()
        for alert in period_alerts:
            if alert.county_codes:
                for county in alert.county_codes:
                    geo_dist[county] += 1
        
        # Time distributions
        hourly_dist = Counter()
        daily_dist = Counter()
        
        for alert in period_alerts:
            alert_time = alert.sent or alert.effective
            if alert_time:
                if alert_time.tzinfo is None:
                    alert_time = alert_time.replace(tzinfo=timezone.utc)
                
                hourly_dist[alert_time.hour] += 1
                daily_dist[alert_time.weekday()] += 1
        
        # Processing time statistics
        processing_times = [
            time_ms for time_ms in self._processing_times
            if start_time <= datetime.now(timezone.utc) - timedelta(milliseconds=time_ms) <= end_time
        ]
        
        avg_processing_time = statistics.mean(processing_times) if processing_times else 0.0
        
        # Find peaks
        peak_hour = max(hourly_dist.items(), key=lambda x: x[1])[0] if hourly_dist else 0
        peak_day = max(daily_dist.items(), key=lambda x: x[1])[0] if daily_dist else 0
        
        # Most common values
        most_common_event = max(event_dist.items(), key=lambda x: x[1])[0] if event_dist else ""
        most_common_severity = max(severity_dist.items(), key=lambda x: x[1])[0] if severity_dist else ""
        most_common_urgency = max(urgency_dist.items(), key=lambda x: x[1])[0] if urgency_dist else ""
        
        return AlertStatistics(
            period_start=start_time,
            period_end=end_time,
            total_alerts=len(period_alerts),
            severity_distribution=dict(severity_dist),
            urgency_distribution=dict(urgency_dist),
            certainty_distribution=dict(certainty_dist),
            category_distribution=dict(category_dist),
            event_type_distribution=dict(event_dist),
            geographic_distribution=dict(geo_dist),
            hourly_distribution=dict(hourly_dist),
            daily_distribution=dict(daily_dist),
            average_processing_time_ms=avg_processing_time,
            peak_alert_hour=peak_hour,
            peak_alert_day=peak_day,
            most_common_event=most_common_event,
            most_common_severity=most_common_severity,
            most_common_urgency=most_common_urgency,
            calculated_at=datetime.now(timezone.utc)
        )
    
    def analyze_trends(self, metric_name: str, period: AnalyticsPeriod, data_points: int = 10) -> TrendAnalysis:
        """
        Analyze trends for a specific metric.
        
        Args:
            metric_name: Name of the metric to analyze
            period: Time period for analysis
            data_points: Number of data points to analyze
            
        Returns:
            Trend analysis
        """
        # Get data points for the metric
        metric_data = self._get_metric_data(metric_name, period, data_points)
        
        if len(metric_data) < 2:
            return TrendAnalysis(
                metric_name=metric_name,
                current_value=0.0,
                previous_value=0.0,
                change_percentage=0.0,
                trend_direction=TrendDirection.STABLE,
                confidence_level=0.0,
                data_points=metric_data,
                period=period,
                calculated_at=datetime.now(timezone.utc)
            )
        
        current_value = metric_data[-1]
        previous_value = metric_data[-2]
        
        # Calculate change percentage
        if previous_value != 0:
            change_percentage = ((current_value - previous_value) / previous_value) * 100
        else:
            change_percentage = 100.0 if current_value > 0 else 0.0
        
        # Determine trend direction
        trend_direction = self._determine_trend_direction(metric_data)
        
        # Calculate confidence level
        confidence_level = self._calculate_confidence_level(metric_data)
        
        return TrendAnalysis(
            metric_name=metric_name,
            current_value=current_value,
            previous_value=previous_value,
            change_percentage=change_percentage,
            trend_direction=trend_direction,
            confidence_level=confidence_level,
            data_points=metric_data,
            period=period,
            calculated_at=datetime.now(timezone.utc)
        )
    
    def get_performance_metrics(self, period_hours: int = 24) -> PerformanceMetrics:
        """
        Get performance metrics for alert processing.
        
        Args:
            period_hours: Number of hours to analyze
            
        Returns:
            Performance metrics
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=period_hours)
        
        # Filter data for the period
        period_alerts = [
            alert for alert in self._alert_history
            if (alert.sent or alert.effective or datetime.min.replace(tzinfo=timezone.utc)) >= cutoff_time
        ]
        
        period_processing_times = [
            time_ms for time_ms in self._processing_times
            if datetime.now(timezone.utc) - timedelta(milliseconds=time_ms) >= cutoff_time
        ]
        
        total_processed = len(period_alerts)
        successful_processing = total_processed - sum(self._error_counts.values())
        failed_processing = sum(self._error_counts.values())
        
        # Processing time statistics
        if period_processing_times:
            avg_processing_time = statistics.mean(period_processing_times)
            median_processing_time = statistics.median(period_processing_times)
            p95_processing_time = self._calculate_percentile(period_processing_times, 95)
            p99_processing_time = self._calculate_percentile(period_processing_times, 99)
        else:
            avg_processing_time = 0.0
            median_processing_time = 0.0
            p95_processing_time = 0.0
            p99_processing_time = 0.0
        
        # Throughput
        throughput_per_hour = total_processed / period_hours if period_hours > 0 else 0.0
        
        # Error rate
        error_rate = (failed_processing / total_processed) if total_processed > 0 else 0.0
        
        # Uptime (simplified calculation)
        uptime_percentage = (successful_processing / total_processed) if total_processed > 0 else 100.0
        
        return PerformanceMetrics(
            total_processed=total_processed,
            successful_processing=successful_processing,
            failed_processing=failed_processing,
            average_processing_time_ms=avg_processing_time,
            median_processing_time_ms=median_processing_time,
            p95_processing_time_ms=p95_processing_time,
            p99_processing_time_ms=p99_processing_time,
            throughput_per_hour=throughput_per_hour,
            error_rate=error_rate,
            uptime_percentage=uptime_percentage,
            calculated_at=datetime.now(timezone.utc)
        )
    
    def generate_report(self, period: AnalyticsPeriod, include_trends: bool = True) -> Dict[str, Any]:
        """
        Generate a comprehensive analytics report.
        
        Args:
            period: Time period for the report
            include_trends: Whether to include trend analysis
            
        Returns:
            Analytics report
        """
        self.logger.info(f"Generating analytics report for {period.value} period")
        
        # Get basic statistics
        stats = self.get_statistics(period)
        
        # Get performance metrics
        period_hours = self._get_period_hours(period)
        performance = self.get_performance_metrics(period_hours)
        
        report = {
            "report_generated_at": datetime.now(timezone.utc).isoformat(),
            "period": period.value,
            "period_start": stats.period_start.isoformat(),
            "period_end": stats.period_end.isoformat(),
            "statistics": {
                "total_alerts": stats.total_alerts,
                "severity_distribution": stats.severity_distribution,
                "urgency_distribution": stats.urgency_distribution,
                "certainty_distribution": stats.certainty_distribution,
                "category_distribution": stats.category_distribution,
                "event_type_distribution": stats.event_type_distribution,
                "geographic_distribution": stats.geographic_distribution,
                "hourly_distribution": stats.hourly_distribution,
                "daily_distribution": stats.daily_distribution,
                "peak_alert_hour": stats.peak_alert_hour,
                "peak_alert_day": stats.peak_alert_day,
                "most_common_event": stats.most_common_event,
                "most_common_severity": stats.most_common_severity,
                "most_common_urgency": stats.most_common_urgency
            },
            "performance": {
                "total_processed": performance.total_processed,
                "successful_processing": performance.successful_processing,
                "failed_processing": performance.failed_processing,
                "average_processing_time_ms": performance.average_processing_time_ms,
                "median_processing_time_ms": performance.median_processing_time_ms,
                "p95_processing_time_ms": performance.p95_processing_time_ms,
                "p99_processing_time_ms": performance.p99_processing_time_ms,
                "throughput_per_hour": performance.throughput_per_hour,
                "error_rate": performance.error_rate,
                "uptime_percentage": performance.uptime_percentage
            }
        }
        
        # Add trend analysis if requested
        if include_trends:
            trends = {}
            trend_metrics = ["total_alerts", "average_processing_time", "error_rate"]
            
            for metric in trend_metrics:
                try:
                    trend = self.analyze_trends(metric, period)
                    trends[metric] = {
                        "current_value": trend.current_value,
                        "previous_value": trend.previous_value,
                        "change_percentage": trend.change_percentage,
                        "trend_direction": trend.trend_direction.value,
                        "confidence_level": trend.confidence_level
                    }
                except Exception as e:
                    self.logger.error(f"Failed to analyze trend for {metric}: {e}")
                    trends[metric] = {
                        "current_value": 0.0,
                        "previous_value": 0.0,
                        "change_percentage": 0.0,
                        "trend_direction": "stable",
                        "confidence_level": 0.0
                    }
            
            report["trends"] = trends
        
        return report
    
    def _get_period_start(self, period: AnalyticsPeriod) -> datetime:
        """Get start time for a period."""
        now = datetime.now(timezone.utc)
        
        if period == AnalyticsPeriod.HOUR:
            return now - timedelta(hours=1)
        elif period == AnalyticsPeriod.DAY:
            return now - timedelta(days=1)
        elif period == AnalyticsPeriod.WEEK:
            return now - timedelta(weeks=1)
        elif period == AnalyticsPeriod.MONTH:
            return now - timedelta(days=30)
        elif period == AnalyticsPeriod.YEAR:
            return now - timedelta(days=365)
        else:
            return now - timedelta(days=1)
    
    def _get_period_hours(self, period: AnalyticsPeriod) -> int:
        """Get number of hours for a period."""
        if period == AnalyticsPeriod.HOUR:
            return 1
        elif period == AnalyticsPeriod.DAY:
            return 24
        elif period == AnalyticsPeriod.WEEK:
            return 168
        elif period == AnalyticsPeriod.MONTH:
            return 720
        elif period == AnalyticsPeriod.YEAR:
            return 8760
        else:
            return 24
    
    def _create_empty_statistics(self, start_time: datetime, end_time: datetime) -> AlertStatistics:
        """Create empty statistics for a period with no alerts."""
        return AlertStatistics(
            period_start=start_time,
            period_end=end_time,
            total_alerts=0,
            severity_distribution={},
            urgency_distribution={},
            certainty_distribution={},
            category_distribution={},
            event_type_distribution={},
            geographic_distribution={},
            hourly_distribution={},
            daily_distribution={},
            average_processing_time_ms=0.0,
            peak_alert_hour=0,
            peak_alert_day=0,
            most_common_event="",
            most_common_severity="",
            most_common_urgency="",
            calculated_at=datetime.now(timezone.utc)
        )
    
    def _get_metric_data(self, metric_name: str, period: AnalyticsPeriod, data_points: int) -> List[float]:
        """Get data points for a specific metric."""
        # This is a simplified implementation
        # In a real implementation, you'd query historical data
        
        if metric_name == "total_alerts":
            return [len(self._alert_history)] * data_points
        elif metric_name == "average_processing_time":
            if self._processing_times:
                return [statistics.mean(self._processing_times)] * data_points
            return [0.0] * data_points
        elif metric_name == "error_rate":
            total_errors = sum(self._error_counts.values())
            total_processed = len(self._alert_history)
            if total_processed > 0:
                error_rate = total_errors / total_processed
                return [error_rate] * data_points
            return [0.0] * data_points
        else:
            return [0.0] * data_points
    
    def _determine_trend_direction(self, data_points: List[float]) -> TrendDirection:
        """Determine trend direction from data points."""
        if len(data_points) < 2:
            return TrendDirection.STABLE
        
        # Calculate slope
        x = list(range(len(data_points)))
        y = data_points
        
        n = len(x)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(x[i] * y[i] for i in range(n))
        sum_x2 = sum(x[i] ** 2 for i in range(n))
        
        if n * sum_x2 - sum_x ** 2 == 0:
            return TrendDirection.STABLE
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)
        
        # Calculate variance to determine volatility
        mean_y = sum_y / n
        variance = sum((y[i] - mean_y) ** 2 for i in range(n)) / n
        std_dev = variance ** 0.5
        
        # Determine trend direction
        if std_dev > mean_y * 0.5:  # High volatility
            return TrendDirection.VOLATILE
        elif slope > 0.1:
            return TrendDirection.INCREASING
        elif slope < -0.1:
            return TrendDirection.DECREASING
        else:
            return TrendDirection.STABLE
    
    def _calculate_confidence_level(self, data_points: List[float]) -> float:
        """Calculate confidence level for trend analysis."""
        if len(data_points) < 2:
            return 0.0
        
        # Simple confidence calculation based on data consistency
        mean_value = statistics.mean(data_points)
        variance = statistics.variance(data_points) if len(data_points) > 1 else 0
        
        # Higher confidence for more consistent data
        if variance == 0:
            return 1.0
        
        coefficient_of_variation = (variance ** 0.5) / mean_value if mean_value != 0 else 1.0
        
        # Convert to confidence level (0-1)
        confidence = max(0.0, min(1.0, 1.0 - coefficient_of_variation))
        
        return confidence
    
    def _calculate_percentile(self, data: List[float], percentile: int) -> float:
        """Calculate percentile of data."""
        if not data:
            return 0.0
        
        sorted_data = sorted(data)
        index = (percentile / 100) * (len(sorted_data) - 1)
        
        if index.is_integer():
            return sorted_data[int(index)]
        else:
            lower_index = int(index)
            upper_index = lower_index + 1
            weight = index - lower_index
            
            return sorted_data[lower_index] * (1 - weight) + sorted_data[upper_index] * weight
