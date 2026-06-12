# Email notifications

SkywarnPlus-NG includes SMTP configuration and subscriber email support in the dashboard. This guide covers setup and current behavior.

## SMTP configuration

1. Open **Configuration → Notifications → Notifications**.
2. Under **Email Notifications**, choose a provider preset or **Custom**.
3. Enter SMTP settings:

| Field | Gmail example |
|-------|----------------|
| SMTP server | `smtp.gmail.com` |
| Port | `587` |
| Username | your Gmail address |
| Password | [App password](https://myaccount.google.com/apppasswords) (not your login password) |
| Use TLS | On |
| Use SSL | Off (for port 587) |
| From name | `SkywarnPlus-NG` |

4. Click **Test Email Connection** before saving.
5. **Save Configuration**.

Settings are stored under `notifications.email` in `/etc/skywarnplus-ng/config.yaml`. When SMTP is configured and subscribers have email enabled, new alerts and all-clear events are sent automatically through the notification manager.

### Other providers

| Provider | SMTP server | Port | Notes |
|----------|-------------|------|-------|
| Outlook | `smtp-mail.outlook.com` | 587 | TLS |
| Yahoo | `smtp.mail.yahoo.com` | 587 | Often requires app password |
| iCloud | `smtp.mail.me.com` | 587 | App-specific password |
| Custom | your host | 587 or 465 | Match TLS/SSL to your provider |

### YAML example (Gmail)

```yaml
notifications:
  email:
    provider: gmail
    smtp_server: smtp.gmail.com
    smtp_port: 587
    username: you@gmail.com
    password: "your-app-password"
    from_name: SkywarnPlus-NG
    use_tls: true
    use_ssl: false
```

## Subscriber email

To prepare recipients for email delivery:

1. **Configuration → Notifications → Subscribers → Add Subscriber**
2. Enter name and email address.
3. Enable the **Email** notification method.
4. Set county, severity, and event filters as needed.
5. Save.

Subscriber records live in `/var/lib/skywarnplus-ng/data/subscribers.json`.

## Current alert delivery behavior

**Important:** SMTP settings and **Test Email Connection** work today. Subscriber email on **live NWS alerts** is implemented in `NotificationManager` but that manager is **not yet hooked into** the main alert processing loop.

Automatic email on new alerts is planned; until then:

- Use **PushOver** or **Discord** for automatic mobile/channel alerts — see [PushOver](pushover.md) and [Discord webhooks](discord-webhooks.md).
- Use **AlertScripts** to call `mail`, `sendmail`, or a custom script when specific events fire — see **Configuration → Scripts** and examples in `config/default.yaml`.

## Troubleshooting SMTP test

| Problem | Fix |
|---------|-----|
| Authentication failed (Gmail) | Enable 2FA and create an app password; “Less secure apps” is no longer supported |
| Connection timeout | Outbound port 587 blocked on firewall; try provider’s SSL port with `use_ssl: true` |
| Test passes, no alert emails | Expected until subscriber email is wired to the alert loop — use Discord/PushOver or scripts |

See also: [Subscribers](subscribers.md) · [Notifications overview](notifications-overview.md)
