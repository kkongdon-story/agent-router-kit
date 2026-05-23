# Security

agent-router-kit runs local commands from Slack. Treat it like a private local automation tool, not a public bot.

## Hard Rules

- Never commit `.env` files.
- Never paste real Slack tokens into AI chat.
- Use a private Slack channel for the router.
- Invite only trusted users.
- Keep the router on a computer you control.
- Review optional SMS/Kakao collection before enabling it.

## Secret Locations

Windows:

```text
%USERPROFILE%\.agent-router-kit\secrets\slack-agent-router.env
```

macOS:

```text
~/.agent-router-kit/secrets/slack-agent-router.env
```

## Slack Token Scope

Use the smallest scopes that make the router work. Do not grant workspace admin permissions.

Required app-level scope:

- `connections:write`

Required bot token scopes:

- `app_mentions:read`
- `channels:history`
- `channels:read`
- `chat:write`
- `groups:history`
- `groups:read`
- `im:history`
- `im:read`
- `mpim:history`
- `mpim:read`

## Local Command Risk

The router can launch Claude Code or Codex locally. If a Slack user can talk to the bot, they can potentially ask it to inspect files or run tasks within the configured workspace.

Recommended mitigations:

- Use `SLACK_CHANNEL` to restrict the channel.
- Use `USER_SLACK_ID` to restrict the primary operator.
- Keep `PROJECT_ROOT` scoped to a safe folder.
- Do not point it at your whole home folder.
- Review logs after first install.

## SMS and Kakao Risk

SMS and Kakao may include private messages, financial records, authentication codes, and personal identifiers.

Recommended mitigations:

- Store raw data locally.
- Do not sync raw ledgers to public cloud.
- Redact account numbers and authentication codes before sharing.
- Keep optional modules disabled until you know why you need them.

## Public Repo Checklist

Before publishing:

- No real `xoxb-` token.
- No real `xapp-` token.
- No personal phone numbers.
- No personal Windows paths.
- No real Slack channel IDs except placeholders.
- No private Kakao exports.
