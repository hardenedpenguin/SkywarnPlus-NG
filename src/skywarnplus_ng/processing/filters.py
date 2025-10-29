"""
Advanced alert filtering system for SkywarnPlus-NG.
"""

import re
import logging
from datetime import datetime, timezone, time
from typing import List, Dict, Any, Optional, Union, Callable
from dataclasses import dataclass
from enum import Enum
import json

from ..core.models import WeatherAlert, AlertSeverity, AlertUrgency, AlertCertainty

logger = logging.getLogger(__name__)


class FilterType(Enum):
    """Types of filters."""
    GEOGRAPHIC = "geographic"
    TIME = "time"
    SEVERITY = "severity"
    CUSTOM_RULE = "custom_rule"
    TEXT_MATCH = "text_match"
    REGEX = "regex"


@dataclass
class FilterResult:
    """Result of filter evaluation."""
    
    passed: bool
    reason: str
    metadata: Dict[str, Any]
    
    def __post_init__(self):
        if not self.metadata:
            self.metadata = {}


class AlertFilter:
    """Base class for alert filters."""
    
    def __init__(self, name: str, enabled: bool = True):
        self.name = name
        self.enabled = enabled
        self.logger = logging.getLogger(f"{__name__}.{name}")
    
    def filter(self, alert: WeatherAlert) -> FilterResult:
        """
        Filter an alert.
        
        Args:
            alert: Weather alert to filter
            
        Returns:
            Filter result
        """
        if not self.enabled:
            return FilterResult(passed=True, reason="Filter disabled", metadata={})
        
        try:
            return self._apply_filter(alert)
        except Exception as e:
            self.logger.error(f"Filter '{self.name}' failed: {e}")
            return FilterResult(
                passed=False, 
                reason=f"Filter error: {str(e)}", 
                metadata={"error": str(e)}
            )
    
    def _apply_filter(self, alert: WeatherAlert) -> FilterResult:
        """Apply the actual filter logic. Override in subclasses."""
        raise NotImplementedError


class GeographicFilter(AlertFilter):
    """Filter alerts based on geographic criteria."""
    
    def __init__(
        self, 
        name: str = "GeographicFilter",
        enabled: bool = True,
        allowed_counties: Optional[List[str]] = None,
        blocked_counties: Optional[List[str]] = None,
        bounding_box: Optional[Dict[str, float]] = None,
        polygon_coordinates: Optional[List[List[float]]] = None
    ):
        super().__init__(name, enabled)
        self.allowed_counties = allowed_counties or []
        self.blocked_counties = blocked_counties or []
        self.bounding_box = bounding_box
        self.polygon_coordinates = polygon_coordinates
    
    def _apply_filter(self, alert: WeatherAlert) -> FilterResult:
        """Apply geographic filtering."""
        metadata = {}
        
        # Check county-based filtering
        if self.allowed_counties or self.blocked_counties:
            alert_counties = alert.county_codes or []
            
            # Check if any alert counties are in blocked list
            if self.blocked_counties:
                blocked_matches = set(alert_counties) & set(self.blocked_counties)
                if blocked_matches:
                    return FilterResult(
                        passed=False,
                        reason=f"Alert counties blocked: {list(blocked_matches)}",
                        metadata={"blocked_counties": list(blocked_matches)}
                    )
            
            # Check if any alert counties are in allowed list
            if self.allowed_counties:
                allowed_matches = set(alert_counties) & set(self.allowed_counties)
                if not allowed_matches:
                    return FilterResult(
                        passed=False,
                        reason=f"No alert counties in allowed list: {alert_counties}",
                        metadata={"alert_counties": alert_counties, "allowed_counties": self.allowed_counties}
                    )
                metadata["allowed_counties"] = list(allowed_matches)
        
        # Check bounding box filtering
        if self.bounding_box:
            if not self._is_in_bounding_box(alert, self.bounding_box):
                return FilterResult(
                    passed=False,
                    reason="Alert outside bounding box",
                    metadata={"bounding_box": self.bounding_box}
                )
            metadata["in_bounding_box"] = True
        
        # Check polygon filtering
        if self.polygon_coordinates:
            if not self._is_in_polygon(alert, self.polygon_coordinates):
                return FilterResult(
                    passed=False,
                    reason="Alert outside polygon area",
                    metadata={"polygon_coordinates": self.polygon_coordinates}
                )
            metadata["in_polygon"] = True
        
        return FilterResult(
            passed=True,
            reason="Geographic filter passed",
            metadata=metadata
        )
    
    def _is_in_bounding_box(self, alert: WeatherAlert, bbox: Dict[str, float]) -> bool:
        """Check if alert is within bounding box."""
        # This is a simplified implementation
        # In a real implementation, you'd parse the alert's geocode data
        # and check if coordinates fall within the bounding box
        return True  # Placeholder
    
    def _is_in_polygon(self, alert: WeatherAlert, polygon: List[List[float]]) -> bool:
        """Check if alert is within polygon using ray casting algorithm."""
        # This is a simplified implementation
        # In a real implementation, you'd parse the alert's geocode data
        # and use a proper point-in-polygon algorithm
        return True  # Placeholder


