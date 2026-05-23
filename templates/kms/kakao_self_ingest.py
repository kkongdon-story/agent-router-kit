from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LEGACY_SYSTEM_DIR = Path("workspace") / "system" / "kakao"
KMS_DIR = Path("workspace") / "kms"
KMS_INPUTS_DIR = KMS_DIR / "inputs"
KAKAO_INPUT_DIR = KMS_INPUTS_DIR / "kakao"
KMS_PROCESSED_DIR = KMS_DIR / "processed"
TASKS_DIR = KMS_PROCESSED_DIR / "tasks"
MEMOS_DIR = KMS_PROCESSED_DIR / "memos"
HOLD_DIR = KMS_PROCESSED_DIR / "hold"
KMS_LEDGER_DIR = KMS_DIR / "ledger"
SYSTEM_DIR = KMS_LEDGER_DIR / "kakao"
LOGS_DIR = KMS_LEDGER_DIR / "logs"
STATE_NAME = "kakao-self-ingest-state.json"
EVENTS_DB_NAME = "kakao-self-events.sqlite"
EVENTS_JSONL_NAME = "kakao-self-events.jsonl"
DEFAULT_USER_ID = "local-user"
DEFAULT_CHAT_ID = "kakao-self"

TASK_KEYWORDS = (
    "해야",
    "할 일",
    "정리해",
    "정리해줘",
    "확인",
    "처리",
    "답변",
    "작성",
    "만들어",
    "보내",
    "예약",
    "미팅",
    "회의",
    "전화",
    "연락",
    "문의",
    "마감",
    "오늘까지",
    "내일까지",
    "해줘",
)
HOLD_TEXTS = {"", "음", "ㅇ", "ㅇㅇ", "흠", "메모", "테스트"}
PHONE_RE = re.compile(r"(?<!\d)(?:\+?82[-\s]?)?0?1[016789][-\s]?\d{3,4}[-\s]?\d{4}(?!\d)")
OTP_RE = re.compile(r"(?<!\d)\d{4,8}(?!\d)")


def force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def ensure_dirs(root: Path = ROOT) -> None:
    for rel in (SYSTEM_DIR, LOGS_DIR, KAKAO_INPUT_DIR, TASKS_DIR, MEMOS_DIR, HOLD_DIR):
        (root / rel).mkdir(parents=True, exist_ok=True)


def init_db(root: Path = ROOT) -> None:
    ensure_dirs(root)
    with sqlite3.connect(root / SYSTEM_DIR / EVENTS_DB_NAME) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kakao_self_events (
                id TEXT PRIMARY KEY,
                store_key TEXT NOT NULL,
                msg_id TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                text TEXT NOT NULL,
                redacted_text TEXT NOT NULL,
                ts INTEGER NOT NULL,
                route TEXT NOT NULL,
                action_needed INTEGER NOT NULL,
                artifact_path TEXT,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_kakao_self_events_ts ON kakao_self_events(ts)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_kakao_self_events_route ON kakao_self_events(route)"
        )


def default_kakao_cli(root: Path = ROOT) -> Path:
    return root.parent / "kakao-windows-cli" / ".venv" / "Scripts" / "kakao-windows-cli.exe"


def default_rooms_file() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "kakao-windows-cli" / "reader-workspace" / "rooms.json"
    return Path.home() / ".kakao-windows-cli" / "reader-workspace" / "rooms.json"


def load_room_ids(path: Path) -> list[str]:
    if not path.is_file():
        return [DEFAULT_CHAT_ID]
    data = json.loads(path.read_text(encoding="utf-8"))
    rooms = data.get("rooms", {}) if isinstance(data, dict) else {}
    if not isinstance(rooms, dict):
        return [DEFAULT_CHAT_ID]
    room_ids = [str(room_id) for room_id in rooms.keys()]
    return room_ids or [DEFAULT_CHAT_ID]


