"""
NWS API client for fetching weather alerts.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, Set
import logging
import asyncio
import httpx
from dateutil import parser

from ..core.config import NWSApiConfig
from ..core.models import (
    WeatherAlert,
    AlertSeverity,
    AlertUrgency,
    AlertCertainty,
    AlertStatus,
    AlertCategory,
)

logger = logging.getLogger(__name__)


class NWSClientError(Exception):
    """NWS API client error."""

    pass


class NWSClient:
    """NWS API client for fetching weather alerts."""

    def __init__(self, config: NWSApiConfig, max_retries: int = 3):
        """
        Initialize NWS client.

        Args:
            config: NWS API configuration
            max_retries: Maximum number of retry attempts for failed requests
        """
        self.config = config
        self.max_retries = max_retries
        self.client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=config.timeout,
            headers={"User-Agent": config.user_agent},
            follow_redirects=True,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    def _map_severity(self, severity: Optional[str]) -> AlertSeverity:
        """Map NWS severity string to AlertSeverity enum."""
        if not severity:
            return AlertSeverity.UNKNOWN

        mapping = {
            "Extreme": AlertSeverity.EXTREME,
            "Severe": AlertSeverity.SEVERE,
            "Moderate": AlertSeverity.MODERATE,
            "Minor": AlertSeverity.MINOR,
            "Unknown": AlertSeverity.UNKNOWN,
        }
        return mapping.get(severity, AlertSeverity.UNKNOWN)

    def _map_urgency(self, urgency: Optional[str]) -> AlertUrgency:
        """Map NWS urgency string to AlertUrgency enum."""
        if not urgency:
            return AlertUrgency.UNKNOWN

        mapping = {
            "Immediate": AlertUrgency.IMMEDIATE,
            "Expected": AlertUrgency.EXPECTED,
            "Future": AlertUrgency.FUTURE,
            "Past": AlertUrgency.PAST,
            "Unknown": AlertUrgency.UNKNOWN,
        }
        return mapping.get(urgency, AlertUrgency.UNKNOWN)

    def _map_certainty(self, certainty: Optional[str]) -> AlertCertainty:
        """Map NWS certainty string to AlertCertainty enum."""
        if not certainty:
            return AlertCertainty.UNKNOWN

        mapping = {
            "Observed": AlertCertainty.OBSERVED,
            "Likely": AlertCertainty.LIKELY,
            "Possible": AlertCertainty.POSSIBLE,
            "Unlikely": AlertCertainty.UNLIKELY,
            "Unknown": AlertCertainty.UNKNOWN,
        }
        return mapping.get(certainty, AlertCertainty.UNKNOWN)

    def _map_status(self, status: Optional[str]) -> AlertStatus:
        """Map NWS status string to AlertStatus enum."""
        if not status:
            return AlertStatus.ACTUAL

        mapping = {
            "Actual": AlertStatus.ACTUAL,
            "Exercise": AlertStatus.EXERCISE,
            "System": AlertStatus.SYSTEM,
            "Test": AlertStatus.TEST,
            "Draft": AlertStatus.DRAFT,
        }
        return mapping.get(status, AlertStatus.ACTUAL)

    def _map_category(self, category: Optional[str]) -> AlertCategory:
        """Map NWS category string to AlertCategory enum."""
        if not category:
            return AlertCategory.OTHER

        mapping = {
            "Met": AlertCategory.MET,
            "Geo": AlertCategory.GEO,
            "Safety": AlertCategory.SAFETY,
            "Security": AlertCategory.SECURITY,
            "Rescue": AlertCategory.RESCUE,
            "Fire": AlertCategory.FIRE,
            "Health": AlertCategory.HEALTH,
            "Env": AlertCategory.ENV,
            "Transport": AlertCategory.TRANSPORT,
            "Infra": AlertCategory.INFRA,
            "CBRNE": AlertCategory.CBRNE,
            "Other": AlertCategory.OTHER,
        }
        return mapping.get(category, AlertCategory.OTHER)

    def _parse_datetime(self, dt_str: str) -> datetime:
        """Parse ISO datetime string to datetime object."""
        try:
            return parser.isoparse(dt_str)
        except (ValueError, TypeError) as e:
            raise NWSClientError(f"Invalid datetime {dt_str!r}: {e}") from e

    def _parse_alert(self, feature: Dict[str, Any]) -> WeatherAlert:
        """Parse a GeoJSON feature into a WeatherAlert."""
        props = feature.get("properties")
        if not isinstance(props, dict):
            raise NWSClientError("Feature missing or invalid 'properties'")

        for key in ("sent", "effective", "expires", "id", "event"):
            if key not in props or props[key] is None:
                raise NWSClientError(f"Feature properties missing required field: {key}")

        # Parse timestamps
        sent = self._parse_datetime(props["sent"])
        effective = self._parse_datetime(props["effective"])
        expires = self._parse_datetime(props["expires"])

        onset = None
        if "onset" in props and props["onset"] is not None:
            onset = self._parse_datetime(props["onset"])

        ends = None
        if "ends" in props and props["ends"] is not None:
            ends = self._parse_datetime(props["ends"])

        # Extract geocode (county codes)
        geocode = props.get("geocode") if isinstance(props.get("geocode"), dict) else {}
        county_codes = geocode.get("UGC", []) if isinstance(geocode.get("UGC"), list) else []

        return WeatherAlert(
            id=props["id"],
            event=props["event"],
            headline=props.get("headline"),
            description=props.get("description", ""),
            instruction=props.get("instruction"),
            severity=self._map_severity(props.get("severity")),
            urgency=self._map_urgency(props.get("urgency")),
            certainty=self._map_certainty(props.get("certainty")),
            status=self._map_status(props.get("status")),
            category=self._map_category(props.get("category")),
            sent=sent,
            effective=effective,
            onset=onset,
            expires=expires,
            ends=ends,
            area_desc=props.get("areaDesc", ""),
            geocode=geocode.get("SAME", []),
            county_codes=county_codes,
            sender=props.get("sender", ""),
            sender_name=props.get("senderName", ""),
        )

    async def _fetch_with_retry(
        self, url: str, retry_count: int = 0
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch data from NWS API with retry logic.

        Args:
            url: URL to fetch
            retry_count: Current retry attempt

        Returns:
            JSON response data or None if all retries failed
        """
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500 and retry_count < self.max_retries:
                logger.warning(
                    f"Server error {e.response.status_code}, retrying... ({retry_count + 1}/{self.max_retries})"
                )
                await asyncio.sleep(2 ** retry_count)  # Exponential backoff
                return await self._fetch_with_retry(url, retry_count + 1)
            else:
                logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
                raise NWSClientError(f"HTTP error: {e.response.status_code}") from e
        except httpx.RequestError as e:
            if retry_count < self.max_retries:
                logger.warning(f"Request error, retrying... ({retry_count + 1}/{self.max_retries})")
                await asyncio.sleep(2 ** retry_count)
                return await self._fetch_with_retry(url, retry_count + 1)
            else:
                logger.error(f"Request error: {e}")
                raise NWSClientError(f"Request failed: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise NWSClientError(f"Unexpected error: {e}") from e

    async def fetch_alerts_for_zone(self, zone_code: str) -> List[WeatherAlert]:
        """
        Fetch active alerts for a specific zone/county code.

        Args:
            zone_code: Zone/county code (e.g., "TXC039")

        Returns:
            List of active weather alerts
        """
        url = f"/alerts/active?zone={zone_code}"
        logger.debug(f"Fetching alerts for zone: {zone_code}")

        data = await self._fetch_with_retry(url)
        if data is None:
            return []

        alerts = []
        seen_alert_ids: Set[str] = set()

        for feature in data.get("features", []):
            try:
                props = feature.get("properties") if isinstance(feature, dict) else None
                alert_id = props.get("id") if isinstance(props, dict) else None
                if alert_id in seen_alert_ids:
                    continue  # Skip duplicate alerts

                alert = self._parse_alert(feature)
                alerts.append(alert)
                seen_alert_ids.add(alert_id)
            except NWSClientError as e:
                logger.debug("Skipping invalid alert feature: %s", e)
                continue
            except Exception as e:
                logger.error(f"Failed to parse alert: {e}")
                continue

        logger.debug(f"Retrieved {len(alerts)} alerts for zone {zone_code}")
        return alerts

    async def fetch_alerts_for_zones(
        self, zone_codes: List[str], deduplicate: bool = True
    ) -> List[WeatherAlert]:
        """
        Fetch active alerts for multiple zones concurrently.

        Args:
            zone_codes: List of zone/county codes
            deduplicate: Whether to deduplicate alerts by ID

        Returns:
            List of active weather alerts from all zones
        """
        logger.debug(f"Fetching alerts for {len(zone_codes)} zones")

        # Fetch alerts for all zones concurrently
        tasks = [self.fetch_alerts_for_zone(zone_code) for zone_code in zone_codes]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect all alerts
        all_alerts = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Error fetching alerts: {result}")
                continue
            all_alerts.extend(result)

        # Deduplicate by alert ID if requested
        if deduplicate:
            seen_ids: Set[str] = set()
            unique_alerts = []
            for alert in all_alerts:
                if alert.id not in seen_ids:
                    unique_alerts.append(alert)
                    seen_ids.add(alert.id)
            all_alerts = unique_alerts

        logger.debug(f"Retrieved {len(all_alerts)} total alerts from {len(zone_codes)} zones")
        return all_alerts

    async def fetch_all_alerts(self) -> List[WeatherAlert]:
        """
        Fetch all active alerts (use with caution!).

        Returns:
            List of all active weather alerts
        """
        url = "/alerts/active"
        logger.warning("Fetching ALL active alerts - this may return a large dataset")

        data = await self._fetch_with_retry(url)
        if data is None:
            return []

        alerts = []
        seen_alert_ids: Set[str] = set()

        for feature in data.get("features", []):
            try:
                props = feature.get("properties") if isinstance(feature, dict) else None
                alert_id = props.get("id") if isinstance(props, dict) else None
                if alert_id in seen_alert_ids:
                    continue

                alert = self._parse_alert(feature)
                alerts.append(alert)
                seen_alert_ids.add(alert_id)
            except NWSClientError as e:
                logger.debug("Skipping invalid alert feature: %s", e)
                continue
            except Exception as e:
                logger.error(f"Failed to parse alert: {e}")
                continue

        logger.debug(f"Retrieved {len(alerts)} total alerts")
        return alerts

    def filter_active_alerts(
        self, alerts: List[WeatherAlert], time_type: str = "onset"
    ) -> List[WeatherAlert]:
        """
        Filter alerts to only include currently active ones.

        Args:
            alerts: List of alerts to filter
            time_type: Time type to use - 'onset' or 'effective'

        Returns:
            Filtered list of active alerts
        """
        current_time = datetime.now(timezone.utc)
        active_alerts = []

        for alert in alerts:
            # Determine start and end times based on time_type
            if time_type == "onset" and alert.onset:
                start_time = alert.onset
                end_time = alert.ends if alert.ends else alert.expires
            else:
                start_time = alert.effective
                end_time = alert.expires

            # Check if alert is currently active
            if start_time <= current_time < end_time:
                active_alerts.append(alert)
            else:
                logger.debug(
                    f"Alert {alert.event} not active: "
                    f"start={start_time}, end={end_time}, current={current_time}"
                )

        return active_alerts

    def generate_inject_alerts(
        self, inject_config: List[Dict[str, Any]], available_counties: List[str]
    ) -> List[WeatherAlert]:
        """
        Generate test alerts from injection configuration.
        
        Args:
            inject_config: List of injection alert configurations
            available_counties: List of available county codes to assign
            
        Returns:
            List of generated WeatherAlert objects
        """
        if not inject_config:
            return []
            
        alerts = []
        current_time = datetime.now(timezone.utc)
        
        # Severity mapping based on last word in alert title
        severity_words = {
            "Warning": AlertSeverity.SEVERE,
            "Watch": AlertSeverity.MODERATE,
            "Advisory": AlertSeverity.MINOR,
            "Statement": AlertSeverity.MINOR,
        }
        
        for idx, alert_info in enumerate(inject_config):
            if not isinstance(alert_info, dict):
                continue
                
            title = alert_info.get("Title", "")
            if not title:
                continue
                
            # Determine severity from last word
            last_word = title.split()[-1] if title else "Unknown"
            severity = severity_words.get(last_word, AlertSeverity.UNKNOWN)
            
            # Parse end time or default to 1 hour from now
            end_time_str = alert_info.get("EndTime")
            if end_time_str:
                try:
                    end_time = parser.isoparse(end_time_str)
                except Exception:
                    end_time = current_time + timedelta(hours=1)
            else:
                end_time = current_time + timedelta(hours=1)
            
            # Get counties to assign
            specified_counties = alert_info.get("CountyCodes", [])
            if not specified_counties:
                # Assign first X counties where X = alert index + 1
                county_count = min(idx + 1, len(available_counties))
                specified_counties = available_counties[:county_count]
            
            # Create one alert per county
            for county in specified_counties:
                if county not in available_counties:
                    logger.warning(f"County {county} not in configured counties, skipping")
                    continue
                
                # Generate unique ID
                alert_id = f"TEST-{title.replace(' ', '_')}-{county}-{int(current_time.timestamp())}"
                
                alert = WeatherAlert(
                    id=alert_id,
                    event=title,
                    headline=f"TEST: {title}",
                    description="This alert was manually injected as a test.",
                    instruction=None,
                    severity=severity,
                    urgency=AlertUrgency.IMMEDIATE,
                    certainty=AlertCertainty.OBSERVED,
                    status=AlertStatus.TEST,
                    category=AlertCategory.OTHER,
                    sent=current_time,
                    effective=current_time,
                    onset=current_time,
                    expires=end_time,
                    ends=end_time,
                    area_desc=f"Test area for {county}",
                    geocode=[],
                    county_codes=[county],
                    sender="SkywarnPlus-NG Test Mode",
                    sender_name="Test Alert System",
                )
                
                alerts.append(alert)
                logger.info(f"Generated test alert: {title} for {county}")
        
        return alerts

    async def test_connection(self) -> bool:
        """
        Test connection to the NWS API.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Try to fetch any active alerts
            response = await self.client.get("/alerts/active")
            response.raise_for_status()
            logger.info("NWS API connection test successful")
            return True
        except Exception as e:
            logger.error(f"NWS API connection test failed: {e}")
            return False
