# Earthquake and wildfire monitoring

SkywarnPlus-NG can announce **position-based hazards** on your repeater nodes in addition to NWS county alerts. These use the same gpsd or static coordinates as [NHC tropical cyclone](https://www.nhc.noaa.gov) monitoring.

## What is covered where

| Hazard type | Source | Configuration section |
|-------------|--------|------------------------|
| Tornado, severe thunderstorm, flood, etc. | NWS API | Counties + alert behavior |
| Fire **weather** (Red Flag Warning, Fire Weather Watch) | NWS API | Counties — no extra setup |
| Tropical cyclone advisories | NHC GIS RSS | **NHC Tropical Cyclones** |
| **Earthquakes** | USGS FDSN event API | **USGS Earthquakes** |
| **Active wildfire perimeters** | NIFC WFIGS | **Wildfire Incidents** |

Fire weather forecasts are NWS alerts. The wildfire section tracks **active fire boundaries** from interagency perimeter data, not Red Flag Warnings.

## Requirements

1. **Enable per feature** — each of NHC, earthquakes, and wildfires has its own **Enable** checkbox in Configuration (all default to off). Uncheck and save to stop polling and voice alerts for that hazard type.
2. **Position** — enable **gpsd** or set **static latitude/longitude** for each hazard type you enable.
3. **Asterisk / asl-tts** — voice announcements use the same TTS pipeline as weather alerts.
4. **Optional notifications** — when email, Pushover, or global webhooks are configured, subscribers receive a broadcast when an earthquake or wildfire is announced on the air (same as general notifications, not county-filtered NWS alerts).

## USGS earthquakes

```yaml
earthquake:
  enabled: true
  poll_interval_minutes: 10
  min_magnitude: 3.5
  max_distance_miles: 75
  lookback_hours: 24
  max_event_age_hours: 6
  announce_history_on_enable: false
  max_announcements_per_cycle: 3
  ignore_automatic_below: 4.5   # optional; skip low-confidence automatic events
  use_gps_position: true
  static_lat: 29.95
  static_lon: -90.07
```

- Polls [USGS GeoJSON](https://earthquake.usgs.gov/fdsnws/event/1/) within `max_distance_miles` of your position.
- Only announces events newer than `max_event_age_hours` (default 6), even though the feed lookback may be longer.
- On first enable, existing in-range events are **seeded** as already announced (no voice) unless `announce_history_on_enable: true`.
- At most `max_announcements_per_cycle` earthquakes are voiced per poll (default 3); additional matches wait for later polls.
- Each event is announced **once** (tracked in application state).
- Respects **quiet hours** (same as NHC cyclone advisories).
- Dashboard shows tracked events, distance, and announce status.

**Tuning tips**

- Gulf Coast / low seismic areas: `min_magnitude: 4.0`, larger `max_distance_miles`.
- California / active zones: `min_magnitude: 3.0–3.5`, `ignore_automatic_below: 4.0` to reduce false positives.

## Wildfire incidents (WFIGS)

```yaml
wildfire:
  enabled: true
  poll_interval_minutes: 15
  max_distance_miles: 50
  min_acres: 250
  exclude_prescribed: true
  max_discovery_age_hours: 48
  announce_history_on_enable: false
  max_announcements_per_cycle: 3
  use_gps_position: true
  static_lat: 34.05
  static_lon: -118.25
```

- Polls NIFC **WFIGS Interagency Perimeters (Current)** near your position.
- Filters by acreage, distance, discovery age, and optionally excludes prescribed burns.
- On first enable, existing in-range incidents are seeded without voice unless `announce_history_on_enable: true`.
- At most `max_announcements_per_cycle` incidents are voiced per poll (default 3).
- Each incident is announced **once**.
- Respects quiet hours.
- NHC cyclone advisories also send broadcast notifications when configured (same as earthquakes/wildfires).

**Tuning tips**

- Rural / mountain West: try `max_distance_miles: 150–500` with higher `min_acres` to limit chatter.
- Wide-area monitoring (dashboard + occasional distant large fires): up to **5000** miles (same cap as NHC/earthquake).

## Dashboard and health

- **Dashboard** — sections appear when each feature is enabled; warnings show if the last poll failed.
- **Health** — `usgs_api` and `wfigs_api` checks run when the corresponding feature is enabled.

## Testing

1. Enable the feature and set static coordinates near a recent event (or use a test position in a active fire zone).
2. Lower thresholds temporarily (`min_magnitude`, `min_acres`) to verify voice and dashboard.
3. Check **Health** and poll error banners if feeds are unreachable.
4. Confirm announcements are not repeated after the first voice alert (state keys `usgs_announced_events`, `wildfire_announced_incidents`).
