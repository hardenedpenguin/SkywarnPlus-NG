"""
Alert prioritization and scoring system for SkywarnPlus-NG.
"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import math

from ..core.models import WeatherAlert, AlertSeverity, AlertUrgency, AlertCertainty

logger = logging.getLogger(__name__)


class PriorityLevel(Enum):
    """Priority levels for alerts."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class PriorityScore:
    """Priority score for an alert."""
    
    alert: WeatherAlert
    total_score: float
    priority_level: PriorityLevel
    component_scores: Dict[str, float]
    risk_factors: List[str]
    recommendations: List[str]
    calculated_at: datetime
    
    def __post_init__(self):
        if not self.calculated_at:
            self.calculated_at = datetime.now(timezone.utc)


@dataclass
class RiskAssessment:
    """Risk assessment for an alert."""
    
    alert: WeatherAlert
    risk_level: str
    impact_score: float
    probability_score: float
    urgency_score: float
    factors: List[str]
    mitigation_actions: List[str]
    calculated_at: datetime
    
    def __post_init__(self):
        if not self.calculated_at:
            self.calculated_at = datetime.now(timezone.utc)


class AlertPrioritizer:
    """Prioritizes alerts based on various factors."""
    
    def __init__(
        self,
        severity_weights: Optional[Dict[str, float]] = None,
        urgency_weights: Optional[Dict[str, float]] = None,
        certainty_weights: Optional[Dict[str, float]] = None,
        time_decay_factor: float = 0.1,
        geographic_risk_multiplier: float = 1.0,
        population_density_weight: float = 0.3
    ):
        self.severity_weights = severity_weights or {
            "Minor": 1.0,
            "Moderate": 2.0,
            "Severe": 4.0,
            "Extreme": 8.0
        }
        self.urgency_weights = urgency_weights or {
            "Past": 0.1,
            "Future": 0.5,
            "Expected": 1.0,
            "Immediate": 2.0
        }
        self.certainty_weights = certainty_weights or {
            "Unlikely": 0.2,
            "Possible": 0.5,
            "Likely": 0.8,
            "Observed": 1.0
        }
        self.time_decay_factor = time_decay_factor
        self.geographic_risk_multiplier = geographic_risk_multiplier
        self.population_density_weight = population_density_weight
        self.logger = logging.getLogger(__name__)
    
    def prioritize_alert(self, alert: WeatherAlert) -> PriorityScore:
        """
        Calculate priority score for an alert.
        
        Args:
            alert: Weather alert to prioritize
            
        Returns:
            Priority score
        """
        self.logger.debug(f"Prioritizing alert {alert.id}: {alert.event}")
        
        # Calculate component scores
        severity_score = self._calculate_severity_score(alert)
        urgency_score = self._calculate_urgency_score(alert)
        certainty_score = self._calculate_certainty_score(alert)
        time_score = self._calculate_time_score(alert)
        geographic_score = self._calculate_geographic_score(alert)
        population_score = self._calculate_population_score(alert)
        
        # Calculate total score
        total_score = (
            severity_score * 0.3 +
            urgency_score * 0.25 +
            certainty_score * 0.15 +
            time_score * 0.1 +
            geographic_score * 0.1 +
            population_score * 0.1
        )
        
        # Determine priority level
        priority_level = self._determine_priority_level(total_score)
        
        # Identify risk factors
        risk_factors = self._identify_risk_factors(alert, {
            "severity": severity_score,
            "urgency": urgency_score,
            "certainty": certainty_score,
            "time": time_score,
            "geographic": geographic_score,
            "population": population_score
        })
        
        # Generate recommendations
        recommendations = self._generate_recommendations(alert, priority_level, risk_factors)
        
        return PriorityScore(
            alert=alert,
            total_score=total_score,
            priority_level=priority_level,
            component_scores={
                "severity": severity_score,
                "urgency": urgency_score,
                "certainty": certainty_score,
                "time": time_score,
                "geographic": geographic_score,
                "population": population_score
            },
            risk_factors=risk_factors,
            recommendations=recommendations,
            calculated_at=datetime.now(timezone.utc)
        )
    
    def prioritize_alerts(self, alerts: List[WeatherAlert]) -> List[PriorityScore]:
        """
        Prioritize a list of alerts.
        
        Args:
            alerts: List of alerts to prioritize
            
        Returns:
            List of priority scores, sorted by priority
        """
        self.logger.info(f"Prioritizing {len(alerts)} alerts")
        
        priority_scores = []
        for alert in alerts:
            try:
                score = self.prioritize_alert(alert)
                priority_scores.append(score)
            except Exception as e:
                self.logger.error(f"Failed to prioritize alert {alert.id}: {e}")
                continue
        
        # Sort by total score (descending)
        priority_scores.sort(key=lambda x: x.total_score, reverse=True)
        
        self.logger.info(f"Prioritized {len(priority_scores)} alerts")
        return priority_scores
    
    def assess_risk(self, alert: WeatherAlert) -> RiskAssessment:
        """
        Assess risk level for an alert.
        
        Args:
            alert: Weather alert to assess
            
        Returns:
            Risk assessment
        """
        self.logger.debug(f"Assessing risk for alert {alert.id}: {alert.event}")
        
        # Calculate impact score
        impact_score = self._calculate_impact_score(alert)
        
        # Calculate probability score
        probability_score = self._calculate_probability_score(alert)
        
        # Calculate urgency score
        urgency_score = self._calculate_urgency_score(alert)
        
        # Determine risk level
        risk_level = self._determine_risk_level(impact_score, probability_score, urgency_score)
        
        # Identify risk factors
        factors = self._identify_risk_factors(alert, {
            "impact": impact_score,
            "probability": probability_score,
            "urgency": urgency_score
        })
        
        # Generate mitigation actions
        mitigation_actions = self._generate_mitigation_actions(alert, risk_level, factors)
        
        return RiskAssessment(
            alert=alert,
            risk_level=risk_level,
            impact_score=impact_score,
            probability_score=probability_score,
            urgency_score=urgency_score,
            factors=factors,
            mitigation_actions=mitigation_actions,
            calculated_at=datetime.now(timezone.utc)
        )
    
    def _calculate_severity_score(self, alert: WeatherAlert) -> float:
        """Calculate severity score."""
        return self.severity_weights.get(alert.severity.value, 1.0)
    
    def _calculate_urgency_score(self, alert: WeatherAlert) -> float:
        """Calculate urgency score."""
        return self.urgency_weights.get(alert.urgency.value, 1.0)
    
    def _calculate_certainty_score(self, alert: WeatherAlert) -> float:
        """Calculate certainty score."""
        return self.certainty_weights.get(alert.certainty.value, 1.0)
    
    def _calculate_time_score(self, alert: WeatherAlert) -> float:
        """Calculate time-based score."""
        now = datetime.now(timezone.utc)
        alert_time = alert.effective or alert.sent
        
        if not alert_time:
            return 1.0
        
        # Ensure timezone-aware
        if alert_time.tzinfo is None:
            alert_time = alert_time.replace(tzinfo=timezone.utc)
        
        # Calculate time difference in hours
        time_diff_hours = (now - alert_time).total_seconds() / 3600
        
        # Apply time decay
        time_score = math.exp(-self.time_decay_factor * time_diff_hours)
        
        return min(time_score, 1.0)
    
    def _calculate_geographic_score(self, alert: WeatherAlert) -> float:
        """Calculate geographic risk score."""
        # This is a simplified implementation
        # In a real implementation, you'd consider:
        # - Population density
        # - Critical infrastructure
        # - Historical impact data
        # - Geographic vulnerability
        
        base_score = 1.0
        
        # Check for high-risk keywords in area description
        high_risk_keywords = [
            "downtown", "city center", "airport", "hospital", "school",
            "university", "stadium", "shopping", "business district"
        ]
        
        area_desc_lower = alert.area_desc.lower()
        for keyword in high_risk_keywords:
            if keyword in area_desc_lower:
                base_score *= self.geographic_risk_multiplier
                break
        
        return min(base_score, 5.0)  # Cap at 5.0
    
    def _calculate_population_score(self, alert: WeatherAlert) -> float:
        """Calculate population density score."""
        # This is a simplified implementation
        # In a real implementation, you'd use actual population data
        
        base_score = 1.0
        
        # Check for population-related keywords
        population_keywords = [
            "metropolitan", "urban", "city", "town", "downtown",
            "residential", "suburban", "densely populated"
        ]
        
        area_desc_lower = alert.area_desc.lower()
        for keyword in population_keywords:
            if keyword in area_desc_lower:
                base_score += self.population_density_weight
                break
        
        return min(base_score, 3.0)  # Cap at 3.0
    
    def _calculate_impact_score(self, alert: WeatherAlert) -> float:
        """Calculate potential impact score."""
        # Combine severity and geographic factors
        severity_score = self._calculate_severity_score(alert)
        geographic_score = self._calculate_geographic_score(alert)
        population_score = self._calculate_population_score(alert)
        
        return (severity_score + geographic_score + population_score) / 3.0
    
    def _calculate_probability_score(self, alert: WeatherAlert) -> float:
        """Calculate probability score."""
        # Based on certainty and urgency
        certainty_score = self._calculate_certainty_score(alert)
        urgency_score = self._calculate_urgency_score(alert)
        
        return (certainty_score + urgency_score) / 2.0
    
    def _determine_priority_level(self, total_score: float) -> PriorityLevel:
        """Determine priority level based on total score."""
        if total_score >= 6.0:
            return PriorityLevel.CRITICAL
        elif total_score >= 4.0:
            return PriorityLevel.HIGH
        elif total_score >= 2.0:
            return PriorityLevel.MEDIUM
        elif total_score >= 1.0:
            return PriorityLevel.LOW
        else:
            return PriorityLevel.INFO
    
    def _determine_risk_level(self, impact_score: float, probability_score: float, urgency_score: float) -> str:
        """Determine risk level based on scores."""
        # Calculate risk matrix
        risk_score = (impact_score + probability_score + urgency_score) / 3.0
        
        if risk_score >= 4.0:
            return "Very High"
        elif risk_score >= 3.0:
            return "High"
        elif risk_score >= 2.0:
            return "Medium"
        elif risk_score >= 1.0:
            return "Low"
        else:
            return "Very Low"
    
    def _identify_risk_factors(self, alert: WeatherAlert, scores: Dict[str, float]) -> List[str]:
        """Identify risk factors for an alert."""
        factors = []
        
        # Severity factors
        if scores.get("severity", 0) >= 4.0:
            factors.append("High severity alert")
        elif scores.get("severity", 0) >= 2.0:
            factors.append("Moderate severity alert")
        
        # Urgency factors
        if scores.get("urgency", 0) >= 1.5:
            factors.append("Immediate or expected timing")
        elif scores.get("urgency", 0) >= 1.0:
            factors.append("Future timing")
        
        # Certainty factors
        if scores.get("certainty", 0) >= 0.8:
            factors.append("High certainty")
        elif scores.get("certainty", 0) >= 0.5:
            factors.append("Moderate certainty")
        
        # Geographic factors
        if scores.get("geographic", 0) >= 2.0:
            factors.append("High-risk geographic area")
        elif scores.get("geographic", 0) >= 1.5:
            factors.append("Moderate-risk geographic area")
        
        # Population factors
        if scores.get("population", 0) >= 2.0:
            factors.append("Densely populated area")
        
        # Time factors
        if scores.get("time", 0) >= 0.8:
            factors.append("Recent alert")
        elif scores.get("time", 0) <= 0.3:
            factors.append("Aged alert")
        
        return factors
    
    def _generate_recommendations(self, alert: WeatherAlert, priority_level: PriorityLevel, risk_factors: List[str]) -> List[str]:
        """Generate recommendations based on priority and risk factors."""
        recommendations = []
        
        # Priority-based recommendations
        if priority_level == PriorityLevel.CRITICAL:
            recommendations.extend([
                "Immediate response required",
                "Activate emergency protocols",
                "Notify all stakeholders immediately",
                "Consider evacuation procedures"
            ])
        elif priority_level == PriorityLevel.HIGH:
            recommendations.extend([
                "Urgent response required",
                "Notify key stakeholders",
                "Prepare for potential escalation",
                "Monitor situation closely"
            ])
        elif priority_level == PriorityLevel.MEDIUM:
            recommendations.extend([
                "Standard response procedures",
                "Notify relevant personnel",
                "Prepare contingency plans",
                "Regular monitoring"
            ])
        elif priority_level == PriorityLevel.LOW:
            recommendations.extend([
                "Routine monitoring",
                "Document for future reference",
                "No immediate action required"
            ])
        
        # Risk factor-based recommendations
        if "High severity alert" in risk_factors:
            recommendations.append("Implement high-priority response protocols")
        
        if "Immediate or expected timing" in risk_factors:
            recommendations.append("Prepare for immediate impact")
        
        if "High certainty" in risk_factors:
            recommendations.append("Proceed with confidence in response")
        
        if "High-risk geographic area" in risk_factors:
            recommendations.append("Focus resources on high-risk area")
        
        if "Densely populated area" in risk_factors:
            recommendations.append("Consider population protection measures")
        
        if "Aged alert" in risk_factors:
            recommendations.append("Verify alert is still relevant")
        
        return recommendations
    
    def _generate_mitigation_actions(self, alert: WeatherAlert, risk_level: str, factors: List[str]) -> List[str]:
        """Generate mitigation actions based on risk assessment."""
        actions = []
        
        # Risk level-based actions
        if risk_level in ["Very High", "High"]:
            actions.extend([
                "Activate emergency response team",
                "Implement immediate protective measures",
                "Evacuate high-risk areas if necessary",
                "Coordinate with emergency services"
            ])
        elif risk_level == "Medium":
            actions.extend([
                "Prepare response resources",
                "Monitor situation development",
                "Notify relevant authorities",
                "Implement standard protective measures"
            ])
        elif risk_level in ["Low", "Very Low"]:
            actions.extend([
                "Continue monitoring",
                "Prepare for potential escalation",
                "Document situation"
            ])
        
        # Factor-based actions
        if "High severity alert" in factors:
            actions.append("Deploy maximum available resources")
        
        if "Immediate or expected timing" in factors:
            actions.append("Execute immediate response protocols")
        
        if "High-risk geographic area" in factors:
            actions.append("Focus mitigation efforts on high-risk area")
        
        if "Densely populated area" in factors:
            actions.append("Implement population protection measures")
        
        return actions
