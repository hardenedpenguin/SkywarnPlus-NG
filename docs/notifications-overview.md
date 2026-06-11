# Notifications overview

SkywarnPlus-NG can notify you outside the repeater when NWS alerts are processed. Configuration lives in the dashboard under **Configuration**.

## What sends automatically today

When a new alert is processed (or all-clear is issued), these channels are wired in the main alert loop:

| Channel | Where to configure | Scope | All-clear |
|---------|-------------------|-------|-----------|
| **PushOver** | **Configuration → Monitoring → PushOver** | Every new alert for all monitored counties | Yes |
| **Discord webhook** | **Configuration → Subscribers** (webhook URL must contain `discord.com/api/webhooks`) | Per subscriber — county, severity, event filters | No |

PushOver is a single global destination (one user key). Discord uses the subscriber system so different people or channels can get different subsets of alerts.

## Dashboard sections

| Tab | Purpose |
|-----|---------|
| **Monitoring → PushOver** | API token, user key, optional fixed priority/sound |
| **Notifications → Notifications** | SMTP email, Slack/Teams/generic webhook URLs, FCM keys, delivery tuning |
| **Notifications → Subscribers** | Named recipients with filters and delivery methods |
| **Notifications → Templates** | Customize notification text (used by the notification subsystem) |
| **Monitoring → DEV** | Test alert injection (development only) |

Subscriber data is stored at:

```text
/var/lib/skywarnplus-ng/data/subscribers.json
```

(backed up with your node; not in `/etc/skywarnplus-ng/config.yaml`).

## Email, Slack, Teams, FCM, and generic webhooks

The **Notifications** tab saves SMTP and webhook settings to `config.yaml`, and **Test Email Connection** verifies SMTP credentials. The subscriber UI also supports email, webhook, and push methods with rich filtering.

Those pieces share a `NotificationManager` in the codebase, but that manager is **not yet called** from the main alert processing loop. Only PushOver and Discord (via subscribers) fire on live alerts today.

If you need email or a non-Discord webhook immediately, use **AlertScripts** (**Configuration → Scripts**) to run your own command when specific events arrive — see the examples in `config/default.yaml`.

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

5. Look for lines such as `PushOver notification sent` or `Discord webhook notification sent`.

Injected alerts follow the same notification path as real NWS alerts.

## Quick links

- [PushOver setup](pushover.md)
- [Discord webhooks](discord-webhooks.md)
- [Email SMTP](email.md)
- [Subscribers and filters](subscribers.md)
