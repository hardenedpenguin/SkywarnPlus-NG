# Notifications overview

SkywarnPlus-NG can notify you outside the repeater when NWS alerts are processed. Configuration lives in the dashboard under **Configuration**.

## What sends automatically

When a **new** alert is processed (or all-clear is issued), these channels are wired in the main alert loop:

| Channel | Where to configure | Scope | All-clear |
|---------|-------------------|-------|-----------|
| **PushOver** | **Configuration → Monitoring → PushOver** | Every new alert for all monitored counties | Yes |
| **Email (SMTP)** | **Configuration → Notifications → Email** + **Subscribers** | Per subscriber (filters apply) | Yes (subscribers) |
| **Discord / Slack / Teams / generic webhook** | **Subscribers** (per-recipient URL) or **Notifications → Webhooks** (global URLs) | Per subscriber or global broadcast | Yes |
| **FCM push** | **Configuration → Notifications → Push** + subscriber device tokens | Per subscriber | Yes (subscribers) |

PushOver remains a separate global destination (one user key). Email, webhooks, and FCM use the shared **NotificationManager**, which also runs the delivery queue for batch/retry delivery.

## Dashboard sections

| Tab | Purpose |
|-----|---------|
| **Monitoring → PushOver** | API token, user key, optional fixed priority/sound |
| **Notifications → Notifications** | SMTP email, Slack/Teams/generic webhook URLs, FCM keys, delivery tuning |
| **Notifications → Subscribers** | Named recipients with filters and delivery methods |
| **Notifications → Templates** | Customize notification text |
| **Monitoring → DEV** | Test alert injection (development only) |

Subscriber data is stored at:

```text
/var/lib/skywarnplus-ng/data/subscribers.json
```

Delivery queue and templates live alongside it under `data_dir`. Secrets (SMTP password, FCM key) are stored in `/etc/skywarnplus-ng/config.yaml` and redacted in the dashboard API.

## Delivery queue and batch mode

The delivery processor starts with the application and handles:

- Retries for failed email, webhook, and push deliveries
- **Batch delivery** when a subscriber enables it (notifications are queued until the batch interval elapses)

Tune concurrency, timeout, and retries under **Notifications → Delivery Settings**.

## SMS

Subscriber UI includes SMS as a delivery method placeholder. SMS is **not** implemented yet; enabling it logs a clear failure without affecting other channels.

## Security: webhook URLs

All webhook URLs must be **public HTTPS** endpoints. Private IPs, `localhost`, and link-local addresses are rejected. This applies to subscriber webhooks and global webhook fields in the UI.

## Testing notifications

1. Open **Configuration → Monitoring → DEV**.
2. Enable **Test alert injection** (disable again in production).
3. Save configuration.
4. Watch logs:

   ```bash
   journalctl -u skywarnplus-ng -f
   ```

5. Look for lines such as `PushOver notification sent`, `Alert notifications sent`, or delivery queue activity.

Injected alerts follow the same notification path as real NWS alerts.

## Quick links

- [PushOver setup](pushover.md)
- [Discord webhooks](discord-webhooks.md)
- [Email SMTP](email.md)
- [Subscribers and filters](subscribers.md)
