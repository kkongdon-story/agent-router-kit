# Module 04. Kakao Input

Kakao input is optional. v1 is Windows PC Kakao first.

## Goal

Use Kakao as another input source, then route collected text into KMS instead of treating Kakao as a separate operating system.

## Recommended v1 Scope

- Self-room or intentionally opened rooms
- Manual or scheduled reader execution
- Local markdown/SQLite storage first
- No cloud sync by default

## Why Not Always-On Full Reading

Windows desktop apps often do not expose every chat room as clean text to automation tools. The stable approach is to read rooms the user intentionally opens or exports, then process those records locally.

## KMS Flow

1. Collect Kakao messages.
2. Save raw records under `workspace/kms/ledger/kakao`.
3. Save input markdown under `workspace/kms/inputs/kakao`.
4. Classify into tasks, memos, schedules, content, questions, or noise.

## Slack Usage

Examples:

```text
덱스 카카오 나에게 보내기 방에서 들어온 할 일 정리해줘
작업 카카오 최근 2시간 수집분 요약해줘
업무 카카오에서 일정으로 보이는 것만 뽑아줘
```

Slack is the command surface. Kakao is an input source. KMS is the operating folder.