def load_state(root: Path = ROOT) -> dict[str, Any]:
    path = root / SYSTEM_DIR / STATE_NAME
    if not path.is_file():
        legacy_path = root / LEGACY_SYSTEM_DIR / STATE_NAME
        if legacy_path.is_file():
            state = json.loads(legacy_path.read_text(encoding="utf-8"))
            state["migrated_from"] = str(legacy_path.relative_to(root))
            return state
        return {
            "version": 1,
            "chat_id": DEFAULT_CHAT_ID,
            "last_processed_ts": 0,
            "processed_store_keys": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any], root: Path = ROOT) -> None:
    ensure_dirs(root)
    keys = list(dict.fromkeys(str(k) for k in state.get("processed_store_keys", [])))
    state = dict(state)
    state["processed_store_keys"] = keys[-500:]
    state["updated_at"] = now_iso()
    (root / SYSTEM_DIR / STATE_NAME).write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def classify_text(text: str) -> dict[str, Any]:
    normalized = " ".join((text or "").split())
    lower = normalized.lower()
    if normalized in HOLD_TEXTS or len(normalized) <= 2:
        return {
            "route": "hold",
            "label": "보류",
            "action_needed": False,
            "confidence": 0.55,
            "reason": "too_short_or_ambiguous",
        }
    if any(keyword.lower() in lower for keyword in TASK_KEYWORDS):
        return {
            "route": "task",
            "label": "TASK",
            "action_needed": True,
            "confidence": 0.82,
            "reason": "task_keyword",
        }
    return {
        "route": "memo",
        "label": "메모",
        "action_needed": False,
        "confidence": 0.72,
        "reason": "capture_for_reference",
    }


def redact_text(text: str) -> str:
    redacted = PHONE_RE.sub("[전화번호]", text or "")
    if "인증" in redacted or "OTP" in redacted.upper():
        redacted = OTP_RE.sub("[인증번호]", redacted)
    return redacted


def normalize_message(message: dict[str, Any]) -> dict[str, Any]:
    text = str(message.get("text") or message.get("message") or "")
    return {
        "store_key": str(message.get("store_key") or message.get("msg_id") or message.get("id") or ""),
        "msg_id": str(message.get("msg_id") or message.get("id") or ""),
        "chat_id": str(message.get("room_id") or message.get("chat_id") or DEFAULT_CHAT_ID),
        "room_title": str(message.get("room_title") or message.get("chat_title") or ""),
            "sender": str(message.get("sender") or message.get("author") or "unknown"),
        "text": text,
        "redacted_text": redact_text(text),
        "ts": int(message.get("ts") or message.get("sendAt") or 0),
        "type": int(message.get("type") or 0),
    }


def event_id(message: dict[str, Any]) -> str:
    key = message["store_key"] or "|".join(
        [message["chat_id"], message["msg_id"], str(message["ts"]), message["text"]]
    )
    import hashlib

    return "kakao_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


def artifact_prefix(chat_id: str) -> str:
    if chat_id == DEFAULT_CHAT_ID:
        return "kakao-self"
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", chat_id).strip("-").lower()
    return cleaned or "kakao-room"


def source_label(chat_id: str, room_title: str = "") -> str:
    if chat_id == DEFAULT_CHAT_ID:
        return "카카오 나에게 보내기"
    if room_title:
        return f"카카오 대화방 {room_title}"
    return f"카카오 대화방 {chat_id}"


def input_markdown(event: dict[str, Any]) -> tuple[str, str]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    prefix = artifact_prefix(event["chat_id"])
    label = source_label(event["chat_id"], event.get("room_title", ""))
    input_id = f"input-{prefix}-{stamp}-{event['id'][-6:]}"
    content = f"""---
id: {input_id}
kms_layer: input
source_channel: kakao
source_chat_id: {event['chat_id']}
source_room_title: {event.get('room_title', '')}
source_sender: {event['sender']}
source_event_id: {event['id']}
source_store_key: {event['store_key']}
route_candidate: {event['route']}
action_needed: {str(event['action_needed']).lower()}
created_at: {now_iso()}
---

# {label} 입력

## 원문

{event['redacted_text']}

## KMS 판정 초안

- 분류 후보: {event['label']}
- confidence: {event['confidence']}
- reason: {event['reason']}
- 수신 시각(ms): {event['ts']}
"""
    return input_id, content


