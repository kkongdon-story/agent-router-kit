# Module 02. KMS Workspace

KMS workspace is a local operating folder for inputs and processed outputs.

## Structure

```text
workspace/kms/
  inputs/
    slack/
    sms/
    kakao/
    folder/
  processed/
    tasks/
    memos/
    finance/
    schedules/
    content/
    questions/
    noise/
  ledger/
    sms/
    kakao/
    logs/
```

## Rule

Slack is a control surface. It is not automatically stored as input.

Store something only when the user explicitly asks for capture, save, archive, task creation, schedule extraction, Kakao ingestion, SMS ingestion, or folder processing.

## Recommended Flow

1. Inputs land in `workspace/kms/inputs/<source>`.
2. A classifier decides whether the item is task, memo, finance, schedule, content, question, or noise.
3. Processed markdown lands in `workspace/kms/processed/<category>`.
4. Raw event records and logs land in `workspace/kms/ledger/<source>`.

## Future Extensions

Notion, Google Drive, and Google Calendar can mirror processed outputs later, but v1 keeps local files as the source of truth.
