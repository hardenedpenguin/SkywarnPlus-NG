"""
Alert processing pipeline for SkywarnPlus-NG.
"""

from .deduplication import (
    AlertDeduplicator,
    DuplicateDetectionStrategy,
    collapse_superseded_nws_alerts,
    deduplicate_nws_active_alerts,
    merge_same_issuance_zone_splits,
)
from .filters import AlertFilter, CustomRuleFilter, GeographicFilter, SeverityFilter, TimeFilter
from .pipeline import AlertProcessingPipeline, AlertProcessor, ProcessingError
from .prioritization import AlertPrioritizer, PriorityScore, RiskAssessment
from .validation import AlertValidator, ConfidenceScore, ValidationResult
from .workflows import AlertWorkflow, ResponseAction, WorkflowEngine

__all__ = [
    "AlertDeduplicator",
    "AlertFilter",
    "AlertPrioritizer",
    "AlertProcessingPipeline",
    "AlertProcessor",
    "AlertValidator",
    "AlertWorkflow",
    "ConfidenceScore",
    "CustomRuleFilter",
    "DuplicateDetectionStrategy",
    "GeographicFilter",
    "PriorityScore",
    "ProcessingError",
    "ResponseAction",
    "RiskAssessment",
    "SeverityFilter",
    "TimeFilter",
    "ValidationResult",
    "WorkflowEngine",
    "collapse_superseded_nws_alerts",
    "deduplicate_nws_active_alerts",
    "merge_same_issuance_zone_splits",
]
