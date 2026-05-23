# Module 03. SMS Input

SMS input is optional. It collects card usage, deposits, withdrawals, inquiries, authentication codes, and notification messages into the local workspace.

## Android

Use Tasker.

High-level flow:

1. Create a Tasker profile for received SMS or selected notification events.
2. Send an HTTP POST to the local receiver.
3. The receiver stores raw events in SQLite and writes processed markdown when a task or important item is detected.

Local receiver:

```powershell
python .\scripts\sms_receiver.py
```

Default endpoint:

```text
http://<PC_LOCAL_IP>:8788/sms
```

Example JSON body:

```json
{
  "sender": "%SMSRF",
  "sender_name": "%SMSRN",
  "body": "%SMSRB",
  "sms_date": "%SMSRD",
  "sms_time": "%SMSRT",
  "source": "android_tasker_sms"
}
```

For notification-based collection, include app package/title/text fields when Tasker provides them.

## iPhone

Use Shortcuts Automation where available. iOS may require confirmation depending on security settings and trigger type.

High-level flow:

1. Create a personal automation for message or app notification conditions.
2. Use "Get Contents of URL".
3. Set method to POST.
4. Send JSON to the receiver endpoint.

## Privacy

SMS often contains sensitive financial and authentication data. Keep it local by default. Do not push raw SMS logs to public repos or AI chat.
