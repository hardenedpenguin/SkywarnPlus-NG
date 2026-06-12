# SMS notifications (Twilio)

SkywarnPlus-NG can send **short text messages** to subscribers through [Twilio](https://www.twilio.com/). 

## Setup

1. Create a [Twilio](https://www.twilio.com/try-twilio) account and buy or verify a phone number that can send SMS.
2. In the dashboard, open **Configuration → Notifications → SMS (Twilio)**.
3. Enter **Account SID**, **Auth Token**, and **From Number** (your Twilio number in E.164, e.g. `+15551234567`).
4. Enable **Twilio SMS** and save.
5. Add subscribers with **Phone** (E.164) and enable the **SMS** delivery method.

Twilio charges per message; check [Twilio pricing](https://www.twilio.com/sms/pricing) for your region.

## Message format

Bodies are kept near **160 characters** by default. Example:

```text
⚠ Tornado Warning
Harris County
Until 05/18 3:00 PM UTC
```

Customize under **Notifications → Templates** (`sms_alert_default`).

## All-clear

SMS on all-clear is **off by default**. Enable **Send SMS on all-clear** if subscribers should get a short text when alerts clear.

## Testing

1. Fill in Twilio credentials in the SMS section.
2. Enter a **Test Phone Number** (must be verified on trial accounts).
3. Click **Test Twilio SMS**.

## Security

Auth Token is stored in `config.yaml` and redacted in the dashboard API. Leave the token field blank when saving other settings to keep the current value.

## Alternatives without SMS

PushOver, email, FCM push, and Discord/Slack webhooks already reach phones without per-message cost.

See also: [Subscribers](subscribers.md) · [Notifications overview](notifications-overview.md)
