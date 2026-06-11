# Subscribers

Subscribers are named recipients with optional filters controlling **which** alerts they should receive and **how** they should be notified.

Manage them under **Configuration → Notifications → Subscribers**. Data is persisted to:

```text
/var/lib/skywarnplus-ng/data/subscribers.json
```

Back up this file when migrating nodes. It is separate from `/etc/skywarnplus-ng/config.yaml`.

## Adding a subscriber

1. Click **Add Subscriber**.
2. Required fields: **Name**, **Email** (used as the subscriber identifier even for webhook-only users).
3. Optional contact fields: **Phone**, **Webhook URL**, **Push tokens** (one FCM token per line).
4. Choose **Notification Methods**:
   - **Email** — SMTP must be configured; automatic delivery on alerts not yet wired (see [Email](email.md)).
   - **Webhook** — **Discord only** is sent on live alerts today (`discord.com/api/webhooks` URLs). See [Discord webhooks](discord-webhooks.md).
   - **Push** — FCM keys in Notifications tab; push delivery not yet wired on alerts.
   - **SMS** — reserved for future use.
5. Set **Status** to **Active** when ready.

## Geographic filters

| Field | Behavior |
|-------|----------|
| **Counties** | Comma-separated NWS codes (e.g. `TXC039, TXC201`). Empty = no county restriction. |
| **States** | Two-letter state codes. Used with counties; can match when NWS returns zone codes (`TXZ*`) instead of county codes (`TXC*`). |
| **Custom areas** | Substrings matched against the alert area description (case-insensitive). |

County codes: [CountyCodes.md](../CountyCodes.md).

## Event and severity filters

| Field | Behavior |
|-------|----------|
| **Enabled events** | If empty, all events allowed (subject to blocks). If set, alert event name must contain one listed string (case-insensitive). |
| **Blocked events** | Substring match — if the event name contains a blocked string, the subscriber is skipped. |
| **Severity** | Minor, Moderate, Severe, Extreme checkboxes. |
| **Urgency** | Future, Expected, Immediate. |
| **Certainty** | Possible, Likely, Observed (in the subscriber modal). |

## Rate limits and quiet hours

Each subscriber tracks notifications per hour and per day (defaults: 10/hour, 50/day). Optional quiet hours (start/end/timezone) suppress delivery during those windows.

These limits apply when the notification subsystem delivers to subscribers.

## Notification templates

**Configuration → Notifications → Templates** defines reusable message formats (email, webhook, push). Templates are used by `NotificationManager` when subscriber delivery is fully integrated.

## Delivery status summary

| Method | Configured in | Live on NWS alerts |
|--------|---------------|-------------------|
| Discord webhook | Subscriber webhook URL | Yes |
| Email | Subscriber + SMTP | Not yet (SMTP test works) |
| Webhook (non-Discord) | Subscriber or Notifications tab | Not yet |
| Push (FCM) | Subscriber tokens + FCM keys | Not yet |
| PushOver | Monitoring tab (not subscribers) | Yes — see [PushOver](pushover.md) |

## API

Subscribers can also be managed via the dashboard API (`/api/notifications/subscribers` and related routes) if you automate provisioning.

See also: [Notifications overview](notifications-overview.md)
