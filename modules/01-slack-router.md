# Module 01. Slack Router

Slack Router is the core module. It turns a Slack channel into a control surface for local Claude Code and Codex sessions.

## Commands

```text
덱스 <request>
클로 <request>
둘 다 <request>
둘이 토론해
다음
계속
리셋 토론
slack agent router app으로 뭐 할 수 있어?
```

Legacy commands are also supported:

```text
!codex <request>
!claude <request>
!reset codex
!reset claude
```

## Required Slack Scopes

Bot token scopes:

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

App-level token scope:

- `connections:write`

## Context Guard

The router classifies intent before continuing Debate Mode. Direct commands such as Kakao, SMS, inbox, file, task, schedule, save, capture, archive, and register should not be swallowed by a stale debate state.

## Debate Mode

Debate Mode is for structured Dex/Chlo discussion.

- Dex: structure, execution, systems, scalability
- Chlo: brand perception, style, emotional line, reader experience

`다음` and `계속` only continue Debate Mode when the previous state is an active debate.
