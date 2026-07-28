"""
Core data models for SkywarnPlus-NG.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class AlertSeverity(StrEnum):
    """Alert severity levels."""

    EXTREME = "Extreme"
    SEVERE = "Severe"
    MODERATE = "Moderate"
    MINOR = "Minor"
    UNKNOWN = "Unknown"


class AlertUrgency(StrEnum):
    """Alert urgency levels."""

    IMMEDIATE = "Immediate"
    EXPECTED = "Expected"
    FUTURE = "Future"
    PAST = "Past"
    UNKNOWN = "Unknown"


class AlertCertainty(StrEnum):
    """Alert certainty levels."""

    OBSERVED = "Observed"
    LIKELY = "Likely"
    POSSIBLE = "Possible"
    UNLIKELY = "Unlikely"
    UNKNOWN = "Unknown"


class AlertStatus(StrEnum):
    """Alert status."""

    ACTUAL = "Actual"
    EXERCISE = "Exercise"
    SYSTEM = "System"
    TEST = "Test"
    DRAFT = "Draft"


class AlertCategory(StrEnum):
    """Alert categories."""

    MET = "Met"
    GEO = "Geo"
    SAFETY = "Safety"
    SECURITY = "Security"
    RESCUE = "Rescue"
    FIRE = "Fire"
    HEALTH = "Health"
    ENV = "Env"
    TRANSPORT = "Transport"
    INFRA = "Infra"
    CBRNE = "CBRNE"
    OTHER = "Other"


class WeatherAlert(BaseModel):
    """Weather alert model."""

    id: str = Field(..., description="Alert identifier")
    event: str = Field(..., description="Alert event type")
    headline: str | None = Field(None, description="Alert headline")
    description: str = Field(..., description="Alert description")
    instruction: str | None = Field(None, description="Alert instructions")
    severity: AlertSeverity = Field(AlertSeverity.UNKNOWN, description="Alert severity")
    urgency: AlertUrgency = Field(AlertUrgency.UNKNOWN, description="Alert urgency")
    certainty: AlertCertainty = Field(AlertCertainty.UNKNOWN, description="Alert certainty")
    status: AlertStatus = Field(AlertStatus.ACTUAL, description="Alert status")
    category: AlertCategory = Field(AlertCategory.OTHER, description="Alert category")
    sent: datetime = Field(..., description="Alert sent timestamp")
    effective: datetime = Field(..., description="Alert effective timestamp")
    onset: datetime | None = Field(None, description="Alert onset timestamp")
    expires: datetime = Field(..., description="Alert expiration timestamp")
    ends: datetime | None = Field(None, description="Alert end timestamp")
    area_desc: str = Field(..., description="Affected area description")
    geocode: list[str] = Field(default_factory=list, description="Geographic codes")
    county_codes: list[str] = Field(default_factory=list, description="County codes")
    sender: str = Field(..., description="Alert sender")
    sender_name: str = Field(..., description="Alert sender name")