class TimeFilter(AlertFilter):
    """Filter alerts based on time criteria."""
    
    def __init__(
        self,
        name: str = "TimeFilter",
        enabled: bool = True,
        business_hours_only: bool = False,
        business_start: time = time(9, 0),
        business_end: time = time(17, 0),
        weekdays_only: bool = False,
        allowed_days: Optional[List[int]] = None,  # 0=Monday, 6=Sunday
        time_window_hours: Optional[int] = None,
        exclude_holidays: bool = False
    ):
        super().__init__(name, enabled)
        self.business_hours_only = business_hours_only
        self.business_start = business_start
        self.business_end = business_end
        self.weekdays_only = weekdays_only
        self.allowed_days = allowed_days or []
        self.time_window_hours = time_window_hours
        self.exclude_holidays = exclude_holidays
    
    def _apply_filter(self, alert: WeatherAlert) -> FilterResult:
        """Apply time-based filtering."""
        now = datetime.now(timezone.utc)
        alert_time = alert.effective.replace(tzinfo=timezone.utc) if alert.effective else now
        
        metadata = {"alert_time": alert_time.isoformat()}
        
        # Check business hours
        if self.business_hours_only:
            alert_local_time = alert_time.time()
            if not (self.business_start <= alert_local_time <= self.business_end):
                return FilterResult(
                    passed=False,
                    reason=f"Alert outside business hours ({self.business_start}-{self.business_end})",
                    metadata=metadata
                )
            metadata["in_business_hours"] = True
        
        # Check weekdays only
        if self.weekdays_only:
            if alert_time.weekday() >= 5:  # Saturday=5, Sunday=6
                return FilterResult(
                    passed=False,
                    reason="Alert on weekend",
                    metadata=metadata
                )
            metadata["is_weekday"] = True
        
        # Check allowed days
        if self.allowed_days:
            if alert_time.weekday() not in self.allowed_days:
                return FilterResult(
                    passed=False,
                    reason=f"Alert on non-allowed day (weekday {alert_time.weekday()})",
                    metadata=metadata
                )
            metadata["allowed_day"] = True
        
        # Check time window
        if self.time_window_hours:
            time_diff = (now - alert_time).total_seconds() / 3600
            if time_diff > self.time_window_hours:
                return FilterResult(
                    passed=False,
                    reason=f"Alert too old ({time_diff:.1f}h > {self.time_window_hours}h)",
                    metadata=metadata
                )
            metadata["within_time_window"] = True
        
        # Check holidays (simplified implementation)
        if self.exclude_holidays:
            if self._is_holiday(alert_time):
                return FilterResult(
                    passed=False,
                    reason="Alert on holiday",
                    metadata=metadata
                )
            metadata["not_holiday"] = True
        
        return FilterResult(
            passed=True,
            reason="Time filter passed",
            metadata=metadata
        )
    
    def _is_holiday(self, dt: datetime) -> bool:
        """Check if date is a holiday (simplified implementation)."""
        # This is a placeholder - in a real implementation you'd check against
        # a holiday calendar or API
        return False