def task_markdown(event: dict[str, Any]) -> tuple[str, str]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    prefix = artifact_prefix(event["chat_id"])
    label = source_label(event["chat_id"], event.get("room_title", ""))
    task_id = f"task-{prefix}-{stamp}-{event['id'][-6:]}"
    title = f"{label}: {event['redacted_text'][:42]}"
    content = f"""---
id: {task_id}
kms_layer: processed
kms_type: task
status: open
priority: medium
origin: kms
source_channel: kakao
source_chat_id: {event['chat_id']}
source_input_path: {event.get('input_path', '')}
created_at: {now_iso()}
source_event_id: {event['id']}
source_store_key: {event['store_key']}
---

# {title}

## 다음 행동

- 카카오톡 메시지를 확인하고 필요한 작업으로 정리한다.

## 원문 요약

- 입력: {label}
- chat_id: {event['chat_id']}
- 수신 시각(ms): {event['ts']}
- 보낸 사람: {event['sender']}
- 내용: {event['redacted_text']}

## 로컬 원장

- Kakao Event ID: `{event['id']}`
- 입력 파일: `{event.get('input_path', '')}`
- DB: `workspace/kms/ledger/kakao/{EVENTS_DB_NAME}`
"""
    return task_id, content


def memo_markdown(event: dict[str, Any]) -> tuple[str, str]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    prefix = artifact_prefix(event["chat_id"])
    label = source_label(event["chat_id"], event.get("room_title", ""))
    memo_id = f"{prefix}-{stamp}-{event['id'][-6:]}"
    content = f"""---
id: {memo_id}
kms_layer: processed
kms_type: memo
origin: kms
source_channel: kakao
source_chat_id: {event['chat_id']}
source_input_path: {event.get('input_path', '')}
status: captured
created_at: {now_iso()}
source_event_id: {event['id']}
source_store_key: {event['store_key']}
---

# {label} 메모

{event['redacted_text']}

## 로컬 원장

- Kakao Event ID: `{event['id']}`
- 입력 파일: `{event.get('input_path', '')}`
- DB: `workspace/kms/ledger/kakao/{EVENTS_DB_NAME}`
"""
    return memo_id, content


def hold_markdown(event: dict[str, Any]) -> tuple[str, str]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    prefix = artifact_prefix(event["chat_id"])
    label = source_label(event["chat_id"], event.get("room_title", ""))
    hold_id = f"{prefix}-{stamp}-{event['id'][-6:]}"
    content = f"""---
id: {hold_id}
kms_layer: processed
kms_type: hold
origin: kms
source_channel: kakao
source_chat_id: {event['chat_id']}
source_input_path: {event.get('input_path', '')}
status: hold
created_at: {now_iso()}
source_event_id: {event['id']}
source_store_key: {event['store_key']}
---

# {label} 보류

{event['redacted_text']}

## 보류 이유

- 짧거나 의미가 불명확해서 TASK나 메모로 확정하지 않았다.
"""
    return hold_id, content


def write_input_artifact(event: dict[str, Any], root: Path = ROOT) -> str:
    artifact_id, content = input_markdown(event)
    path = root / KAKAO_INPUT_DIR / f"{artifact_id}.md"
    path.write_text(content, encoding="utf-8")
    return str(path.relative_to(root))


def write_artifact(event: dict[str, Any], root: Path = ROOT) -> str:
    if event["route"] == "task":
        artifact_id, content = task_markdown(event)
        path = root / TASKS_DIR / f"{artifact_id}.md"
    elif event["route"] == "memo":
        artifact_id, content = memo_markdown(event)
        path = root / MEMOS_DIR / f"{artifact_id}.md"
    else:
        artifact_id, content = hold_markdown(event)
        path = root / HOLD_DIR / f"{artifact_id}.md"
    path.write_text(content, encoding="utf-8")
    return str(path.relative_to(root))


