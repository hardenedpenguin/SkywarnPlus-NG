# Discord webhooks

Discord is the recommended way to send **filtered** alert notifications to a channel. Each subscriber can have its own webhook URL and county/severity/event preferences.

Discord webhooks must be configured through **Subscribers**, not the global Slack/Teams fields on the Notifications tab. The alert loop only delivers to subscriber URLs that contain `discord.com/api/webhooks`.

## Create a Discord webhook

1. In Discord, open your server → **Server Settings → Integrations → Webhooks**.
2. Click **New Webhook**, choose a channel, and copy the **Webhook URL**.
3. The URL looks like:

   ```text
   https://discord.com/api/webhooks/123456789/abcdef...
   ```

Only `https://` URLs to Discord’s webhook host are accepted.

## Add a subscriber

1. Open **Configuration → Notifications → Subscribers**.
2. Click **Add Subscriber**.
3. Fill in **Name** and **Email** (email is required by the form even if you only use webhooks).
4. Paste the **Webhook URL**.
5. Under **Notification Methods**, enable **Webhook**.
6. Set filters (optional but recommended):
   - **Counties** — e.g. `TXC039, TXC201` ([county code list](../CountyCodes.md)). Leave empty to match all counties in alerts.
   - **States** — two-letter codes, e.g. `TX`.
   - **Enabled events** — e.g. `Tornado Warning`. Leave empty for all event types.
   - **Blocked events** — substring match, e.g. `*Advisory`.
   - **Severity / Urgency** checkboxes — uncheck levels you do not want.
7. Set **Status** to **Active** and save.

Repeat for each Discord channel or audience that needs different filters.

## What Discord receives

Alerts are sent as a Discord **embed** with:

- Event title and area description
- Severity, urgency, certainty
- Effective and expire times
- Description and instructions (truncated if very long)
- Color by severity (yellow → red → purple for higher levels)

Duplicate delivery is prevented: each alert ID is marked after a successful Discord post so the same alert is not sent twice to the same webhook.

## Multiple subscribers

You can add several subscribers with different webhooks:

- `#wx-severe` — counties A/B, Severe and Extreme only
- `#wx-local` — one county, all severities
- `#wx-statewide` — state filter `TX`, tornado and severe thunderstorm in enabled events

Each matching subscriber gets its own webhook POST when a new alert arrives.

## Testing

1. Enable **DEV → Test alert injection** under **Configuration → Monitoring**.
2. Save, then tail logs:

   ```bash
   journalctl -u skywarnplus-ng -f
   ```

3. Confirm `Discord webhook notification sent` and check your Discord channel.

Use county codes in the injected alert that match your subscriber filters.

## Troubleshooting

| Problem | What to check |
|---------|----------------|
| Webhook rejected on save | URL must be `https://` and a public Discord webhook URL |
| No message in Discord | Subscriber **Active**, **Webhook** method enabled, counties/events match the alert |
| `already sent for alert` in logs | Normal — deduplication for that alert ID |
| Wrong channel | Edit webhook in Discord or update subscriber URL |

Slack and Microsoft Teams URLs in **Configuration → Notifications** are saved to config but are **not** sent automatically on alerts yet. For Slack/Teams today, use AlertScripts or wait for full NotificationManager integration.

See also: [Subscribers](subscribers.md) · [Notifications overview](notifications-overview.md)
