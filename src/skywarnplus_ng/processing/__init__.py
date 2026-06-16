"""
Alert processing pipeline for SkywarnPlus-NG.
"""

from .pipeline import AlertProcessingPipeline, AlertProcessor, ProcessingError
from .filters import AlertFilter, GeographicFilter, TimeFilter, SeverityFilter, CustomRuleFilter
from .deduplication import (
    AlertDeduplicator,
    DuplicateDetectionStrategy,
    collapse_superseded_nws_alerts,
    merge_same_issuance_zone_splits,
)
from .prioritization import AlertPrioritizer, PriorityScore, RiskAssessment
from .validation import AlertValidator, ValidationResult, ConfidenceScore
from .workflows import AlertWorkflow, WorkflowEngine, ResponseAction

__all__ = [
    "AlertProcessingPipeline",
    "AlertProcessor",
    "ProcessingError",
    "AlertFilter",
    "GeographicFilter",
    "TimeFilter",
    "SeverityFilter",
    "CustomRuleFilter",
    "AlertDeduplicator",
    "DuplicateDetectionStrategy",
    "collapse_superseded_nws_alerts",
    "merge_same_issuance_zone_splits",
    "AlertPrioritizer",
    "PriorityScore",
    "RiskAssessment",
    "AlertValidator",
    "ValidationResult",
    "ConfidenceScore",
    "AlertWorkflow",
    "WorkflowEngine",
    "ResponseAction",
]
