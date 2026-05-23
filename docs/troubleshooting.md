# Troubleshooting

## Slack does not respond

Check:

1. Router process is running.
2. `SLACK_BOT_TOKEN` starts with `xoxb-`.
3. `SLACK_APP_TOKEN` starts with `xapp-`.
4. Socket Mode is enabled.
5. Bot is invited to the channel.
6. `SLACK_CHANNEL` matches the target channel ID.
7. `USER_SLACK_ID` matches your member ID.

## It answers generic Slack features

Ask:

```text
slack agent router app으로 뭐 할 수 있어?
```

Expected answer should describe agent-router-kit features: Claude/Codex routing, KMS workspace, Debate Mode, and optional SMS/Kakao inputs.

If it describes Slack search, Slack Canvas, or generic workspace admin features, the router prompt or capability answer path is wrong.

## `다음` or `계속` goes to the wrong mode

Expected:

- If Debate Mode is active, continue the debate.
- If Debate Mode is not active, treat it as normal continuation.
- Direct commands like Kakao, SMS, inbox, file, task, schedule, save, capture, archive, and register should not enter Debate Mode.

Use:

```text
리셋 토론
```

Then retry.

## Claude or Codex command is not found

Set explicit paths in the env file:

```env
CLAUDE_EXE=claude
CODEX_EXE=codex
```

On Windows, if your Codex launcher is a PowerShell script:

```env
CODEX_EXE=C:\path\to\codex.ps1
POWERSHELL_EXE=pwsh
```

## Windows scheduled task does not start

Run the installer with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1 -EnableKms -RegisterTask
```

Then check Task Scheduler for `AgentRouterKit`.

## macOS launchd does not start

Run:

```bash
bash ./scripts/install-macos.sh --enable-kms --register-launchd
```

Then check:

```bash
launchctl list | grep agent-router-kit
```

## SMS receiver health check

Open:

```text
http://<PC_LOCAL_IP>:8788/health
```

Expected:

```json
{"ok": true}
```

## Kakao input reads only one room

v1 intentionally prioritizes stable, explicit collection. Open or select the target room before collecting, or use an export/import flow where available.
