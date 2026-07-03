"""
NWS API client for fetching weather alerts.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, Set, Tuple
import logging
import re
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

# NWS SAME uses a 6-digit FIPS form: 0 + 2-digit state FIPS + 3-digit county FIPS (e.g. 048167 -> TXC167).
_FIPS_STATE_POSTAL: Dict[str, str] = {
    "01": "AL",
    "02": "AK",
    "04": "AZ",
    "05": "AR",
    "06": "CA",
    "08": "CO",
    "09": "CT",
    "10": "DE",
    "11": "DC",
    "12": "FL",
    "13": "GA",
    "15": "HI",
    "16": "ID",
    "17": "IL",
    "18": "IN",
    "19": "IA",
    "20": "KS",
    "21": "KY",
    "22": "LA",
    "23": "ME",
    "24": "MD",
    "25": "MA",
    "26": "MI",
    "27": "MN",
    "28": "MS",
    "29": "MO",
    "30": "MT",
    "31": "NE",
    "32": "NV",
    "33": "NH",
    "34": "NJ",
    "35": "NM",
    "36": "NY",
    "37": "NC",
    "38": "ND",
    "39": "OH",
    "40": "OK",
    "41": "OR",
    "42": "PA",
    "44": "RI",
    "45": "SC",
    "46": "SD",
    "47": "TN",
    "48": "TX",
    "49": "UT",
    "50": "VT",
    "51": "VA",
    "53": "WA",
    "54": "WV",
    "55": "WI",
    "56": "WY",
    "60": "AS",
    "66": "GU",
    "69": "MP",
    "72": "PR",
    "78": "VI",
}

_UGC_COUNTY_CODE = re.compile(r"^[A-Z]{2}C\d{3}$")


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
        self._point_county_cache: Dict[Tuple[float, float], Tuple[str, str]] = {}

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

    @staticmethod
    def _county_codes_from_nws_geocode(geocode: Dict[str, Any]) -> List[str]:
        """
        Build NWS county zone codes (e.g. TXC167) for filtering and display.

        Coastal/marine products often list forecast zones (TXZ###) in UGC while SAME still
        lists affected county FIPS. Geographic matching uses ``TXC###`` codes from config.
        """
        out: List[str] = []
        seen: Set[str] = set()

        def add(code: str) -> None:
            if code not in seen:
                seen.add(code)
                out.append(code)

        ugc_raw = geocode.get("UGC", [])
        if isinstance(ugc_raw, list):
            for raw in ugc_raw:
                if isinstance(raw, str):
                    u = raw.strip().upper()
                    if _UGC_COUNTY_CODE.match(u):
                        add(u)

        same_raw = geocode.get("SAME", [])
        if isinstance(same_raw, list):
            for raw in same_raw:
                s = str(raw).strip()
                if len(s) == 6 and s.isdigit() and s[0] == "0":
                    state_fips = s[1:3]
                    county_fips = s[3:6]
                    abbrev = _FIPS_STATE_POSTAL.get(state_fips)
                    if abbrev:
                        add(f"{abbrev}C{county_fips}")

        return out

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

        # Extract geocode (county codes for monitored-county matching)
        geocode = props.get("geocode") if isinstance(props.get("geocode"), dict) else {}
        county_codes = self._county_codes_from_nws_geocode(geocode)

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

    async def _fetch_with_retry(self, url: str, retry_count: int = 0) -> Optional[Dict[str, Any]]:
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
            status = e.response.status_code
            if status == 429 and retry_count < self.max_retries:
                retry_after = e.response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else float(2**retry_count)
                except (TypeError, ValueError):
                    delay = float(2**retry_count)
                logger.warning(
                    "NWS rate limited (429), retrying in %ss (%s/%s)",
                    delay,
                    retry_count + 1,
                    self.max_retries,
                )
                await asyncio.sleep(delay)
                return await self._fetch_with_retry(url, retry_count + 1)
            if status >= 500 and retry_count < self.max_retries:
                logger.warning(
                    f"Server error {e.response.status_code}, retrying... ({retry_count + 1}/{self.max_retries})"
                )
                await asyncio.sleep(2**retry_count)  # Exponential backoff
                return await self._fetch_with_retry(url, retry_count + 1)
            else:
                logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
                raise NWSClientError(f"HTTP error: {e.response.status_code}") from e
        except httpx.RequestError as e:
            if retry_count < self.max_retries:
                logger.warning(f"Request error, retrying... ({retry_count + 1}/{self.max_retries})")
                await asyncio.sleep(2**retry_count)
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

    async def fetch_active_alert_features_at_point(
        self, lat: float, lon: float
    ) -> List[Dict[str, Any]]:
        """
        Fetch raw active alert GeoJSON features for a geographic point.

        Used by tsunami monitoring (NWS /alerts/active?point=).
        """
        url = f"/alerts/active?point={lat:.4f},{lon:.4f}"
        logger.debug("Fetching active alerts at point: %s, %s", lat, lon)

        data = await self._fetch_with_retry(url)
        if data is None:
            return []

        features = data.get("features", [])
        if not isinstance(features, list):
            return []
        return [f for f in features if isinstance(f, dict)]

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
        failed_zones: List[str] = []
        for zone_code, result in zip(zone_codes, results):
            if isinstance(result, Exception):
                logger.error("Error fetching alerts for zone %s: %s", zone_code, result)
                failed_zones.append(zone_code)
                continue
            all_alerts.extend(result)

        if failed_zones:
            raise NWSClientError(
                f"Failed to fetch alerts for {len(failed_zones)} zone(s): "
                + ", ".join(failed_zones)
            )

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

    @staticmethod
    def _alert_cancelled_or_no_longer_in_effect(alert: WeatherAlert) -> bool:
        """
        True when NWS marks the phenomenon over or the product is a cancellation.

        The active-alerts feed can still return these until `ends`; we drop them so
        the station does not treat them as live hazards.
        """
        if alert.urgency == AlertUrgency.PAST:
            return True
        h = (alert.headline or "").lower()
        if "cancelled" in h or "canceled" in h:
            return True
        return False

    def filter_active_alerts(
        self, alerts: List[WeatherAlert], time_type: str = "onset"
    ) -> List[WeatherAlert]:
        """
        Filter alerts to only include currently active ones.

        Cancellation products and ``urgency=Past`` (event no longer applicable per
        CAP) are excluded immediately, even when ``ends`` is still in the future.

        Args:
            alerts: List of alerts to filter
            time_type: Time type to use - 'onset' or 'effective'

        Returns:
            Filtered list of active alerts
        """
        current_time = datetime.now(timezone.utc)
        active_alerts = []

        for alert in alerts:
            if self._alert_cancelled_or_no_longer_in_effect(alert):
                logger.debug(
                    "Dropping alert %s (%s): cancelled or urgency=Past",
                    alert.id,
                    alert.event,
                )
                continue

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
                alert_id = (
                    f"TEST-{title.replace(' ', '_')}-{county}-{int(current_time.timestamp())}"
                )

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

    async def resolve_county_from_coordinates(
        self, latitude: float, longitude: float
    ) -> Optional[Tuple[str, str]]:
        """
        Resolve an NWS county zone code (e.g. TXC039) from coordinates.

        Uses the NWS /points endpoint and caches by rounded lat/lon.
        """
        cache_key = (round(latitude, 3), round(longitude, 3))
        cached = self._point_county_cache.get(cache_key)
        if cached:
            return cached

        url = f"/points/{cache_key[0]},{cache_key[1]}"
        try:
            data = await self._fetch_with_retry(url)
        except NWSClientError as exc:
            logger.warning("Failed to resolve county from coordinates: %s", exc)
            return None

        if not isinstance(data, dict):
            return None

        props = data.get("properties")
        if not isinstance(props, dict):
            return None

        county_url = props.get("county")
        if not isinstance(county_url, str):
            return None

        match = re.search(r"/zones/county/([A-Z]{2}C\d{3})$", county_url.strip())
        if not match:
            return None

        county_code = match.group(1)
        county_name = county_code

        zone_path = county_url
        if county_url.startswith(self.config.base_url):
            zone_path = county_url[len(self.config.base_url) :]
        elif county_url.startswith("http"):
            from urllib.parse import urlparse

            zone_path = urlparse(county_url).path

        try:
            zone_data = await self._fetch_with_retry(zone_path)
            zone_props = zone_data.get("properties") if isinstance(zone_data, dict) else None
            if isinstance(zone_props, dict) and zone_props.get("name"):
                county_name = str(zone_props["name"])
        except NWSClientError:
            logger.debug("County zone lookup failed for %s", county_code)

        result = (county_code, county_name)
        self._point_county_cache[cache_key] = result
        return result

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
