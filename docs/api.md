# Dashboard HTTP API

Programmatic access to SkywarnPlus-NG goes through the same HTTP server as the web dashboard (default port **8100**). There is no separate API process.

This guide covers authentication, `base_path`, common integration patterns, and a full catalog of routes as implemented in the current tree.

Related: [notifications](notifications-overview.md), [subscribers](subscribers.md), [reverse proxy](../nginx-proxy-manager-guide.md), [Debian install](debian.md).

---

## Quick start

Replace `BASE` with your dashboard root. Direct listen:

```text
BASE=http://127.0.0.1:8100
```

Behind the packaged Apache proxy (or any reverse proxy with a prefix):

```text
BASE=http://your-host/skywarnplus-ng
```

`monitoring.http_server.base_path` must match that prefix (for example `/skywarnplus-ng`). All paths below are relative to `BASE`.

### Public read (typical install with auth enabled)

```bash
curl -sS "$BASE/api/status" | jq .
curl -sS "$BASE/api/alerts" | jq .
curl -sS "$BASE/api/health" | jq .
```

### Login, then call a protected route

Sessions use an encrypted cookie (`AIOHTTP_SESSION`). Send credentials as JSON; reuse the cookie jar.

```bash
COOKIE_JAR=$(mktemp)
curl -sS -c "$COOKIE_JAR" -b "$COOKIE_JAR" -X POST "$BASE/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"YOUR_PASSWORD"}'

curl -sS -c "$COOKIE_JAR" -b "$COOKIE_JAR" "$BASE/api/config" | jq .
curl -sS -c "$COOKIE_JAR" -b "$COOKIE_JAR" -X POST "$BASE/api/auth/logout"
rm -f "$COOKIE_JAR"
```

### Supermon / per-node status

```bash
curl -sS "$BASE/api/status?nodes=546051,546055" | jq '.alerts_by_node'
```

### WebSocket (live status + alerts)

Connect to `$BASE/ws` (same host/prefix as HTTP). Send JSON text frames:

```json
{"type": "ping"}
```

```json
{"type": "subscribe", "subscription": "alerts"}
```