class SeverityFilter(AlertFilter):
    """Filter alerts based on severity criteria."""
    
    def __init__(
        self,
        name: str = "SeverityFilter",
        enabled: bool = True,
        min_severity: Optional[AlertSeverity] = None,
        max_severity: Optional[AlertSeverity] = None,
        allowed_severities: Optional[List[AlertSeverity]] = None,
        blocked_severities: Optional[List[AlertSeverity]] = None,
        min_urgency: Optional[AlertUrgency] = None,
        min_certainty: Optional[AlertCertainty] = None
    ):
        super().__init__(name, enabled)
        self.min_severity = min_severity
        self.max_severity = max_severity
        self.allowed_severities = allowed_severities or []
        self.blocked_severities = blocked_severities or []
        self.min_urgency = min_urgency
        self.min_certainty = min_certainty
    
    def _apply_filter(self, alert: WeatherAlert) -> FilterResult:
        """Apply severity-based filtering."""
        metadata = {
            "severity": alert.severity.value,
            "urgency": alert.urgency.value,
            "certainty": alert.certainty.value
        }
        
        # Check blocked severities
        if self.blocked_severities and alert.severity in self.blocked_severities:
            return FilterResult(
                passed=False,
                reason=f"Severity blocked: {alert.severity.value}",
                metadata=metadata
            )
        
        # Check allowed severities
        if self.allowed_severities and alert.severity not in self.allowed_severities:
            return FilterResult(
                passed=False,
                reason=f"Severity not allowed: {alert.severity.value}",
                metadata=metadata
            )
        
        # Check minimum severity
        if self.min_severity and not self._severity_gte(alert.severity, self.min_severity):
            return FilterResult(
                passed=False,
                reason=f"Severity too low: {alert.severity.value} < {self.min_severity.value}",
                metadata=metadata
            )
        
        # Check maximum severity
        if self.max_severity and not self._severity_lte(alert.severity, self.max_severity):
            return FilterResult(
                passed=False,
                reason=f"Severity too high: {alert.severity.value} > {self.max_severity.value}",
                metadata=metadata
            )
        
        # Check minimum urgency
        if self.min_urgency and not self._urgency_gte(alert.urgency, self.min_urgency):
            return FilterResult(
                passed=False,
                reason=f"Urgency too low: {alert.urgency.value} < {self.min_urgency.value}",
                metadata=metadata
            )
        
        # Check minimum certainty
        if self.min_certainty and not self._certainty_gte(alert.certainty, self.min_certainty):
            return FilterResult(
                passed=False,
                reason=f"Certainty too low: {alert.certainty.value} < {self.min_certainty.value}",
                metadata=metadata
            )
        
        return FilterResult(
            passed=True,
            reason="Severity filter passed",
            metadata=metadata
        )
    
    def _severity_gte(self, severity1: AlertSeverity, severity2: AlertSeverity) -> bool:
        """Check if severity1 >= severity2."""
        severity_order = {
            AlertSeverity.MINOR: 1,
            AlertSeverity.MODERATE: 2,
            AlertSeverity.SEVERE: 3,
            AlertSeverity.EXTREME: 4
        }
        return severity_order.get(severity1, 0) >= severity_order.get(severity2, 0)
    
    def _severity_lte(self, severity1: AlertSeverity, severity2: AlertSeverity) -> bool:
        """Check if severity1 <= severity2."""
        return self._severity_gte(severity2, severity1)
    
    def _urgency_gte(self, urgency1: AlertUrgency, urgency2: AlertUrgency) -> bool:
        """Check if urgency1 >= urgency2."""
        urgency_order = {
            AlertUrgency.PAST: 1,
            AlertUrgency.FUTURE: 2,
            AlertUrgency.EXPECTED: 3,
            AlertUrgency.IMMEDIATE: 4
        }
        return urgency_order.get(urgency1, 0) >= urgency_order.get(urgency2, 0)
    
    def _certainty_gte(self, certainty1: AlertCertainty, certainty2: AlertCertainty) -> bool:
        """Check if certainty1 >= certainty2."""
        certainty_order = {
            AlertCertainty.UNLIKELY: 1,
            AlertCertainty.POSSIBLE: 2,
            AlertCertainty.LIKELY: 3,
            AlertCertainty.OBSERVED: 4
        }
        return certainty_order.get(certainty1, 0) >= certainty_order.get(certainty2, 0)


