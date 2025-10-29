"""
Alert deduplication and merging system for SkywarnPlus-NG.
"""

import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass
from enum import Enum
import difflib

from ..core.models import WeatherAlert

logger = logging.getLogger(__name__)


class DuplicateDetectionStrategy(Enum):
    """Strategies for detecting duplicate alerts."""
    EXACT_MATCH = "exact_match"
    SIMILARITY_THRESHOLD = "similarity_threshold"
    TIME_WINDOW = "time_window"
    GEOGRAPHIC_OVERLAP = "geographic_overlap"
    HYBRID = "hybrid"


@dataclass
class DuplicateMatch:
    """Represents a duplicate match between alerts."""
    
    alert1: WeatherAlert
    alert2: WeatherAlert
    similarity_score: float
    match_type: str
    confidence: float
    metadata: Dict[str, Any]
    
    def __post_init__(self):
        if not self.metadata:
            self.metadata = {}


@dataclass
class MergedAlert:
    """Represents a merged alert."""
    
    primary_alert: WeatherAlert
    merged_alerts: List[WeatherAlert]
    merged_at: datetime
    merge_reason: str
    metadata: Dict[str, Any]
    
    def __post_init__(self):
        if not self.merged_at:
            self.merged_at = datetime.now(timezone.utc)
        if not self.metadata:
            self.metadata = {}


