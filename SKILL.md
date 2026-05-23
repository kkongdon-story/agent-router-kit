# Agent Router Kit Installer Skill

Use this skill when helping a user install, verify, or troubleshoot `agent-router-kit`.

## Goal

Install a local Slack-based personal agent router that can call Claude Code and Codex from Slack, with optional local workspace, SMS input, and Kakao input modules.

## Rules

- Never ask the user to paste real Slack tokens into chat.
- Keep secrets in the local env file only.
- Run a dry run before mutating the machine.
- Prefer the bundled install scripts over manual copy steps.
- Keep local workspace, SMS, and Kakao optional unless the user explicitly enables them.
- Do not enable Notion, Google Drive, or Google Calendar in v1.
- When the user asks what the app can do, answer about agent-router-kit, not generic Slack connector features.

## Installation Flow

1. Identify OS.
2. Confirm Python 3 is available.
3. Confirm Claude Code and/or Codex CLI launchers are available.
4. Run dry-run installer.
5. Run installer with local workspace enabled.
6. Tell the user the env file path.
7. Guide the user through Slack App setup.
8. Ask the user to fill local env values.
9. Start the router.
10. Verify Slack commands.

## Windows

Dry run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1 -DryRun -EnableWorkspace
```

Install:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1 -EnableWorkspace
```

Start at logon:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1 -EnableWorkspace -RegisterTask
```

Env file:

```text
%USERPROFILE%\.agent-router-kit\secrets\slack-agent-router.env
```

Run file:

```text
%USERPROFILE%\.agent-router-kit\slack-agent-router\run.ps1
```

## macOS

Dry run:

```bash
bash ./scripts/install-macos.sh --dry-run --enable-workspace
```

Install:

```bash
bash ./scripts/install-macos.sh --enable-workspace
```

Start at login:

```bash
bash ./scripts/install-macos.sh --enable-workspace --register-launchd
```

Env file:

```text
~/.agent-router-kit/secrets/slack-agent-router.env
```

Run file:

```text
~/.agent-router-kit/slack-agent-router/run.sh
```

## Slack App Setup

Minimum setup:

- Create Slack App from scratch.
- Enable Socket Mode.
- Create App-Level Token with `connections:write`.
- Add bot token scopes:
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
- Install app to workspace.
- Invite bot to the target channel.

Required env values:

```env
SLACK_BOT_TOKEN=
SLACK_APP_TOKEN=
SLACK_CHANNEL=
USER_SLACK_ID=
DEFAULT_AGENT=codex
CLAUDE_EXE=claude
CODEX_EXE=codex
```

## Verification

Before real Slack token testing, run the public release verifier when possible:

```powershell
.\scripts\verify-release.ps1
```

Send these in Slack:

```text
코덱스 안녕
클로드 안녕
둘이 토론해
업무 할일 테스트 작업
slack agent router app으로 뭐 할 수 있어?
```

Expected:

- `코덱스` routes to Codex.
- `클로드` routes to Claude.
- `덱스` and `클로` are only example aliases. Users can change them with `CODEX_ALIASES` and `CLAUDE_ALIASES`.
- Debate Mode uses the tiktaka debate protocol.
- Work/task commands do not get swallowed by stale Debate Mode.
- Capability questions describe agent-router-kit.

## Optional Modules

Local workspace:

- `ENABLE_WORKSPACE=1`
- Creates local input, processed, and ledger folders.

SMS:

- `ENABLE_SMS=1`
- Use Android Tasker or iPhone Shortcuts to POST events to the local receiver.

Kakao:

- `ENABLE_KAKAO=1`
- v1 is Windows PC Kakao first.
- Collect only rooms the user intentionally opens or exports through the configured reader.

## User-facing Docs

- `docs/beginner-tutorial.md`: step-by-step tutorial for non-developers.
- `docs/feature-reference.md`: commands, env variables, aliases, folder layout, and optional modules.
- `docs/e2e-checklist.md`: fresh install and real Slack connection checklist.

## Troubleshooting

If the router does not respond:

1. Check env file values.
2. Check bot was invited to the channel.
3. Check Socket Mode app token starts with `xapp-`.
4. Check bot token starts with `xoxb-`.
5. Check local run logs under `.agent-router-kit/slack-agent-router/logs`.
6. Restart the router.
