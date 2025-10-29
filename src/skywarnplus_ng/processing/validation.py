"""
Alert validation and verification system for SkywarnPlus-NG.
"""

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import json

from ..core.models import WeatherAlert, AlertSeverity, AlertUrgency, AlertCertainty, AlertStatus, AlertCategory

logger = logging.getLogger(__name__)


class ValidationStatus(Enum):
    """Validation status."""
    VALID = "valid"
    INVALID = "invalid"
    SUSPICIOUS = "suspicious"
    UNKNOWN = "unknown"


class ConfidenceLevel(Enum):
    """Confidence levels."""
    VERY_HIGH = "very_high"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    VERY_LOW = "very_low"


@dataclass
class ValidationResult:
    """Result of alert validation."""
    
    alert: WeatherAlert
    status: ValidationStatus
    confidence: ConfidenceLevel
    confidence_score: float
    validation_checks: List[Dict[str, Any]]
    issues: List[str]
    recommendations: List[str]
    validated_at: datetime
    
    def __post_init__(self):
        if not self.validated_at:
            self.validated_at = datetime.now(timezone.utc)


@dataclass
class ConfidenceScore:
    """Confidence score for an alert."""
    
    alert: WeatherAlert
    overall_confidence: float
    component_scores: Dict[str, float]
    factors: List[str]
    calculated_at: datetime
    
    def __post_init__(self):
        if not self.calculated_at:
            self.calculated_at = datetime.now(timezone.utc)


