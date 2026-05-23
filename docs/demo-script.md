# Demo Script

Use this script to show the AI-assisted install story.

## 1. Positioning

This is not a normal developer library.

It is a kit that a non-developer can hand to Claude Code or Codex and say:

```text
INSTALL_WITH_AI.md 읽고 내 컴퓨터에 설치해줘.
```

## 2. Install Flow

Show:

1. Clone or download repo.
2. Open Claude Code or Codex.
3. Ask it to read `INSTALL_WITH_AI.md`.
4. Run dry run.
5. Run install.
6. Fill local Slack env values.
7. Start router.

## 3. Slack Demo

Send:

```text
덱스 안녕
```

Expected:

```text
덱스
연결 정상입니다.
```

Send:

```text
클로 안녕
```

Expected:

```text
클로
연결 정상입니다.
```

Send:

```text
둘이 토론해
```

Expected:

- Debate Mode starts.
- Dex speaks from structure/execution.
- Chlo speaks from brand/reader experience.
- They respond to each other before agreement.

Send:

```text
업무 할일 테스트 작업
```

Expected:

- Creates or routes a KMS task.
- Does not fall into stale Debate Mode.

Send:

```text
slack agent router app으로 뭐 할 수 있어?
```

Expected:

- Describes this app, not generic Slack features.

## 4. Optional Module Demo

SMS:

```text
Run SMS receiver, send test POST, confirm local ledger.
```

Kakao:

```text
Collect from intentionally opened Kakao room, then ask Slack to classify recent Kakao inputs.
```

## 5. Close

End with the product promise:

```text
Slack is the control surface. Local KMS is the operating folder. Claude and Codex are the workers.
```