Server replies include `{"type":"pong"}` and updates such as `status_update` / `alerts_update` (see [WebSocket](#websocket)).

---

## Base URL and `base_path`

| Setting | Default (packaged) | Notes |
|---------|-------------------|--------|
| `monitoring.http_server.host` | `0.0.0.0` | Bind address |
| `monitoring.http_server.port` | `8100` | Direct access when not proxied |
| `monitoring.http_server.base_path` | `/skywarnplus-ng` | Must match the reverse-proxy mount; use `""` only for bare `:8100` |

If the UI loads but `/static/` or `/api/` 404 under a proxy prefix, `base_path` is wrong — see [docs/debian.md](debian.md).

All API paths in this document omit the prefix. With `base_path: "/skywarnplus-ng"`, `GET /api/status` is reached as `GET /skywarnplus-ng/api/status`.

---

## Authentication

Controlled by `monitoring.http_server.auth`.

| Field | Role |
|-------|------|
| `enabled` | When `false`, nothing requires login |
| `username` / `password` | Dashboard admin credentials (password stored hashed) |
| `session_timeout_hours` | Cookie session lifetime (default 24) |
| `public_status_api` | When `true` (default), `GET /api/status` and `/ws` stay public; set `false` to require login for those too |
| `secure_cookies` / `cookie_secure_auto` | `Secure` on the session cookie (HTTPS / `X-Forwarded-Proto`) |

### Access model (auth enabled)

**Public (no login)** — operational read-only pages and the GET APIs they need:

- Pages: `/`, `/dashboard`, `/alerts`, `/alerts/history`, `/health`, `/metrics`, `/activity`
- APIs: `/api/status` (unless `public_status_api: false`), `/api/alerts`, `/api/alerts/history`, `/api/alerts/{id}/audio`, `/api/health`, `/api/health/history`, `/api/metrics`, `/api/activity`, `/api/update-status`
- WebSocket `/ws` follows `public_status_api` (same as status)

**Always requires a session** (when auth is enabled):

- Pages: `/configuration`, `/logs`, `/database`
- APIs under `/api/config`, `/api/logs`, `/api/database`, `/api/notifications`, `/api/tts`, `/api/counties`
- Any `POST` / `PUT` / `DELETE` / `PATCH` (except login/logout)

Unauthenticated API calls that require auth receive:

```json
{"error": "Authentication required"}
```

with HTTP **401**. HTML pages redirect to `/login`.

Login is rate-limited per client IP (**429** + optional `Retry-After`).

---

## Conventions

- **JSON** request bodies: `Content-Type: application/json`
- **Errors**: usually `{"error": "..."}`; some notification/test routes also return `{"success": false, "error": "..."}`
- **Success**: many mutating routes return `{"success": true, "message": "..."}` plus extra fields
- **Datetimes**: ISO-8601 strings (often UTC with `Z` or offset)
- There is **no API key** today — use the session cookie after login for protected routes
- `/api/alerts` does **not** accept `county` / `severity` query filters; filtering is done by monitored counties on the server

---

## Endpoint catalog

Auth column assumes `auth.enabled: true`. **Public** = no session. **Session** = login cookie required. **Public\*** = public only if `public_status_api: true`.

### Auth

#### `POST /api/auth/login`

| | |
|--|--|
| Auth | Public |
| Body | `{"username": "...", "password": "...", "remember": false}` |

**200:**

```json
{"success": true, "message": "Login successful"}
```

If the factory default password is still in use: `"must_change_password": true`.

**401** invalid credentials · **429** rate limited · **400** missing/invalid fields.

#### `POST /api/auth/logout`

| | |
|--|--|
| Auth | Public (clears cookie if present) |

**200:** `{"success": true, "message": "Logout successful"}`

---

### Status and live updates

#### `GET /api/status`

| | |
|--|--|
| Auth | Public\* |
| Query | `nodes` — optional comma-separated Asterisk node numbers (Supermon); ensures each appears under `alerts_by_node` |

Core fields from the application status, plus dashboard extras:

| Field | Meaning |
|-------|---------|
| `running`, `initialized` | Process state |
| `nws_connected`, `audio_available`, `asterisk_available`, … | Subsystem flags |
| `active_alerts`, `total_alerts` | Counts |
| `last_poll`, `last_all_clear` | ISO timestamps or null |
| `*_last_error_at` / `*_last_error_message` | NWS / NHC / USGS / wildfire / tsunami / space weather / volcano |
| `uptime_seconds` | Process uptime |
| `has_alerts`, `alerts` | Compact alert list for display (`event`, `severity`, `headline`) |
| `alerts_by_node` | Per-node `has_alerts`, `alerts`, `effective_counties`, optional `gps` |
| `gps` | Present when GPS/mobile county service is active |
| `asterisk_nodes` | Configured nodes (JSON-safe) |
| `is_configured` | Setup / default-password gate for the UI |

Example compact alert entry:

```json
{
  "event": "Tornado Warning (Travis)",
  "severity": "Extreme",
  "headline": "..."
}
```

#### `GET /ws`

| | |
|--|--|
| Auth | Public\* (same rule as `/api/status`) |
| Limit | Max **50** concurrent clients (**503** if full) |

**Client → server**

| Message | Effect |
|---------|--------|
| `{"type":"ping"}` | Reply `{"type":"pong"}` |
| `{"type":"subscribe","subscription":"alerts"}` | Immediate `alerts_update` with the active alert list |

**Server → client** (also pushed after polls / broadcasts)

```json
{
  "type": "status_update",
  "data": { },
  "timestamp": "2026-07-29T12:00:00+00:00"
}
```

```json
{
  "type": "alerts_update",
  "data": [ ],
  "timestamp": "2026-07-29T12:00:00+00:00"
}
```

`alerts_update.data` matches the alert objects from `GET /api/alerts` (full payloads, not the compact status list). Protocol-level WebSocket ping/pong runs about every 20s for proxy keep-alive.

---

### Alerts

#### `GET /api/alerts`

| | |
|--|--|
| Auth | Public |

```json
{
  "alerts": [ ],
  "count": 0,
  "timestamp": "2026-07-29T12:00:00+00:00"
}
```

Each alert is the stored CAP-style object (see [Alert object](#alert-object)), filtered to **enabled monitored counties**, with:

- `announced` — whether the alert was voice-announced
- `script_executed` — whether AlertScript ran for it

#### `GET /api/alerts/history`

| | |
|--|--|
| Auth | Public |
| Query | `limit` (default `100`), `hours` (default `24`) |

Requires database. **503** if unavailable.

```json
{
  "alerts": [
    {
      "id": "...",
      "event": "Severe Thunderstorm Warning",
      "severity": "Severe",
      "area_desc": "...",
      "effective_time": "...",
      "expires_time": "...",
      "processed_at": "...",
      "announced": true,
      "script_executed": false
    }
  ],
  "count": 1,
  "timestamp": "..."
}
```

#### `GET /api/alerts/{alert_id}/audio`

| | |
|--|--|
| Auth | Public |
| Response | Binary audio (`audio/wav`, `audio/mpeg`, …) — not JSON on success |

Generates TTS for an **active** alert id from `last_alerts`. **404** if expired/unknown · **503** if audio unavailable · **400** if id missing.

---

### Health, metrics, activity, updates

#### `GET /api/health`

| | |
|--|--|
| Auth | Public |

```json
{
  "overall_status": "healthy",
  "timestamp": "...",
  "uptime_seconds": 0,
  "version": "...",
  "system_info": { },
  "components": [
    {
      "name": "...",
      "status": "healthy",
      "message": "...",
      "response_time_ms": 1.2,
      "last_check": "...",
      "details": { }
    }
  ],
  "summary": { },
  "metrics": { }
}
```

**503** if health monitor unavailable.

#### `GET /api/health/history`

| | |
|--|--|
| Auth | Public |
| Query | `limit` — 1–500 (default `10`) |

Returns a **JSON array** (not wrapped) of summary records: `timestamp`, `overall_status`, `uptime_seconds`, `version`, component counts.

#### `GET /api/metrics`

| | |
|--|--|
| Auth | Public |
| Query | `hours` (default `24`), `metric_name` — optional: `performance`, `alerts`, `system`, or `health` to return only that slice |

Full response includes flattened overview fields (`total_requests`, `avg_response_time`, `error_rate`, `uptime_seconds`), plus `performance`, `requests`, `system` (CPU/memory/disk when available), and nested `metrics`.

When `metric_name` is set:

```json
{
  "timestamp": "...",
  "period_hours": 24,
  "metric_name": "system",
  "data": { }
}
```

#### `GET /api/activity`

| | |
|--|--|
| Auth | Public |
| Query | `limit` (default `20`) |

```json
{
  "activities": [
    {
      "type": "alert_processed",
      "message": "...",
      "details": "...",
      "timestamp": "...",
      "severity": "severe",
      "icon": "alert-triangle"
    }
  ],
  "count": 1,
  "timestamp": "..."
}
```

Activity types include `alert_processed`, `alert_announced`, `system_status`, `system_event`.

#### `GET /api/update-status`

| | |
|--|--|
| Auth | Public |
| Query | `force=1` — refresh GitHub latest-release cache immediately |

```json
{
  "check_enabled": true,
  "installed_version": "1.6.4",
  "update_available": false,
  "latest_version": null,
  "latest_tag": null,
  "release_url": null,
  "checked_at": null,
  "error": null
}
```

Respects `monitoring.update_check` (`enabled`, `interval_hours`, `github_repo`).

---

### Logs (session)

#### `GET /api/logs`

| | |
|--|--|
| Auth | Session |
| Query | `level` — empty/`ALL` or minimum severity (`DEBUG`…`CRITICAL`); `limit` 1–5000 (default `100`); `q` — case-insensitive substring |

```json
{
  "logs": [ ],
  "count": 0,
  "level": "ALL",
  "limit": 100
}
```

Entries are parsed JSON lines from the configured log file, or `{"message": "...", "level": "INFO"}` for plain lines.

---

### Database (session)

#### `GET /api/database/stats`

| | |
|--|--|
| Auth | Session |

```json
{
  "connected": true,
  "total_alerts": 0,
  "active_alerts": 0,
  "database_size_bytes": 0,
  "metrics_count": 0,
  "health_checks_count": 0,
  "script_executions_count": 0,
  "configurations_count": 0
}
```

**503** when the database is unavailable (`connected: false`).

#### `POST /api/database/cleanup`

| | |
|--|--|
| Auth | Session |
| Body | optional `{"days": 30}` — retain last N days; `days` must be 1–3650 |

**200:** `{"success": true, "message": "...", "stats": {…}}`

#### `POST /api/database/optimize`

| | |
|--|--|
| Auth | Session |
| Body | none |

**200:** `{"success": true, "message": "...", "stats": {…}}`

#### `POST /api/database/backup`

| | |
|--|--|
| Auth | Session |
| Body | none |

**200:** `{"success": true, "message": "...", "backup_path": "/path/to/backup"}`

---

### Configuration (session)

#### `GET /api/config`

| | |
|--|--|
| Auth | Session |

Returns the full application config as JSON (dashboard shape), with **secrets redacted** to empty strings (auth password, email/SMS/PushOver tokens, etc.). Also includes helpers such as `runtime_warnings`, `auth_uses_default_password`, `is_configured`, `tts_default_node_number`.

Blank secret fields on **POST** mean “keep the stored value.”

#### `POST /api/config`

| | |
|--|--|
| Auth | Session |
| Body | Partial or full config object (deep-merged into current config) |

Rate-limited per IP (**429**). If the default admin password is still set, saves are rejected (**403**) until Monitoring → Authentication sets a new password.

**200:**

```json
{
  "success": true,
  "message": "Configuration updated and saved successfully",
  "config_file": "/etc/skywarnplus-ng/config.yaml",
  "config": { }
}
```

**400** validation failure · **403** default password lock · `base_path` is preserved if omitted from the body.

#### `POST /api/config/reset`

| | |
|--|--|
| Auth | Session |

Restores from `config.yaml.example`, packaged default, or built-in defaults.

**200:** `{"success": true, "message": "...", "config_file": "..."}`

#### `POST /api/config/backup`

| | |
|--|--|
| Auth | Session |

Copies the live config to `config.yaml.backup.YYYYMMDD-HHMMSS` beside it.

**200:** `{"success": true, "message": "...", "backup_path": "..."}`

#### `POST /api/config/restore`

| | |
|--|--|
| Auth | Session |
| Body | optional `{"backup_path": "..."}` — must stay under the config directory and match `*.backup.*`; omit to use the newest backup |

**200:** `{"success": true, "message": "...", "restored_from": "...", "config_file": "..."}`

#### `POST /api/counties/{county_code}/generate-audio`

| | |
|--|--|
| Auth | Session |

TTS for the county’s configured name; updates `audio_file` in config when possible.

**200:** `{"success": true, "filename": "...", "message": "..."}`  
**404** unknown county · **503** audio unavailable.

#### `GET /api/tts/voices`

| | |
|--|--|
| Auth | Session |

```json
{
  "default": "en_US-amy-low.onnx",
  "regions": [ ],
  "voices_dir": "/var/lib/piper-tts",
  "voices": [
    {
      "id": "en_US-amy-low",
      "file": "en_US-amy-low.onnx",
      "label": "...",
      "installed": true,
      "catalog": true,
      "region": "..."
    }
  ]
}
```

#### `POST /api/tts/voices/install`

| | |
|--|--|
| Auth | Session |
| Body | `{"voice_id": "en_US-amy-low"}` (or `"id"`) |

**200:** `{"success": true, "message": "...", "file": "...", "voice": "..."}`  
**400** invalid/unknown voice.

---

### Notifications (session)

All routes under `/api/notifications/*` require a session. Prefer the dashboard UI for day-to-day edits; see [subscribers.md](subscribers.md) for filter semantics.

#### `POST /api/notifications/test-email`

Body (typical):

```json
{
  "provider": "gmail",
  "smtp_server": "",
  "smtp_port": 587,
  "use_tls": true,
  "use_ssl": false,
  "username": "...",
  "password": "",
  "from_name": "SkywarnPlus-NG"
}
```

Empty `password` reuses the saved SMTP password. **200:** `{"success": true|false, "message": "..."}`.

#### `POST /api/notifications/test-sms`

Body: `to` (E.164), `account_sid`, `from_number`, `auth_token` (blank = saved), optional `timeout_seconds`, `max_length`.

**200:** success/failure with optional `result` from Twilio.

#### `GET /api/notifications/subscribers`

Returns a **JSON array** of subscriber objects (`subscriber_id`, `name`, `email`, `status`, `preferences`, `phone`, `webhook_url`, `push_tokens`, timestamps, counters).

#### `POST /api/notifications/subscribers`

Required: `name`, `email`. Optional: `subscriber_id`, `status` (`active` / …), `phone`, `webhook_url`, `push_tokens`, preference fields (top-level or nested — see list below).

Preference field names accepted on create/update:

`counties`, `states`, `custom_areas`, `enabled_severities`, `enabled_urgencies`, `enabled_certainties`, `enabled_events`, `blocked_events`, `enabled_methods`, `immediate_delivery`, `batch_delivery`, `batch_interval_minutes`

Webhook URLs must be public HTTPS (private/localhost rejected).

**200:** `{"success": true, "message": "...", "subscriber_id": "..."}`

#### `PUT /api/notifications/subscribers/{subscriber_id}`

Partial update of the same fields. **404** if missing.

#### `DELETE /api/notifications/subscribers/{subscriber_id}`

**200** on delete · **404** if missing.

#### `GET /api/notifications/templates`

Array/list of available templates (engine-defined shape).

#### `GET /api/notifications/templates/{template_id}`

Single template · **404** if missing.

#### `POST /api/notifications/templates`

```json
{
  "template_id": "optional-uuid",
  "name": "...",
  "description": "",
  "template_type": "email",
  "format": "text",
  "subject_template": "...",
  "body_template": "...",
  "enabled": true
}
```

`template_type` / `format` are lowercased enums (`email`, `text`, …).

#### `PUT /api/notifications/templates/{template_id}`

Partial update of the fields above.

#### `DELETE /api/notifications/templates/{template_id}`

May **400** if the template cannot be removed (engine policy).

#### `GET /api/notifications/stats`

Notification manager stats when available; otherwise subscriber counts plus empty notifier/queue placeholders.

---

## Alert object

Active alerts (`GET /api/alerts`, WebSocket `alerts_update`) are dict snapshots of NWS CAP fields plus local metadata. Common keys:

| Field | Type | Notes |
|-------|------|--------|
| `id` | string | Alert id (use for `/api/alerts/{id}/audio`) |
| `event` | string | e.g. `Tornado Warning` |
| `headline` | string \| null | |
| `description` | string | |
| `instruction` | string \| null | |
| `severity` | string | `Extreme`, `Severe`, `Moderate`, `Minor`, `Unknown`, … |
| `urgency` | string | |
| `certainty` | string | |
| `status` | string | |
| `category` | string | |
| `sent`, `effective`, `expires` | datetime strings | |
| `onset`, `ends` | datetime \| null | |
| `area_desc` | string | May be narrowed to monitored counties |
| `geocode` | string[] | |
| `county_codes` | string[] | Filtered to enabled counties when configured |
| `sender`, `sender_name` | string | |
| `announced` | bool | API enrichment |
| `script_executed` | bool | API enrichment |

Geo-hazard / tropical items may carry additional source-specific fields when present in state.

`GET /api/status` uses a **different**, compact shape (`event`, `severity`, `headline` only) for Supermon/dashboard badges.

---

## HTML pages (not JSON)

These serve the UI; auth rules match the access model above.

| Path | Auth |
|------|------|
| `/login` | Public |
| `/`, `/dashboard` | Public |
| `/alerts`, `/alerts/history` | Public |
| `/health`, `/metrics`, `/activity` | Public |
| `/configuration`, `/logs`, `/database` | Session |
| `/static/...` | Public |

---

## Integration notes

1. **Supermon-ng** — poll `GET /api/status` (optionally `?nodes=…`). Keep `public_status_api: true` unless you terminate TLS and inject cookies another way.
2. **Automation** — login once, persist the cookie jar, call protected routes; prefer subscribers API over editing YAML for recipient provisioning.
3. **Proxies** — forward WebSocket Upgrade for `/ws` (or `/skywarnplus-ng/ws`); long read timeouts; strip or preserve prefix consistently with `base_path` ([nginx guide](../nginx-proxy-manager-guide.md)).

---

## Route index

| Method | Path | Auth |
|--------|------|------|
| POST | `/api/auth/login` | Public |
| POST | `/api/auth/logout` | Public |
| GET | `/api/status` | Public\* |
| GET | `/ws` | Public\* |
| GET | `/api/alerts` | Public |
| GET | `/api/alerts/history` | Public |
| GET | `/api/alerts/{alert_id}/audio` | Public |
| GET | `/api/health` | Public |
| GET | `/api/health/history` | Public |
| GET | `/api/metrics` | Public |
| GET | `/api/activity` | Public |
| GET | `/api/update-status` | Public |
| GET | `/api/logs` | Session |
| GET | `/api/database/stats` | Session |
| POST | `/api/database/cleanup` | Session |
| POST | `/api/database/optimize` | Session |
| POST | `/api/database/backup` | Session |
| GET | `/api/config` | Session |
| POST | `/api/config` | Session |
| POST | `/api/config/reset` | Session |
| POST | `/api/config/backup` | Session |
| POST | `/api/config/restore` | Session |
| POST | `/api/counties/{county_code}/generate-audio` | Session |
| GET | `/api/tts/voices` | Session |
| POST | `/api/tts/voices/install` | Session |
| POST | `/api/notifications/test-email` | Session |
| POST | `/api/notifications/test-sms` | Session |
| GET/POST | `/api/notifications/subscribers` | Session |
| PUT/DELETE | `/api/notifications/subscribers/{id}` | Session |
| GET/POST | `/api/notifications/templates` | Session |
| GET/PUT/DELETE | `/api/notifications/templates/{id}` | Session |
| GET | `/api/notifications/stats` | Session |

\* Depends on `auth.public_status_api`.
