# Slack Agent Router

Local router for one Slack app that can call both Claude Code and Codex.

## Slack Commands

- `클로 <message>` routes to Claude Code.
- `덱스 <message>` routes to Codex.
- `클로야 <message>` and `덱스야 <message>` also work.
- The older `!claude` and `!codex` commands still work.
- Plain messages route to `DEFAULT_AGENT`.
- Plain messages start in the dedicated `AGENT_WORKDIR`.
- Ask `slack agent router app으로 뭐 할 수 있어?` to see the local app capability contract.
- Prefix a request with `업무` for the KMS workspace context.
- Prefix a request with `작업` for the light inbox/workspace context.
- Prefix a request with `자료` or `프로젝트` to attach `PROJECT_ROOT` as read-only reference material.
- Use `덱스 카카오 나에게 보내기 할 일 정리해줘` to route Kakao self-room intake through KMS.
- Use `둘이 토론해`, `다음`, and `계속` for Debate Mode. Pure continuations only continue an active debate.
- `리셋 클로` resets Claude channel session.
- `리셋 덱스` resets Codex channel session.
- `리셋 토론` clears Debate Mode state.
- `!help` prints the command list in Slack.

## Context Guard

Slack is the control surface and KMS is the operating system. Ordinary Slack chat is not automatically stored as KMS input. Explicit KMS actions such as Kakao, SMS, inbox, file, task, schedule, save, capture, archive, and register requests are classified before Debate Mode, so stale debate context cannot swallow a new direct command.

## Install Shape

Copy `daemon.py` to:

`{USER_HOME}/.agent-router-kit/slack-agent-router/daemon.py`

Copy `slack-agent-router.env.example` to:

`{USER_HOME}/.agent-router-kit/secrets/slack-agent-router.env`

Then fill Slack tokens locally. Do not paste real tokens into chat.

The generated `run.ps1` should set `AGENT_ROUTER_ENV` and run the daemon with the chosen Python executable.

Use Windows Task Scheduler to start `run.ps1` at logon.
