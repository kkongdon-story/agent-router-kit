# Module 01. Slack Router

Slack Router is the core module. It turns a Slack channel into a control surface for local Claude Code and Codex sessions.

## Commands

```text
코덱스 <request>
클로드 <request>
둘 다 <request>
둘이 토론해
다음
계속
리셋 토론
slack agent router app으로 뭐 할 수 있어?
```

`덱스`, `클로`는 공식 명칭이 아니라 사용자가 정할 수 있는 짧은 별칭입니다. 기본 공식 호출명은 `코덱스`와 `클로드`이며, `CODEX_ALIASES`, `CLAUDE_ALIASES`에서 원하는 이름으로 바꿀 수 있습니다.

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

Debate Mode is for structured Codex/Claude discussion.

- Codex: structure, execution, systems, scalability
- Claude: brand perception, style, emotional line, reader experience

`다음` and `계속` only continue Debate Mode when the previous state is an active debate.
