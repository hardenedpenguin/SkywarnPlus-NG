# PushOver notifications

PushOver sends mobile push notifications when SkywarnPlus-NG processes a new NWS alert or an all-clear.

PushOver is **global**: it is not filtered by county or severity in the subscriber system. Every alert that passes your normal SkywarnPlus filtering (blocked events, max alerts, etc.) triggers a push to the configured user key.

## Prerequisites

1. A [PushOver](https://pushover.net/) account on your phone or desktop.
2. A PushOver **application** API token — create one at [pushover.net/apps/build](https://pushover.net/apps/build).
3. Your **user key** from the PushOver dashboard.

## Configure in the dashboard

1. Open **Configuration → Monitoring**.
2. Scroll to **PushOver Notifications**.
3. Enable **Enable PushOver Notifications**.
4. Enter **Application API Token** and **User Key**.
5. Optionally set:
   - **Default priority** (−2 to 2) — if set, this **overrides** automatic severity-based priority (see below).
   - **Sound** — if set, overrides automatic sound selection.
   - **Timeout** — HTTP timeout in seconds.
6. Click **Save Configuration**.

Settings are written to `/etc/skywarnplus-ng/config.yaml` under the `pushover:` key.

## Automatic priority and sound

When default priority and sound are left at their defaults in config, PushOver adjusts delivery by alert severity:

| Severity | Urgency | Priority | Sound (examples) |
|----------|---------|----------|------------------|
| Extreme | Immediate | Emergency (2) | `siren` — repeats until acknowledged |
| Extreme | Other | High (1) | `persistent` |
| Severe | Immediate | High (1) | `persistent` |
| Severe | Other | Normal (0) | `pianobar` |
| Moderate | — | Normal (0) | `incoming` |
| Minor / unknown | — | Normal (0) | `magic` |

Emergency priority uses PushOver’s retry/expire parameters so critical alerts keep notifying.

## All-clear

When SkywarnPlus-NG announces all-clear on the node, a separate PushOver message is sent (if PushOver is enabled and credentials are set).

## YAML example

```yaml
pushover:
  enabled: true
  api_token: "your-app-token"
  user_key: "your-user-key"
  priority: 0          # omit or null to use severity-based priority
  sound: null          # omit for automatic sound
  timeout_seconds: 30
  retry_count: 3
  retry_delay_seconds: 5
```

## Troubleshooting

| Problem | What to check |
|---------|----------------|
| No push on test alert | PushOver enabled, both token and user key set, DEV injection enabled for testing |
| Wrong priority every time | Fixed `pushover.priority` in config overrides automatic severity logic — clear it to restore auto |
| `PushOver notification failed` in logs | Invalid token/key, network egress blocked, or PushOver API outage |
| Too many notifications | PushOver receives every alert county — use Discord subscribers or AlertScripts for selective delivery |

Log file: `/var/log/skywarnplus-ng/skywarnplus-ng.log` or `journalctl -u skywarnplus-ng -f`.

See also: [Notifications overview](notifications-overview.md).
