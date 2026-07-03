# Geo-hazard monitoring

SkywarnPlus-NG can announce **position-based hazards** (and global space weather) on your repeater nodes in addition to NWS county alerts. Position-based types share gpsd or static coordinates under **Geo Hazard Position**, the same settings used for [NHC tropical cyclone](https://www.nhc.noaa.gov) monitoring.

## What is covered where

| Hazard type | Source | Configuration section |
|-------------|--------|------------------------|
| Tornado, severe thunderstorm, flood, etc. | NWS API | Counties + alert behavior |
| Fire **weather** (Red Flag Warning, Fire Weather Watch) | NWS API | Counties — no extra setup |
| Tropical cyclone advisories | NHC GIS RSS | **NHC Tropical Cyclones** (+ **Geo Hazard Position**) |
| **Earthquakes** | USGS FDSN event API | **USGS Earthquakes** (+ **Geo Hazard Position**) |
| **Active wildfire perimeters** | NIFC WFIGS | **Wildfire Incidents** (+ **Geo Hazard Position**) |
| **Tsunami alerts** | NWS active alerts (point) | **Tsunami Alerts** (+ **Geo Hazard Position**) |
| **Space weather** | NOAA SWPC | **Space Weather** (global — no position) |
| **Volcano notices** | USGS VONA / HANS | **Volcano Notices** (+ **Geo Hazard Position**) |

Fire weather forecasts are NWS alerts. The wildfire section tracks **active fire boundaries** from interagency perimeter data, not Red Flag Warnings. When tsunami monitoring is enabled, county NWS voice skips tsunami events so they are not announced twice.

## Requirements

1. **Enable per feature** — each hazard has **Enable monitoring** and **Enable voice** in Configuration (all default to off). Uncheck monitoring and save to stop polling for that type.
2. **Position** — enable **gpsd** and/or set **static latitude/longitude** once under **Geo Hazard Position** (shared by NHC, earthquakes, wildfires, tsunami, and volcano). Space weather does not use position.
3. **Asterisk / asl-tts** — voice announcements use the same TTS pipeline as weather alerts.
4. **Optional notifications** — when email, Pushover, or global webhooks are configured, subscribers receive a broadcast when a geo hazard is announced on the air (same as general notifications, not county-filtered NWS alerts).

## Shared geo hazard position

```yaml
geo_hazard_position:
  use_gps_position: true
  static_lat: 29.95
  static_lon: -90.07
```

When `use_gps_position` is true, gpsd is preferred; static lat/lon are the fallback for all position-based geo hazards.

## USGS earthquakes

```yaml
earthquake:
  enabled: true
  announce_enabled: false   # monitor on dashboard only
  poll_interval_minutes: 10
  min_magnitude: 3.5
  max_distance_miles: 75
  lookback_hours: 24
  max_event_age_hours: 6
  announce_history_on_enable: false
  max_announcements_per_cycle: 3
  ignore_automatic_below: 4.5   # optional; skip low-confidence automatic events
```

- Polls [USGS GeoJSON](https://earthquake.usgs.gov/fdsnws/event/1/) within `max_distance_miles` of your position.
- `enabled` turns on feed polling and dashboard tracking; `announce_enabled` controls repeater voice (defaults to true).
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
  announce_enabled: true
  poll_interval_minutes: 15
  max_distance_miles: 50
  min_acres: 250
  exclude_prescribed: true
  max_discovery_age_hours: 48
  announce_history_on_enable: false
  max_announcements_per_cycle: 3
```

- Polls NIFC **WFIGS Interagency Perimeters (Current)** near your position.
- `enabled` turns on feed polling and dashboard tracking; `announce_enabled` controls repeater voice (defaults to true).
- Filters by acreage, distance, discovery age, and optionally excludes prescribed burns.
- On first enable, existing in-range incidents are seeded without voice unless `announce_history_on_enable: true`.
- At most `max_announcements_per_cycle` incidents are voiced per poll (default 3).
- Each incident is announced **once**.
- Respects quiet hours.
- NHC cyclone advisories also send broadcast notifications when configured (same as earthquakes/wildfires).

**Tuning tips**

- Rural / mountain West: try `max_distance_miles: 150–500` with higher `min_acres` to limit chatter.
- Wide-area monitoring (dashboard + occasional distant large fires): up to **5000** miles (same cap as NHC/earthquake).

## Tsunami alerts (NWS point)

```yaml
tsunami:
  enabled: true
  announce_enabled: true
  poll_interval_minutes: 2
  min_level: warning   # watch, advisory, or warning
  announce_history_on_enable: false
  max_announcements_per_cycle: 2
```

- Polls NWS active alerts at the geo-hazard position and filters for tsunami products.
- When monitoring is enabled, county NWS voice does not announce tsunami events (geo-hazard path owns them).

## Space weather (NOAA SWPC)

```yaml
space_weather:
  enabled: true
  announce_enabled: true
  poll_interval_minutes: 5
  min_geomagnetic_scale: 0
  min_radio_blackout_scale: 0
  min_solar_radiation_scale: 0
  announce_watches: true
  announce_warnings: true
  announce_alerts: true
  announce_summaries: false
  announce_history_on_enable: false
  max_announcements_per_cycle: 2
```

- Global feed (not position-based). Dashboard shows the five most recent matching alerts; voice considers the full feed with per-cycle caps.
- Scale floors apply only when that scale is present on an alert (G/R/S are independent).

## Volcano notices (USGS VONA)

```yaml
volcano:
  enabled: true
  announce_enabled: true
  poll_interval_minutes: 15
  max_distance_miles: 150
  min_color_code: orange
  observatories: ["HVO"]   # empty = all
  lookback_days: 7
  announce_history_on_enable: false
  max_announcements_per_cycle: 2
```

- Dashboard and voice use the **latest notice per volcano** (not full VONA history).
- Distance uses PSN coordinates in the notice when present, otherwise catalog lat/lon from the API.

## Dashboard and health

- **Dashboard** — sections appear when each feature is enabled; warnings show if the last poll failed.
- **Health** — `usgs_api`, `wfigs_api`, `tsunami_api`, `swpc_api`, and `volcano_api` checks run when the corresponding feature is enabled.

## Testing

1. Enable the feature and set static coordinates near a recent event (or use a test position in an active fire zone).
2. Lower thresholds temporarily (`min_magnitude`, `min_acres`, `min_color_code`) to verify voice and dashboard.
3. Check **Health** and poll error banners if feeds are unreachable.
4. Confirm announcements are not repeated after the first voice alert (state keys such as `usgs_announced_events`, `wildfire_announced_incidents`, `tsunami_announced_alerts`, `spaceweather_announced_alerts`, `volcano_announced_notices`).