def persist_event(event: dict[str, Any], root: Path = ROOT) -> None:
    init_db(root)
    with sqlite3.connect(root / SYSTEM_DIR / EVENTS_DB_NAME) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO kakao_self_events (
                id, store_key, msg_id, chat_id, sender, text, redacted_text, ts,
                route, action_needed, artifact_path, created_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["id"],
                event["store_key"],
                event["msg_id"],
                event["chat_id"],
                event["sender"],
                event["text"],
                event["redacted_text"],
                event["ts"],
                event["route"],
                1 if event["action_needed"] else 0,
                event["artifact_path"],
                event["created_at"],
                json.dumps(event["payload"], ensure_ascii=False),
            ),
        )
    with (root / SYSTEM_DIR / EVENTS_JSONL_NAME).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def ingest_messages(
    messages: list[dict[str, Any]],
    *,
    root: Path = ROOT,
    dry_run: bool = False,
    since_ts: int | None = None,
) -> dict[str, Any]:
    ensure_dirs(root)
    init_db(root)
    state = load_state(root)
    processed_keys = set(str(k) for k in state.get("processed_store_keys", []))
    last_ts = int(since_ts if since_ts is not None else state.get("last_processed_ts") or 0)
    state_by_chat = state.get("last_processed_ts_by_chat", {})
    if since_ts is not None:
        last_ts_by_chat = {}
    else:
        last_ts_by_chat = {
            str(chat_id): int(ts or 0)
            for chat_id, ts in state_by_chat.items()
        } if isinstance(state_by_chat, dict) else {}
    created = {"task": 0, "memo": 0, "hold": 0}
    processed = 0
    skipped = 0
    max_ts = last_ts
    max_ts_by_chat = dict(last_ts_by_chat)
    new_keys = list(processed_keys)
    events: list[dict[str, Any]] = []

    for raw in messages:
        message = normalize_message(raw)
        key = message["store_key"]
        message_last_ts = int(last_ts_by_chat.get(message["chat_id"], last_ts) or 0)
        if key in processed_keys:
            skipped += 1
            continue
        if message["ts"] < message_last_ts:
            skipped += 1
            continue
        route = classify_text(message["text"])
        event = {
            **message,
            **route,
            "id": event_id(message),
            "created_at": now_iso(),
            "payload": raw,
        }
        if dry_run:
            event["input_path"] = ""
            event["artifact_path"] = ""
        else:
            event["input_path"] = write_input_artifact(event, root)
            event["artifact_path"] = write_artifact(event, root)
        if not dry_run:
            persist_event(event, root)
        created[event["route"]] += 1
        processed += 1
        max_ts = max(max_ts, int(event["ts"]))
        max_ts_by_chat[event["chat_id"]] = max(
            int(max_ts_by_chat.get(event["chat_id"], 0) or 0),
            int(event["ts"]),
        )
        new_keys.append(key)
        events.append(event)

    if not dry_run:
        state.update(
            {
                "version": 1,
                "chat_id": "*",
                "last_processed_ts": max_ts,
                "last_processed_ts_by_chat": max_ts_by_chat,
                "processed_store_keys": new_keys,
                "last_run": {
                    "at": now_iso(),
                    "processed": processed,
                    "skipped": skipped,
                    "created": created,
                },
            }
        )
        save_state(state, root)

    return {
        "processed": processed,
        "skipped": skipped,
        "created": created,
        "last_processed_ts": max_ts,
        "events": events,
    }