class CustomRuleFilter(AlertFilter):
    """Filter alerts using custom rules."""
    
    def __init__(
        self,
        name: str = "CustomRuleFilter",
        enabled: bool = True,
        rules: Optional[List[Dict[str, Any]]] = None
    ):
        super().__init__(name, enabled)
        self.rules = rules or []
    
    def _apply_filter(self, alert: WeatherAlert) -> FilterResult:
        """Apply custom rule filtering."""
        metadata = {"rules_evaluated": 0, "rules_passed": 0}
        
        for rule in self.rules:
            metadata["rules_evaluated"] += 1
            
            if not self._evaluate_rule(alert, rule):
                return FilterResult(
                    passed=False,
                    reason=f"Custom rule failed: {rule.get('name', 'unnamed')}",
                    metadata=metadata
                )
            
            metadata["rules_passed"] += 1
        
        return FilterResult(
            passed=True,
            reason=f"All {len(self.rules)} custom rules passed",
            metadata=metadata
        )
    
    def _evaluate_rule(self, alert: WeatherAlert, rule: Dict[str, Any]) -> bool:
        """Evaluate a single custom rule."""
        rule_type = rule.get("type", "text_match")
        
        if rule_type == "text_match":
            return self._evaluate_text_match(alert, rule)
        elif rule_type == "regex":
            return self._evaluate_regex(alert, rule)
        elif rule_type == "field_equals":
            return self._evaluate_field_equals(alert, rule)
        elif rule_type == "field_contains":
            return self._evaluate_field_contains(alert, rule)
        elif rule_type == "custom_function":
            return self._evaluate_custom_function(alert, rule)
        else:
            self.logger.warning(f"Unknown rule type: {rule_type}")
            return True  # Default to pass for unknown rules
    
    def _evaluate_text_match(self, alert: WeatherAlert, rule: Dict[str, Any]) -> bool:
        """Evaluate text match rule."""
        field = rule.get("field", "event")
        pattern = rule.get("pattern", "")
        case_sensitive = rule.get("case_sensitive", False)
        
        value = self._get_field_value(alert, field)
        if not value:
            return False
        
        if not case_sensitive:
            value = value.lower()
            pattern = pattern.lower()
        
        return pattern in value
    
    def _evaluate_regex(self, alert: WeatherAlert, rule: Dict[str, Any]) -> bool:
        """Evaluate regex rule."""
        field = rule.get("field", "event")
        pattern = rule.get("pattern", "")
        case_sensitive = rule.get("case_sensitive", False)
        
        value = self._get_field_value(alert, field)
        if not value:
            return False
        
        flags = 0 if case_sensitive else re.IGNORECASE
        
        try:
            return bool(re.search(pattern, value, flags))
        except re.error as e:
            self.logger.error(f"Regex error in rule: {e}")
            return False
    
    def _evaluate_field_equals(self, alert: WeatherAlert, rule: Dict[str, Any]) -> bool:
        """Evaluate field equals rule."""
        field = rule.get("field", "event")
        expected_value = rule.get("value", "")
        
        actual_value = self._get_field_value(alert, field)
        return str(actual_value) == str(expected_value)
    
    def _evaluate_field_contains(self, alert: WeatherAlert, rule: Dict[str, Any]) -> bool:
        """Evaluate field contains rule."""
        field = rule.get("field", "event")
        expected_value = rule.get("value", "")
        case_sensitive = rule.get("case_sensitive", False)
        
        actual_value = self._get_field_value(alert, field)
        if not actual_value:
            return False
        
        if not case_sensitive:
            actual_value = str(actual_value).lower()
            expected_value = str(expected_value).lower()
        
        return str(expected_value) in str(actual_value)
    
    def _evaluate_custom_function(self, alert: WeatherAlert, rule: Dict[str, Any]) -> bool:
        """Evaluate custom function rule."""
        # This would require implementing a safe way to execute custom functions
        # For now, just return True as a placeholder
        self.logger.warning("Custom function evaluation not implemented")
        return True
    
    def _get_field_value(self, alert: WeatherAlert, field: str) -> Any:
        """Get field value from alert."""
        field_mapping = {
            "event": alert.event,
            "headline": alert.headline,
            "description": alert.description,
            "area_desc": alert.area_desc,
            "severity": alert.severity.value,
            "urgency": alert.urgency.value,
            "certainty": alert.certainty.value,
            "status": alert.status.value,
            "category": alert.category.value,
            "sender": alert.sender,
            "sender_name": alert.sender_name
        }
        
        return field_mapping.get(field, "")


class FilterChain:
    """Chain of filters to apply to alerts."""
    
    def __init__(self, name: str = "FilterChain"):
        self.name = name
        self.filters: List[AlertFilter] = []
        self.logger = logging.getLogger(f"{__name__}.{name}")
    
    def add_filter(self, filter_obj: AlertFilter) -> None:
        """Add a filter to the chain."""
        self.filters.append(filter_obj)
        self.logger.info(f"Added filter '{filter_obj.name}' to chain")
    
    def remove_filter(self, filter_name: str) -> None:
        """Remove a filter from the chain."""
        self.filters = [f for f in self.filters if f.name != filter_name]
        self.logger.info(f"Removed filter '{filter_name}' from chain")
    
    def filter_alert(self, alert: WeatherAlert) -> FilterResult:
        """Apply all filters to an alert."""
        for filter_obj in self.filters:
            result = filter_obj.filter(alert)
            if not result.passed:
                self.logger.debug(f"Alert {alert.id} filtered out by '{filter_obj.name}': {result.reason}")
                return result
        
        return FilterResult(
            passed=True,
            reason="All filters passed",
            metadata={"filters_applied": len(self.filters)}
        )
    
    def filter_alerts(self, alerts: List[WeatherAlert]) -> List[WeatherAlert]:
        """Apply all filters to a list of alerts."""
        filtered_alerts = []
        
        for alert in alerts:
            result = self.filter_alert(alert)
            if result.passed:
                filtered_alerts.append(alert)
        
        self.logger.info(f"Filtered {len(alerts)} alerts to {len(filtered_alerts)} alerts")
        return filtered_alerts