class AlertValidator:
    """Validates and verifies weather alerts."""
    
    def __init__(
        self,
        min_confidence_threshold: float = 0.6,
        enable_cross_validation: bool = True,
        enable_anomaly_detection: bool = True,
        enable_consistency_checks: bool = True
    ):
        self.min_confidence_threshold = min_confidence_threshold
        self.enable_cross_validation = enable_cross_validation
        self.enable_anomaly_detection = enable_anomaly_detection
        self.enable_consistency_checks = enable_consistency_checks
        self.logger = logging.getLogger(__name__)
        
        # Known valid values for validation
        self.valid_severities = {s.value for s in AlertSeverity}
        self.valid_urgencies = {u.value for u in AlertUrgency}
        self.valid_certainties = {c.value for c in AlertCertainty}
        self.valid_statuses = {s.value for s in AlertStatus}
        self.valid_categories = {c.value for c in AlertCategory}
        
        # Patterns for validation
        self.alert_id_pattern = re.compile(r'^[A-Z0-9\-_]+$')
        self.county_code_pattern = re.compile(r'^[A-Z]{2}[A-Z]\d{3}$')
        self.url_pattern = re.compile(r'^https?://[^\s/$.?#].[^\s]*$')
    
    def validate_alert(self, alert: WeatherAlert) -> ValidationResult:
        """
        Validate a weather alert.
        
        Args:
            alert: Weather alert to validate
            
        Returns:
            Validation result
        """
        self.logger.debug(f"Validating alert {alert.id}: {alert.event}")
        
        validation_checks = []
        issues = []
        recommendations = []
        
        # Perform validation checks
        checks = [
            self._validate_alert_id,
            self._validate_basic_fields,
            self._validate_enum_values,
            self._validate_dates,
            self._validate_geographic_data,
            self._validate_content_quality,
            self._validate_consistency,
            self._validate_anomalies
        ]
        
        for check in checks:
            try:
                check_result = check(alert)
                validation_checks.append(check_result)
                
                if not check_result.get("passed", True):
                    issues.extend(check_result.get("issues", []))
                    recommendations.extend(check_result.get("recommendations", []))
            except Exception as e:
                self.logger.error(f"Validation check failed: {e}")
                validation_checks.append({
                    "check": check.__name__,
                    "passed": False,
                    "issues": [f"Check failed: {str(e)}"],
                    "recommendations": ["Review alert data quality"]
                })
        
        # Calculate confidence score
        confidence_score = self._calculate_confidence_score(alert, validation_checks)
        confidence_level = self._determine_confidence_level(confidence_score)
        
        # Determine validation status
        status = self._determine_validation_status(confidence_score, issues)
        
        return ValidationResult(
            alert=alert,
            status=status,
            confidence=confidence_level,
            confidence_score=confidence_score,
            validation_checks=validation_checks,
            issues=issues,
            recommendations=recommendations,
            validated_at=datetime.now(timezone.utc)
        )
    
    def validate_alerts(self, alerts: List[WeatherAlert]) -> List[ValidationResult]:
        """
        Validate a list of alerts.
        
        Args:
            alerts: List of alerts to validate
            
        Returns:
            List of validation results
        """
        self.logger.info(f"Validating {len(alerts)} alerts")
        
        results = []
        for alert in alerts:
            try:
                result = self.validate_alert(alert)
                results.append(result)
            except Exception as e:
                self.logger.error(f"Failed to validate alert {alert.id}: {e}")
                continue
        
        self.logger.info(f"Validated {len(results)} alerts")
        return results
    
    def calculate_confidence_score(self, alert: WeatherAlert) -> ConfidenceScore:
        """
        Calculate confidence score for an alert.
        
        Args:
            alert: Weather alert to score
            
        Returns:
            Confidence score
        """
        self.logger.debug(f"Calculating confidence score for alert {alert.id}")
        
        # Calculate component scores
        data_completeness = self._calculate_data_completeness(alert)
        data_consistency = self._calculate_data_consistency(alert)
        source_reliability = self._calculate_source_reliability(alert)
        temporal_validity = self._calculate_temporal_validity(alert)
        geographic_validity = self._calculate_geographic_validity(alert)
        content_quality = self._calculate_content_quality(alert)
        
        # Calculate overall confidence
        overall_confidence = (
            data_completeness * 0.2 +
            data_consistency * 0.2 +
            source_reliability * 0.2 +
            temporal_validity * 0.15 +
            geographic_validity * 0.15 +
            content_quality * 0.1
        )
        
        # Identify factors affecting confidence
        factors = self._identify_confidence_factors(alert, {
            "data_completeness": data_completeness,
            "data_consistency": data_consistency,
            "source_reliability": source_reliability,
            "temporal_validity": temporal_validity,
            "geographic_validity": geographic_validity,
            "content_quality": content_quality
        })
        
        return ConfidenceScore(
            alert=alert,
            overall_confidence=overall_confidence,
            component_scores={
                "data_completeness": data_completeness,
                "data_consistency": data_consistency,
                "source_reliability": source_reliability,
                "temporal_validity": temporal_validity,
                "geographic_validity": geographic_validity,
                "content_quality": content_quality
            },
            factors=factors,
            calculated_at=datetime.now(timezone.utc)
        )
    
    def _validate_alert_id(self, alert: WeatherAlert) -> Dict[str, Any]:
        """Validate alert ID format."""
        issues = []
        recommendations = []
        
        if not alert.id:
            issues.append("Alert ID is missing")
            recommendations.append("Ensure alert has a valid ID")
            return {"check": "alert_id", "passed": False, "issues": issues, "recommendations": recommendations}
        
        if not self.alert_id_pattern.match(alert.id):
            issues.append(f"Alert ID format is invalid: {alert.id}")
            recommendations.append("Use alphanumeric characters, hyphens, and underscores only")
        
        return {
            "check": "alert_id",
            "passed": len(issues) == 0,
            "issues": issues,
            "recommendations": recommendations
        }
    
    def _validate_basic_fields(self, alert: WeatherAlert) -> Dict[str, Any]:
        """Validate basic required fields."""
        issues = []
        recommendations = []
        
        if not alert.event:
            issues.append("Event field is missing")
            recommendations.append("Ensure alert has an event description")
        
        if not alert.area_desc:
            issues.append("Area description is missing")
            recommendations.append("Ensure alert has an area description")
        
        if not alert.description:
            issues.append("Description field is missing")
            recommendations.append("Ensure alert has a description")
        
        if not alert.sender:
            issues.append("Sender field is missing")
            recommendations.append("Ensure alert has a sender")
        
        return {
            "check": "basic_fields",
            "passed": len(issues) == 0,
            "issues": issues,
            "recommendations": recommendations
        }
    
    def _validate_enum_values(self, alert: WeatherAlert) -> Dict[str, Any]:
        """Validate enum field values."""
        issues = []
        recommendations = []
        
        if alert.severity.value not in self.valid_severities:
            issues.append(f"Invalid severity: {alert.severity.value}")
            recommendations.append(f"Use one of: {', '.join(self.valid_severities)}")
        
        if alert.urgency.value not in self.valid_urgencies:
            issues.append(f"Invalid urgency: {alert.urgency.value}")
            recommendations.append(f"Use one of: {', '.join(self.valid_urgencies)}")
        
        if alert.certainty.value not in self.valid_certainties:
            issues.append(f"Invalid certainty: {alert.certainty.value}")
            recommendations.append(f"Use one of: {', '.join(self.valid_certainties)}")
        
        if alert.status.value not in self.valid_statuses:
            issues.append(f"Invalid status: {alert.status.value}")
            recommendations.append(f"Use one of: {', '.join(self.valid_statuses)}")
        
        if alert.category.value not in self.valid_categories:
            issues.append(f"Invalid category: {alert.category.value}")
            recommendations.append(f"Use one of: {', '.join(self.valid_categories)}")
        
        return {
            "check": "enum_values",
            "passed": len(issues) == 0,
            "issues": issues,
            "recommendations": recommendations
        }
    
    def _validate_dates(self, alert: WeatherAlert) -> Dict[str, Any]:
        """Validate date fields."""
        issues = []
        recommendations = []
        
        now = datetime.now(timezone.utc)
        
        # Check sent date
        if not alert.sent:
            issues.append("Sent date is missing")
            recommendations.append("Ensure alert has a sent date")
        elif alert.sent > now:
            issues.append("Sent date is in the future")
            recommendations.append("Check sent date accuracy")
        
        # Check effective date
        if not alert.effective:
            issues.append("Effective date is missing")
            recommendations.append("Ensure alert has an effective date")
        elif alert.effective > now + timedelta(hours=24):
            issues.append("Effective date is more than 24 hours in the future")
            recommendations.append("Check effective date accuracy")
        
        # Check expires date
        if not alert.expires:
            issues.append("Expires date is missing")
            recommendations.append("Ensure alert has an expires date")
        elif alert.expires < now:
            issues.append("Alert has already expired")
            recommendations.append("Check if alert should still be active")
        elif alert.expires < alert.effective:
            issues.append("Expires date is before effective date")
            recommendations.append("Check date consistency")
        
        # Check onset date
        if alert.onset and alert.onset > now + timedelta(hours=24):
            issues.append("Onset date is more than 24 hours in the future")
            recommendations.append("Check onset date accuracy")
        
        # Check ends date
        if alert.ends and alert.ends < alert.effective:
            issues.append("Ends date is before effective date")
            recommendations.append("Check date consistency")
        
        return {
            "check": "dates",
            "passed": len(issues) == 0,
            "issues": issues,
            "recommendations": recommendations
        }
    
    def _validate_geographic_data(self, alert: WeatherAlert) -> Dict[str, Any]:
        """Validate geographic data."""
        issues = []
        recommendations = []
        
        # Check county codes
        if alert.county_codes:
            for county_code in alert.county_codes:
                if not self.county_code_pattern.match(county_code):
                    issues.append(f"Invalid county code format: {county_code}")
                    recommendations.append("Use format: STC### (e.g., TXC039)")
        
        # Check geocode data
        if alert.geocode:
            if not isinstance(alert.geocode, list):
                issues.append("Geocode should be a list")
                recommendations.append("Format geocode as a list of strings")
            elif len(alert.geocode) == 0:
                issues.append("Geocode list is empty")
                recommendations.append("Include geocode data if available")
        
        return {
            "check": "geographic_data",
            "passed": len(issues) == 0,
            "issues": issues,
            "recommendations": recommendations
        }
    
    def _validate_content_quality(self, alert: WeatherAlert) -> Dict[str, Any]:
        """Validate content quality."""
        issues = []
        recommendations = []
        
        # Check event field
        if alert.event and len(alert.event.strip()) < 3:
            issues.append("Event description is too short")
            recommendations.append("Provide a more descriptive event name")
        
        # Check area description
        if alert.area_desc and len(alert.area_desc.strip()) < 5:
            issues.append("Area description is too short")
            recommendations.append("Provide a more detailed area description")
        
        # Check description
        if alert.description and len(alert.description.strip()) < 10:
            issues.append("Description is too short")
            recommendations.append("Provide a more detailed description")
        
        # Check for suspicious content
        suspicious_patterns = [
            r'test\s+alert',
            r'example\s+alert',
            r'dummy\s+alert',
            r'fake\s+alert'
        ]
        
        content_to_check = f"{alert.event} {alert.headline or ''} {alert.description}".lower()
        for pattern in suspicious_patterns:
            if re.search(pattern, content_to_check):
                issues.append("Alert content appears to be test data")
                recommendations.append("Verify alert is legitimate")
        
        return {
            "check": "content_quality",
            "passed": len(issues) == 0,
            "issues": issues,
            "recommendations": recommendations
        }
    
    def _validate_consistency(self, alert: WeatherAlert) -> Dict[str, Any]:
        """Validate data consistency."""
        issues = []
        recommendations = []
        
        # Check severity vs urgency consistency
        if alert.severity == AlertSeverity.EXTREME and alert.urgency != AlertUrgency.IMMEDIATE:
            issues.append("Extreme severity should typically have immediate urgency")
            recommendations.append("Review severity and urgency alignment")
        
        if alert.severity == AlertSeverity.MINOR and alert.urgency == AlertUrgency.IMMEDIATE:
            issues.append("Minor severity with immediate urgency may be inconsistent")
            recommendations.append("Review severity and urgency alignment")
        
        # Check certainty vs urgency consistency
        if alert.certainty == AlertCertainty.OBSERVED and alert.urgency == AlertUrgency.FUTURE:
            issues.append("Observed certainty with future urgency may be inconsistent")
            recommendations.append("Review certainty and urgency alignment")
        
        # Check date consistency
        if alert.onset and alert.effective and alert.onset > alert.effective:
            issues.append("Onset date is after effective date")
            recommendations.append("Check date consistency")
        
        if alert.ends and alert.expires and alert.ends > alert.expires:
            issues.append("Ends date is after expires date")
            recommendations.append("Check date consistency")
        
        return {
            "check": "consistency",
            "passed": len(issues) == 0,
            "issues": issues,
            "recommendations": recommendations
        }
    
    def _validate_anomalies(self, alert: WeatherAlert) -> Dict[str, Any]:
        """Validate for anomalies."""
        issues = []
        recommendations = []
        
        # Check for unusually long descriptions
        if alert.description and len(alert.description) > 5000:
            issues.append("Description is unusually long")
            recommendations.append("Review description length")
        
        # Check for unusually short descriptions
        if alert.description and len(alert.description) < 20:
            issues.append("Description is unusually short")
            recommendations.append("Provide more detailed description")
        
        # Check for missing critical information
        if alert.severity == AlertSeverity.EXTREME and not alert.instruction:
            issues.append("Extreme severity alert missing instructions")
            recommendations.append("Include safety instructions for extreme alerts")
        
        # Check for suspicious timing
        now = datetime.now(timezone.utc)
        if alert.sent and (now - alert.sent).total_seconds() < 60:
            issues.append("Alert sent very recently (within 1 minute)")
            recommendations.append("Verify alert timing")
        
        return {
            "check": "anomalies",
            "passed": len(issues) == 0,
            "issues": issues,
            "recommendations": recommendations
        }
    
    def _calculate_confidence_score(self, alert: WeatherAlert, validation_checks: List[Dict[str, Any]]) -> float:
        """Calculate overall confidence score."""
        if not validation_checks:
            return 0.0
        
        # Count passed checks
        passed_checks = sum(1 for check in validation_checks if check.get("passed", False))
        total_checks = len(validation_checks)
        
        # Base confidence on check pass rate
        base_confidence = passed_checks / total_checks if total_checks > 0 else 0.0
        
        # Adjust for specific factors
        adjustments = []
        
        # Data completeness adjustment
        if alert.event and alert.area_desc and alert.description:
            adjustments.append(0.1)
        
        # Source reliability adjustment
        if alert.sender and "NWS" in alert.sender.upper():
            adjustments.append(0.1)
        
        # Temporal validity adjustment
        now = datetime.now(timezone.utc)
        if alert.sent and (now - alert.sent).total_seconds() < 3600:  # Within 1 hour
            adjustments.append(0.1)
        
        # Apply adjustments
        confidence = base_confidence + sum(adjustments)
        
        return min(confidence, 1.0)
    
    def _determine_confidence_level(self, confidence_score: float) -> ConfidenceLevel:
        """Determine confidence level from score."""
        if confidence_score >= 0.9:
            return ConfidenceLevel.VERY_HIGH
        elif confidence_score >= 0.8:
            return ConfidenceLevel.HIGH
        elif confidence_score >= 0.6:
            return ConfidenceLevel.MEDIUM
        elif confidence_score >= 0.4:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.VERY_LOW
    
    def _determine_validation_status(self, confidence_score: float, issues: List[str]) -> ValidationStatus:
        """Determine validation status."""
        if confidence_score >= self.min_confidence_threshold and len(issues) == 0:
            return ValidationStatus.VALID
        elif confidence_score >= self.min_confidence_threshold and len(issues) <= 2:
            return ValidationStatus.SUSPICIOUS
        elif len(issues) > 5:
            return ValidationStatus.INVALID
        else:
            return ValidationStatus.UNKNOWN
    
    def _calculate_data_completeness(self, alert: WeatherAlert) -> float:
        """Calculate data completeness score."""
        required_fields = [
            alert.id, alert.event, alert.area_desc, alert.description,
            alert.sent, alert.effective, alert.expires, alert.sender
        ]
        
        optional_fields = [
            alert.headline, alert.instruction, alert.onset, alert.ends,
            alert.geocode, alert.county_codes, alert.sender_name
        ]
        
        required_score = sum(1 for field in required_fields if field) / len(required_fields)
        optional_score = sum(1 for field in optional_fields if field) / len(optional_fields)
        
        return (required_score * 0.8) + (optional_score * 0.2)
    
    def _calculate_data_consistency(self, alert: WeatherAlert) -> float:
        """Calculate data consistency score."""
        score = 1.0
        
        # Check date consistency
        if alert.onset and alert.effective and alert.onset > alert.effective:
            score -= 0.2
        
        if alert.ends and alert.expires and alert.ends > alert.expires:
            score -= 0.2
        
        # Check severity/urgency consistency
        if alert.severity == AlertSeverity.EXTREME and alert.urgency != AlertUrgency.IMMEDIATE:
            score -= 0.1
        
        return max(score, 0.0)
    
    def _calculate_source_reliability(self, alert: WeatherAlert) -> float:
        """Calculate source reliability score."""
        if not alert.sender:
            return 0.0
        
        sender_upper = alert.sender.upper()
        
        if "NWS" in sender_upper:
            return 1.0
        elif "NOAA" in sender_upper:
            return 0.9
        elif "WEATHER" in sender_upper:
            return 0.7
        else:
            return 0.5
    
    def _calculate_temporal_validity(self, alert: WeatherAlert) -> float:
        """Calculate temporal validity score."""
        now = datetime.now(timezone.utc)
        score = 1.0
        
        # Check if alert is too old
        if alert.sent and (now - alert.sent).total_seconds() > 86400:  # 24 hours
            score -= 0.3
        
        # Check if alert is expired
        if alert.expires and alert.expires < now:
            score -= 0.5
        
        return max(score, 0.0)
    
    def _calculate_geographic_validity(self, alert: WeatherAlert) -> float:
        """Calculate geographic validity score."""
        score = 1.0
        
        # Check county codes format
        if alert.county_codes:
            invalid_counties = [cc for cc in alert.county_codes if not self.county_code_pattern.match(cc)]
            if invalid_counties:
                score -= 0.2 * (len(invalid_counties) / len(alert.county_codes))
        
        return max(score, 0.0)
    
    def _calculate_content_quality(self, alert: WeatherAlert) -> float:
        """Calculate content quality score."""
        score = 1.0
        
        # Check description length
        if alert.description:
            if len(alert.description) < 20:
                score -= 0.3
            elif len(alert.description) > 5000:
                score -= 0.1
        
        # Check for test content
        content = f"{alert.event} {alert.description}".lower()
        if any(word in content for word in ["test", "example", "dummy", "fake"]):
            score -= 0.5
        
        return max(score, 0.0)
    
    def _identify_confidence_factors(self, alert: WeatherAlert, scores: Dict[str, float]) -> List[str]:
        """Identify factors affecting confidence."""
        factors = []
        
        if scores.get("data_completeness", 0) >= 0.9:
            factors.append("High data completeness")
        elif scores.get("data_completeness", 0) <= 0.5:
            factors.append("Low data completeness")
        
        if scores.get("source_reliability", 0) >= 0.9:
            factors.append("Reliable source")
        elif scores.get("source_reliability", 0) <= 0.5:
            factors.append("Unreliable source")
        
        if scores.get("temporal_validity", 0) >= 0.8:
            factors.append("Recent alert")
        elif scores.get("temporal_validity", 0) <= 0.3:
            factors.append("Aged alert")
        
        if scores.get("geographic_validity", 0) >= 0.9:
            factors.append("Valid geographic data")
        elif scores.get("geographic_validity", 0) <= 0.5:
            factors.append("Invalid geographic data")
        
        return factors