class AlertDeduplicator:
    """Deduplicates and merges similar alerts."""
    
    def __init__(
        self,
        strategy: DuplicateDetectionStrategy = DuplicateDetectionStrategy.HYBRID,
        similarity_threshold: float = 0.8,
        time_window_minutes: int = 30,
        geographic_overlap_threshold: float = 0.5,
        max_merge_distance_km: float = 50.0
    ):
        self.strategy = strategy
        self.similarity_threshold = similarity_threshold
        self.time_window_minutes = time_window_minutes
        self.geographic_overlap_threshold = geographic_overlap_threshold
        self.max_merge_distance_km = max_merge_distance_km
        self.logger = logging.getLogger(__name__)
        
        # Cache for processed alerts
        self._processed_alerts: Dict[str, WeatherAlert] = {}
        self._alert_hashes: Dict[str, str] = {}
    
    def deduplicate_alerts(self, alerts: List[WeatherAlert]) -> List[WeatherAlert]:
        """
        Deduplicate a list of alerts.
        
        Args:
            alerts: List of alerts to deduplicate
            
        Returns:
            List of deduplicated alerts
        """
        if not alerts:
            return []
        
        self.logger.info(f"Deduplicating {len(alerts)} alerts using {self.strategy.value} strategy")
        
        # Find duplicates
        duplicates = self._find_duplicates(alerts)
        
        # Merge duplicates
        merged_alerts = self._merge_duplicates(duplicates)
        
        # Create final list
        deduplicated = []
        processed_ids = set()
        
        for alert in alerts:
            if alert.id in processed_ids:
                continue
            
            # Check if this alert was merged
            merged_alert = self._get_merged_alert(alert, merged_alerts)
            if merged_alert:
                deduplicated.append(merged_alert)
                # Mark all merged alerts as processed
                for merged in merged_alert.merged_alerts:
                    processed_ids.add(merged.id)
                processed_ids.add(alert.id)
            else:
                deduplicated.append(alert)
                processed_ids.add(alert.id)
        
        self.logger.info(f"Deduplication complete: {len(alerts)} -> {len(deduplicated)} alerts")
        return deduplicated
    
    def _find_duplicates(self, alerts: List[WeatherAlert]) -> List[DuplicateMatch]:
        """Find duplicate alerts using the configured strategy."""
        duplicates = []
        
        if self.strategy == DuplicateDetectionStrategy.EXACT_MATCH:
            duplicates = self._find_exact_matches(alerts)
        elif self.strategy == DuplicateDetectionStrategy.SIMILARITY_THRESHOLD:
            duplicates = self._find_similarity_matches(alerts)
        elif self.strategy == DuplicateDetectionStrategy.TIME_WINDOW:
            duplicates = self._find_time_window_matches(alerts)
        elif self.strategy == DuplicateDetectionStrategy.GEOGRAPHIC_OVERLAP:
            duplicates = self._find_geographic_matches(alerts)
        elif self.strategy == DuplicateDetectionStrategy.HYBRID:
            duplicates = self._find_hybrid_matches(alerts)
        
        return duplicates
    
    def _find_exact_matches(self, alerts: List[WeatherAlert]) -> List[DuplicateMatch]:
        """Find exact matches based on alert content."""
        duplicates = []
        seen_hashes = {}
        
        for alert in alerts:
            alert_hash = self._calculate_alert_hash(alert)
            
            if alert_hash in seen_hashes:
                # Found exact duplicate
                original_alert = seen_hashes[alert_hash]
                match = DuplicateMatch(
                    alert1=original_alert,
                    alert2=alert,
                    similarity_score=1.0,
                    match_type="exact",
                    confidence=1.0,
                    metadata={"hash": alert_hash}
                )
                duplicates.append(match)
            else:
                seen_hashes[alert_hash] = alert
        
        return duplicates
    
    def _find_similarity_matches(self, alerts: List[WeatherAlert]) -> List[DuplicateMatch]:
        """Find similar alerts based on text similarity."""
        duplicates = []
        
        for i, alert1 in enumerate(alerts):
            for alert2 in alerts[i+1:]:
                similarity = self._calculate_similarity(alert1, alert2)
                
                if similarity >= self.similarity_threshold:
                    match = DuplicateMatch(
                        alert1=alert1,
                        alert2=alert2,
                        similarity_score=similarity,
                        match_type="similarity",
                        confidence=similarity,
                        metadata={"threshold": self.similarity_threshold}
                    )
                    duplicates.append(match)
        
        return duplicates
    
    def _find_time_window_matches(self, alerts: List[WeatherAlert]) -> List[DuplicateMatch]:
        """Find alerts within a time window that might be duplicates."""
        duplicates = []
        time_window = timedelta(minutes=self.time_window_minutes)
        
        for i, alert1 in enumerate(alerts):
            for alert2 in alerts[i+1:]:
                if self._are_within_time_window(alert1, alert2, time_window):
                    similarity = self._calculate_similarity(alert1, alert2)
                    
                    if similarity >= 0.5:  # Lower threshold for time-based matching
                        match = DuplicateMatch(
                            alert1=alert1,
                            alert2=alert2,
                            similarity_score=similarity,
                            match_type="time_window",
                            confidence=similarity * 0.8,  # Lower confidence for time-based
                            metadata={
                                "time_window_minutes": self.time_window_minutes,
                                "time_diff_minutes": self._get_time_difference_minutes(alert1, alert2)
                            }
                        )
                        duplicates.append(match)
        
        return duplicates
    
    def _find_geographic_matches(self, alerts: List[WeatherAlert]) -> List[DuplicateMatch]:
        """Find alerts with geographic overlap."""
        duplicates = []
        
        for i, alert1 in enumerate(alerts):
            for alert2 in alerts[i+1:]:
                if self._have_geographic_overlap(alert1, alert2):
                    similarity = self._calculate_similarity(alert1, alert2)
                    
                    if similarity >= 0.6:  # Medium threshold for geographic matching
                        match = DuplicateMatch(
                            alert1=alert1,
                            alert2=alert2,
                            similarity_score=similarity,
                            match_type="geographic",
                            confidence=similarity * 0.9,
                            metadata={"geographic_overlap": True}
                        )
                        duplicates.append(match)
        
        return duplicates
    
    def _find_hybrid_matches(self, alerts: List[WeatherAlert]) -> List[DuplicateMatch]:
        """Find duplicates using a combination of strategies."""
        duplicates = []
        
        # First, find exact matches
        exact_matches = self._find_exact_matches(alerts)
        duplicates.extend(exact_matches)
        
        # Then, find similarity matches for non-exact alerts
        non_exact_alerts = self._get_non_exact_alerts(alerts, exact_matches)
        similarity_matches = self._find_similarity_matches(non_exact_alerts)
        duplicates.extend(similarity_matches)
        
        # Finally, find time window matches for remaining alerts
        remaining_alerts = self._get_remaining_alerts(non_exact_alerts, similarity_matches)
        time_matches = self._find_time_window_matches(remaining_alerts)
        duplicates.extend(time_matches)
        
        return duplicates
    
    def _merge_duplicates(self, duplicates: List[DuplicateMatch]) -> List[MergedAlert]:
        """Merge duplicate alerts."""
        merged_alerts = []
        processed_alerts = set()
        
        for match in duplicates:
            # Skip if either alert was already processed
            if match.alert1.id in processed_alerts or match.alert2.id in processed_alerts:
                continue
            
            # Determine primary alert (keep the more recent or higher severity)
            primary_alert = self._select_primary_alert(match.alert1, match.alert2)
            secondary_alert = match.alert2 if primary_alert == match.alert1 else match.alert1
            
            # Create merged alert
            merged_alert = MergedAlert(
                primary_alert=primary_alert,
                merged_alerts=[secondary_alert],
                merge_reason=f"{match.match_type} match (similarity: {match.similarity_score:.2f})",
                metadata={
                    "similarity_score": match.similarity_score,
                    "match_type": match.match_type,
                    "confidence": match.confidence,
                    **match.metadata
                }
            )
            
            merged_alerts.append(merged_alert)
            processed_alerts.add(match.alert1.id)
            processed_alerts.add(match.alert2.id)
        
        return merged_alerts
    
    def _calculate_alert_hash(self, alert: WeatherAlert) -> str:
        """Calculate a hash for alert content."""
        # Create a string representation of key alert fields
        content = f"{alert.event}|{alert.area_desc}|{alert.severity.value}|{alert.urgency.value}|{alert.certainty.value}"
        
        # Add county codes if available
        if alert.county_codes:
            content += "|" + "|".join(sorted(alert.county_codes))
        
        return hashlib.md5(content.encode()).hexdigest()
    
    def _calculate_similarity(self, alert1: WeatherAlert, alert2: WeatherAlert) -> float:
        """Calculate similarity between two alerts."""
        # Compare event names
        event_similarity = difflib.SequenceMatcher(
            None, alert1.event.lower(), alert2.event.lower()
        ).ratio()
        
        # Compare area descriptions
        area_similarity = difflib.SequenceMatcher(
            None, alert1.area_desc.lower(), alert2.area_desc.lower()
        ).ratio()
        
        # Compare descriptions
        desc_similarity = 0.0
        if alert1.description and alert2.description:
            desc_similarity = difflib.SequenceMatcher(
                None, alert1.description.lower(), alert2.description.lower()
            ).ratio()
        
        # Weighted average
        similarity = (
            event_similarity * 0.4 +
            area_similarity * 0.3 +
            desc_similarity * 0.3
        )
        
        return similarity
    
    def _are_within_time_window(self, alert1: WeatherAlert, alert2: WeatherAlert, window: timedelta) -> bool:
        """Check if two alerts are within the specified time window."""
        time1 = alert1.effective or alert1.sent
        time2 = alert2.effective or alert2.sent
        
        if not time1 or not time2:
            return False
        
        # Ensure both times are timezone-aware
        if time1.tzinfo is None:
            time1 = time1.replace(tzinfo=timezone.utc)
        if time2.tzinfo is None:
            time2 = time2.replace(tzinfo=timezone.utc)
        
        return abs((time1 - time2).total_seconds()) <= window.total_seconds()
    
    def _get_time_difference_minutes(self, alert1: WeatherAlert, alert2: WeatherAlert) -> float:
        """Get time difference between two alerts in minutes."""
        time1 = alert1.effective or alert1.sent
        time2 = alert2.effective or alert2.sent
        
        if not time1 or not time2:
            return float('inf')
        
        # Ensure both times are timezone-aware
        if time1.tzinfo is None:
            time1 = time1.replace(tzinfo=timezone.utc)
        if time2.tzinfo is None:
            time2 = time2.replace(tzinfo=timezone.utc)
        
        return abs((time1 - time2).total_seconds()) / 60.0
    
    def _have_geographic_overlap(self, alert1: WeatherAlert, alert2: WeatherAlert) -> bool:
        """Check if two alerts have geographic overlap."""
        # This is a simplified implementation
        # In a real implementation, you'd parse the geocode data and check for overlap
        
        # Check county codes overlap
        if alert1.county_codes and alert2.county_codes:
            overlap = set(alert1.county_codes) & set(alert2.county_codes)
            if overlap:
                return True
        
        # Check area description similarity
        area_similarity = difflib.SequenceMatcher(
            None, alert1.area_desc.lower(), alert2.area_desc.lower()
        ).ratio()
        
        return area_similarity >= self.geographic_overlap_threshold
    
    def _select_primary_alert(self, alert1: WeatherAlert, alert2: WeatherAlert) -> WeatherAlert:
        """Select the primary alert from two similar alerts."""
        # Prefer more recent alert
        time1 = alert1.effective or alert1.sent
        time2 = alert2.effective or alert2.sent
        
        if time1 and time2:
            if time1 > time2:
                return alert1
            elif time2 > time1:
                return alert2
        
        # Prefer higher severity
        severity_order = {
            "Minor": 1,
            "Moderate": 2,
            "Severe": 3,
            "Extreme": 4
        }
        
        severity1 = severity_order.get(alert1.severity.value, 0)
        severity2 = severity_order.get(alert2.severity.value, 0)
        
        if severity1 > severity2:
            return alert1
        elif severity2 > severity1:
            return alert2
        
        # Prefer higher urgency
        urgency_order = {
            "Past": 1,
            "Future": 2,
            "Expected": 3,
            "Immediate": 4
        }
        
        urgency1 = urgency_order.get(alert1.urgency.value, 0)
        urgency2 = urgency_order.get(alert2.urgency.value, 0)
        
        if urgency1 > urgency2:
            return alert1
        elif urgency2 > urgency1:
            return alert2
        
        # Default to first alert
        return alert1
    
    def _get_non_exact_alerts(self, alerts: List[WeatherAlert], exact_matches: List[DuplicateMatch]) -> List[WeatherAlert]:
        """Get alerts that are not part of exact matches."""
        exact_alert_ids = set()
        for match in exact_matches:
            exact_alert_ids.add(match.alert1.id)
            exact_alert_ids.add(match.alert2.id)
        
        return [alert for alert in alerts if alert.id not in exact_alert_ids]
    
    def _get_remaining_alerts(self, alerts: List[WeatherAlert], matches: List[DuplicateMatch]) -> List[WeatherAlert]:
        """Get alerts that are not part of the given matches."""
        matched_alert_ids = set()
        for match in matches:
            matched_alert_ids.add(match.alert1.id)
            matched_alert_ids.add(match.alert2.id)
        
        return [alert for alert in alerts if alert.id not in matched_alert_ids]
    
    def _get_merged_alert(self, alert: WeatherAlert, merged_alerts: List[MergedAlert]) -> Optional[WeatherAlert]:
        """Get the merged alert if the given alert was merged."""
        for merged_alert in merged_alerts:
            if alert.id == merged_alert.primary_alert.id:
                return merged_alert.primary_alert
            for merged in merged_alert.merged_alerts:
                if alert.id == merged.id:
                    return merged_alert.primary_alert
        
        return None