def run_command(command: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout, proc.stderr


def pull_kakao(cli: Path, chat_id: str | None = None, since_ts: int | None = None) -> dict[str, Any]:
    command = [str(cli), "pull", "--json"]
    if chat_id:
        command.extend(["--chat-id", chat_id])
    if since_ts is not None:
        command.extend(["--since-ts", str(since_ts)])
    code, stdout, stderr = run_command(command)
    if code != 0:
        raise RuntimeError(stderr.strip() or stdout.strip() or "kakao pull failed")
    return json.loads(stdout)


def fetch_kakao_messages(cli: Path, user_id: str, chat_id: str, since_ts: int) -> list[dict[str, Any]]:
    command = [
        str(cli),
        "messages",
        "--user-id",
        user_id,
        "--chat-id",
        chat_id,
        "--since-ts",
        str(since_ts),
        "--json",
    ]
    code, stdout, stderr = run_command(command)
    if code != 0:
        raise RuntimeError(stderr.strip() or stdout.strip() or "kakao messages failed")
    return json.loads(stdout)


def list_prepared_chat_ids(cli: Path, user_id: str) -> list[str]:
    command = [str(cli), "prepared-chats", "--user-id", user_id, "--json"]
    code, stdout, stderr = run_command(command)
    if code != 0:
        raise RuntimeError(stderr.strip() or stdout.strip() or "kakao prepared-chats failed")
    data = json.loads(stdout)
    if not isinstance(data, list):
        return []
    return [str(item["chat_id"]) for item in data if isinstance(item, dict) and item.get("chat_id")]


def main() -> int:
    force_utf8_stdio()
    parser = argparse.ArgumentParser(description="Route KakaoTalk messages into KMS local artifacts.")
    parser.add_argument("--kakao-cli", default=str(default_kakao_cli()))
    parser.add_argument("--user-id", default=DEFAULT_USER_ID)
    parser.add_argument("--chat-id", help="single chat id to process; omit to process all registered rooms")
    parser.add_argument("--rooms-file", default=str(default_rooms_file()))
    parser.add_argument("--since-ts", type=int)
    parser.add_argument("--no-pull", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--init-db", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.init_db:
        init_db(ROOT)
        print(f"initialized {ROOT / SYSTEM_DIR / EVENTS_DB_NAME}")
        return 0

    cli = Path(args.kakao_cli)
    if not cli.is_file():
        raise SystemExit(f"kakao cli not found: {cli}")

    state = load_state(ROOT)
    global_since_ts = int(state.get("last_processed_ts") or 0)
    state_by_chat = state.get("last_processed_ts_by_chat", {})
    last_ts_by_chat = {
        str(chat_id): int(ts or 0)
        for chat_id, ts in state_by_chat.items()
    } if isinstance(state_by_chat, dict) else {}
    pull_result: dict[str, Any] | None = None
    if not args.no_pull:
        pull_since_ts = args.since_ts
        if pull_since_ts is None and not args.chat_id:
            pull_since_ts = 0
        pull_result = pull_kakao(cli, args.chat_id, since_ts=pull_since_ts)

    if args.chat_id:
        chat_ids = [args.chat_id]
    else:
        chat_ids = list_prepared_chat_ids(cli, args.user_id) or load_room_ids(Path(args.rooms_file))

    messages: list[dict[str, Any]] = []
    configured_chat_ids = set(load_room_ids(Path(args.rooms_file)))
    for chat_id in chat_ids:
        fallback_since_ts = global_since_ts if chat_id in configured_chat_ids else 0
        since_ts = (
            args.since_ts
            if args.since_ts is not None
            else int(last_ts_by_chat.get(chat_id, fallback_since_ts) or 0)
        )
        messages.extend(fetch_kakao_messages(cli, args.user_id, chat_id, since_ts))
    result = ingest_messages(messages, root=ROOT, dry_run=args.dry_run, since_ts=args.since_ts)
    output = {
        "source": args.chat_id or "kakao-all",
        "chat_ids": chat_ids,
        "pulled": pull_result,
        "kms_paths": {
            "inputs": str(KAKAO_INPUT_DIR),
            "processed_tasks": str(TASKS_DIR),
            "processed_memos": str(MEMOS_DIR),
            "processed_hold": str(HOLD_DIR),
            "ledger": str(SYSTEM_DIR),
        },
        **result,
    }
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(
            "kakao routed "
            f"{result['processed']} messages "
            f"(task={result['created']['task']}, memo={result['created']['memo']}, "
            f"hold={result['created']['hold']}, skipped={result['skipped']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
