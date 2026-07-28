"""
Delivery queue and status tracking system for SkywarnPlus-NG.
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DeliveryStatus(Enum):
    """Delivery status."""

    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class DeliveryMethod(Enum):
    """Delivery methods."""

    EMAIL = "email"
    WEBHOOK = "webhook"
    PUSH = "push"
    SMS = "sms"


@dataclass
class RetryPolicy:
    """Retry policy for failed deliveries."""

    max_retries: int = 3
    initial_delay_seconds: int = 5
    max_delay_seconds: int = 300
    backoff_multiplier: float = 2.0
    jitter: bool = True

    def get_delay(self, attempt: int) -> int:
        """Get delay for retry attempt."""
        if attempt <= 0:
            return 0

        # Calculate exponential backoff
        delay = self.initial_delay_seconds * (self.backoff_multiplier ** (attempt - 1))

        # Cap at maximum delay
        delay = min(delay, self.max_delay_seconds)

        # Add jitter if enabled
        if self.jitter:
            import random

            jitter_range = delay * 0.1  # 10% jitter
            delay += random.uniform(-jitter_range, jitter_range)

        return max(0, int(delay))


@dataclass
class DeliveryAttempt:
    """Individual delivery attempt."""

    attempt_id: str
    timestamp: datetime
    status: DeliveryStatus
    error_message: str | None = None
    response_data: dict[str, Any] | None = None
    duration_ms: float | None = None


@dataclass
class DeliveryItem:
    """Item in the delivery queue."""

    delivery_id: str
    alert_id: str
    method: DeliveryMethod
    recipient: str
    subject: str
    body: str
    metadata: dict[str, Any] = field(default_factory=dict)

    # Status tracking
    status: DeliveryStatus = DeliveryStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    scheduled_at: datetime | None = None
    sent_at: datetime | None = None
    delivered_at: datetime | None = None

    # Retry tracking
    retry_count: int = 0
    max_retries: int = 3
    next_retry_at: datetime | None = None

    # Attempts
    attempts: list[DeliveryAttempt] = field(default_factory=list)

    def __post_init__(self):
        if not self.scheduled_at:
            self.scheduled_at = self.created_at

    def add_attempt(
        self,
        status: DeliveryStatus,
        error_message: str | None = None,
        response_data: dict[str, Any] | None = None,
        duration_ms: float | None = None,
    ) -> None:
        """Add a delivery attempt."""
        attempt = DeliveryAttempt(
            attempt_id=str(uuid.uuid4()),
            timestamp=datetime.now(UTC),
            status=status,
            error_message=error_message,
            response_data=response_data,
            duration_ms=duration_ms,
        )
        self.attempts.append(attempt)
        self.status = status

    def can_retry(self) -> bool:
        """Check if delivery can be retried."""
        return (
            self.status in [DeliveryStatus.FAILED, DeliveryStatus.RETRYING]
            and self.retry_count < self.max_retries
        )

    def schedule_retry(self, retry_policy: RetryPolicy) -> None:
        """Schedule next retry attempt."""
        if not self.can_retry():
            return

        self.retry_count += 1
        delay_seconds = retry_policy.get_delay(self.retry_count)
        self.next_retry_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
        self.status = DeliveryStatus.RETRYING
        self.scheduled_at = self.next_retry_at

        logger.debug(
            f"Scheduled retry {self.retry_count} for delivery {self.delivery_id} in {delay_seconds}s"
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "delivery_id": self.delivery_id,
            "alert_id": self.alert_id,
            "method": self.method.value,
            "recipient": self.recipient,
            "subject": self.subject,
            "body": self.body,
            "metadata": self.metadata,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
            "attempts": [
                {
                    "attempt_id": attempt.attempt_id,
                    "timestamp": attempt.timestamp.isoformat(),
                    "status": attempt.status.value,
                    "error_message": attempt.error_message,
                    "response_data": attempt.response_data,
                    "duration_ms": attempt.duration_ms,
                }
                for attempt in self.attempts
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeliveryItem":
        """Create from dictionary."""
        item = cls(
            delivery_id=data["delivery_id"],
            alert_id=data["alert_id"],
            method=DeliveryMethod(data["method"]),
            recipient=data["recipient"],
            subject=data["subject"],
            body=data["body"],
            metadata=data.get("metadata", {}),
            status=DeliveryStatus(data.get("status", "pending")),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
        )

        # Set timestamps
        if "created_at" in data:
            item.created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        if data.get("scheduled_at"):
            item.scheduled_at = datetime.fromisoformat(data["scheduled_at"].replace("Z", "+00:00"))
        if data.get("sent_at"):
            item.sent_at = datetime.fromisoformat(data["sent_at"].replace("Z", "+00:00"))
        if data.get("delivered_at"):
            item.delivered_at = datetime.fromisoformat(data["delivered_at"].replace("Z", "+00:00"))
        if data.get("next_retry_at"):
            item.next_retry_at = datetime.fromisoformat(
                data["next_retry_at"].replace("Z", "+00:00")
            )

        # Load attempts
        for attempt_data in data.get("attempts", []):
            attempt = DeliveryAttempt(
                attempt_id=attempt_data["attempt_id"],
                timestamp=datetime.fromisoformat(attempt_data["timestamp"].replace("Z", "+00:00")),
                status=DeliveryStatus(attempt_data["status"]),
                error_message=attempt_data.get("error_message"),
                response_data=attempt_data.get("response_data"),
                duration_ms=attempt_data.get("duration_ms"),
            )
            item.attempts.append(attempt)

        return item


class DeliveryQueue:
    """Delivery queue for managing notification delivery."""

    def __init__(self, data_file: Path | None = None):
        self.data_file = data_file or Path("delivery_queue.json")
        self.queue: list[DeliveryItem] = []
        self.retry_policy = RetryPolicy()
        self.logger = logging.getLogger(__name__)
        self._load_queue()

    def _load_queue(self) -> None:
        """Load delivery queue from file."""
        try:
            if self.data_file.exists():
                with open(self.data_file, encoding="utf-8") as f:
                    data = json.load(f)

                for item_data in data.get("queue", []):
                    item = DeliveryItem.from_dict(item_data)
                    self.queue.append(item)

                self.logger.info(f"Loaded {len(self.queue)} items from delivery queue")
            else:
                self.logger.info("No delivery queue file found, starting with empty queue")

        except Exception as e:
            self.logger.error(f"Failed to load delivery queue: {e}")
            self.queue = []

    def _save_queue(self) -> None:
        """Save delivery queue to file."""
        try:
            data = {
                "queue": [item.to_dict() for item in self.queue],
                "last_updated": datetime.now(UTC).isoformat(),
            }

            from ..utils.atomic_json import atomic_write_json

            atomic_write_json(self.data_file, data)

            self.logger.debug(f"Saved {len(self.queue)} items to delivery queue")

        except Exception as e:
            self.logger.error(f"Failed to save delivery queue: {e}")

    def add_delivery(
        self,
        alert_id: str,
        method: DeliveryMethod,
        recipient: str,
        subject: str,
        body: str,
        metadata: dict[str, Any] | None = None,
        scheduled_at: datetime | None = None,
    ) -> str:
        """Add a delivery item to the queue."""
        delivery_id = str(uuid.uuid4())

        item = DeliveryItem(
            delivery_id=delivery_id,
            alert_id=alert_id,
            method=method,
            recipient=recipient,
            subject=subject,
            body=body,
            metadata=metadata or {},
            scheduled_at=scheduled_at,
        )

        self.queue.append(item)
        self._save_queue()

        self.logger.debug(f"Added delivery {delivery_id} to queue")
        return delivery_id

    def get_pending_deliveries(self) -> list[DeliveryItem]:
        """Get deliveries that are ready to be sent."""
        now = datetime.now(UTC)

        pending = []
        for item in self.queue:
            if (
                item.status in [DeliveryStatus.PENDING, DeliveryStatus.RETRYING]
                and item.scheduled_at
                and item.scheduled_at <= now
            ):
                pending.append(item)

        return pending

    def get_delivery(self, delivery_id: str) -> DeliveryItem | None:
        """Get a delivery item by ID."""
        for item in self.queue:
            if item.delivery_id == delivery_id:
                return item
        return None

    def update_delivery_status(
        self,
        delivery_id: str,
        status: DeliveryStatus,
        error_message: str | None = None,
        response_data: dict[str, Any] | None = None,
        duration_ms: float | None = None,
    ) -> bool:
        """Update delivery status."""
        item = self.get_delivery(delivery_id)
        if not item:
            self.logger.warning(f"Delivery {delivery_id} not found")
            return False

        # Add attempt
        item.add_attempt(status, error_message, response_data, duration_ms)

        # Update timestamps
        if status == DeliveryStatus.SENT:
            item.sent_at = datetime.now(UTC)
        elif status == DeliveryStatus.DELIVERED:
            item.delivered_at = datetime.now(UTC)

        # Handle retry logic
        if status == DeliveryStatus.FAILED and item.can_retry():
            item.schedule_retry(self.retry_policy)
        elif status in [DeliveryStatus.SENT, DeliveryStatus.DELIVERED]:
            # Mark as completed
            pass

        self._save_queue()
        self.logger.debug(f"Updated delivery {delivery_id} status to {status.value}")
        return True

    def remove_delivery(self, delivery_id: str) -> bool:
        """Remove a delivery from the queue."""
        for i, item in enumerate(self.queue):
            if item.delivery_id == delivery_id:
                del self.queue[i]
                self._save_queue()
                self.logger.debug(f"Removed delivery {delivery_id} from queue")
                return True

        self.logger.warning(f"Delivery {delivery_id} not found for removal")
        return False

    def cleanup_completed_deliveries(self, max_age_hours: int = 24) -> int:
        """Remove completed deliveries older than specified age."""
        cutoff_time = datetime.now(UTC) - timedelta(hours=max_age_hours)

        removed_count = 0
        items_to_remove = []

        for item in self.queue:
            if (
                item.status in [DeliveryStatus.SENT, DeliveryStatus.DELIVERED]
                and item.sent_at
                and item.sent_at < cutoff_time
            ):
                items_to_remove.append(item)

        for item in items_to_remove:
            self.queue.remove(item)
            removed_count += 1

        if removed_count > 0:
            self._save_queue()
            self.logger.info(f"Cleaned up {removed_count} completed deliveries")

        return removed_count

    def get_queue_stats(self) -> dict[str, Any]:
        """Get delivery queue statistics."""
        stats = {
            "total_items": len(self.queue),
            "pending": 0,
            "sending": 0,
            "sent": 0,
            "delivered": 0,
            "failed": 0,
            "retrying": 0,
            "cancelled": 0,
        }

        for item in self.queue:
            status_key = item.status.value
            if status_key in stats:
                stats[status_key] += 1

        return stats

    def get_delivery_history(
        self,
        alert_id: str | None = None,
        method: DeliveryMethod | None = None,
        status: DeliveryStatus | None = None,
    ) -> list[DeliveryItem]:
        """Get delivery history with optional filters."""
        filtered = self.queue

        if alert_id:
            filtered = [item for item in filtered if item.alert_id == alert_id]

        if method:
            filtered = [item for item in filtered if item.method == method]

        if status:
            filtered = [item for item in filtered if item.status == status]

        # Sort by creation time (newest first)
        filtered.sort(key=lambda x: x.created_at, reverse=True)

        return filtered

    def get_failed_deliveries(self) -> list[DeliveryItem]:
        """Get deliveries that have failed and can be retried."""
        failed = []
        for item in self.queue:
            if item.status == DeliveryStatus.FAILED and item.can_retry():
                failed.append(item)

        return failed

    def retry_failed_deliveries(self) -> int:
        """Schedule retries for failed deliveries."""
        failed = self.get_failed_deliveries()
        retry_count = 0

        for item in failed:
            item.schedule_retry(self.retry_policy)
            retry_count += 1

        if retry_count > 0:
            self._save_queue()
            self.logger.info(f"Scheduled {retry_count} failed deliveries for retry")

        return retry_count
