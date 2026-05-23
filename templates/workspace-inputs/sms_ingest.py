from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LEGACY_SMS_DIR = ROOT / "workspace" / "system" / "sms"
LOCAL_WORKSPACE_DIR = ROOT
SMS_INPUT_DIR = LOCAL_WORKSPACE_DIR / "inputs" / "sms"
WORKSPACE_PROCESSED_DIR = LOCAL_WORKSPACE_DIR / "processed"
TASKS_DIR = WORKSPACE_PROCESSED_DIR / "tasks"
FINANCE_DIR = WORKSPACE_PROCESSED_DIR / "finance"
MEMOS_DIR = WORKSPACE_PROCESSED_DIR / "memos"
QUESTIONS_DIR = WORKSPACE_PROCESSED_DIR / "questions"
NOISE_DIR = WORKSPACE_PROCESSED_DIR / "noise"
SMS_DIR = LOCAL_WORKSPACE_DIR / "ledger" / "sms"
RULES_PATH = SMS_DIR / "classification-rules.json"
LEGACY_RULES_PATH = LEGACY_SMS_DIR / "classification-rules.json"
DB_PATH = SMS_DIR / "sms-events.sqlite"
JSONL_PATH = SMS_DIR / "sms-events.jsonl"

DEFAULT_RULES: dict[str, Any] = {
    "version": 1,
    "privacy": {
        "local_raw_text": True,
    },
    "task_triggers": {
        "must_task_keywords": [
            "문의",
            "가능할까요",
            "확인 부탁",
            "답변",
            "연락",
            "미팅",
            "회의",
            "예약",
            "처리",
            "요청",
        ],
        "never_task_keywords": [
            "광고",
            "수신거부",
            "인증번호",
            "인증 코드",
            "OTP",
        ],
    },
    "lanes": {
        "card_usage": {
            "label": "카드 사용",
            "keywords": ["카드", "승인", "사용", "일시불", "체크", "결제"],
            "amount_required": True,
            "task_default": False,
        },
        "deposit": {
            "label": "입금",
            "keywords": ["입금", "받았습니다", "이체입금", "입금완료"],
            "amount_required": True,
            "task_default": False,
        },
        "withdrawal": {
            "label": "출금",
            "keywords": ["출금", "이체", "송금", "자동이체", "결제완료"],
            "amount_required": True,
            "task_default": False,
        },
        "inquiry": {
            "label": "문의",
            "keywords": ["문의", "가능할까요", "언제", "미팅", "회의", "연락", "답변"],
            "amount_required": False,
            "task_default": True,
        },
        "verification": {
            "label": "인증",
            "keywords": ["인증", "인증번호", "OTP", "보안코드", "verification"],
            "amount_required": False,
            "task_default": False,
        },
        "notification": {
            "label": "알림",
            "keywords": ["알림", "안내", "공지", "완료", "배송", "도착"],
            "amount_required": False,
            "task_default": False,
        },
    },
}


AMOUNT_RE = re.compile(r"(?P<amount>\d{1,3}(?:,\d{3})+|\d+)\s*(?:원|KRW)", re.IGNORECASE)
ANY_AMOUNT_RE = re.compile(
    r"(?:(?:KRW|USD)\s*)?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\s*\(?\s*(?:원|KRW|USD|달러)\s*\)?",
    re.IGNORECASE,
)
OTP_RE = re.compile(r"(?<!\d)(\d{4,8})(?!\d)")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?82[-\s]?)?0?1[016789][-\s]?\d{3,4}[-\s]?\d{4}(?!\d)")
ACCOUNT_RE = re.compile(r"(?<!\d)\d{2,6}[-\s]\d{2,6}[-\s]\d{2,8}(?!\d)")
PLACEHOLDER_TEXTS = {
    "",
    "%SMSRB",
    "%SMSRF",
    "%SMSRN",
    "%SMSRD",
    "%SMSRT",
    "%MMSRS",
    "%evtprm1",
    "%evtprm2",
    "%evtprm3",
    "%evtprm4",
    "%evtprm5",
    "%NTITLE",
    "%NAPP",
    "%NPKG",
    "%NTEXT",
    "%evtprm()",
    "[제목없음]",
    "[제목 없음]",
}


def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def normalize_received_at(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return now_iso()

    # Tasker %TIME uses a dot separator, for example "23.04".
    return re.sub(r"(^|\s)([01]?\d|2[0-3])\.(\d{2})(?=\s|$)", r"\1\2:\3", text)


def load_rules() -> dict[str, Any]:
    path = RULES_PATH if RULES_PATH.is_file() else LEGACY_RULES_PATH
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return DEFAULT_RULES


def ensure_dirs() -> None:
    for path in (SMS_DIR, SMS_INPUT_DIR, TASKS_DIR, FINANCE_DIR, MEMOS_DIR, QUESTIONS_DIR, NOISE_DIR):
        path.mkdir(parents=True, exist_ok=True)
    migrate_legacy_sms_files()


def migrate_legacy_sms_files() -> None:
    for name in ("classification-rules.json", "sample-payloads.jsonl", "sms-events.sqlite", "sms-events.jsonl"):
        source = LEGACY_SMS_DIR / name
        target = SMS_DIR / name
        if source.is_file() and not target.exists():
            shutil.copy2(source, target)


def init_db(path: Path | None = None) -> None:
    ensure_dirs()
    path = path or DB_PATH
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sms_events (
                id TEXT PRIMARY KEY,
                received_at TEXT NOT NULL,
                source TEXT NOT NULL,
                sender_hash TEXT NOT NULL,
                sender_label TEXT,
                category TEXT NOT NULL,
                direction TEXT NOT NULL,
                amount INTEGER,
                merchant TEXT,
                redacted_text TEXT NOT NULL,
                raw_text TEXT,
                action_needed INTEGER NOT NULL,
                task_id TEXT,
                privacy_level TEXT NOT NULL,
                confidence REAL NOT NULL,
                created_at TEXT NOT NULL,
                input_path TEXT,
                artifact_path TEXT,
                payload_json TEXT NOT NULL
            )
            """
        )
        existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(sms_events)").fetchall()}
        if "input_path" not in existing_columns:
            conn.execute("ALTER TABLE sms_events ADD COLUMN input_path TEXT")
        if "artifact_path" not in existing_columns:
            conn.execute("ALTER TABLE sms_events ADD COLUMN artifact_path TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sms_events_received_at ON sms_events(received_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sms_events_category ON sms_events(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sms_events_action_needed ON sms_events(action_needed)")


def sender_hash(sender: str) -> str:
    normalized = (sender or "").strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def clean_sender(value: Any) -> str:
    text = clean_text(value)
    return re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]", "", text).strip()


def sender_label(sender: str) -> str:
    cleaned = clean_sender(sender)
    if not cleaned:
        return ""
    if re.fullmatch(r"[\d+\-\s().]+", cleaned):
        return cleaned[:4] + "..."
    return cleaned[:40]


def redact_text(text: str, category: str) -> str:
    redacted = PHONE_RE.sub("[전화번호]", text)
    redacted = ACCOUNT_RE.sub("[계좌번호]", redacted)
    if category == "verification" or "인증" in text or "OTP" in text.upper():
        redacted = OTP_RE.sub("[인증번호]", redacted)
        redacted = redacted.replace("[[인증번호]]", "[인증번호]")
    return redacted


def extract_amount(text: str) -> int | None:
    match = AMOUNT_RE.search(text)
    if not match:
        return None
    return int(match.group("amount").replace(",", ""))


def has_amount_signal(text: str) -> bool:
    if AMOUNT_RE.search(text):
        return True
    for match in ANY_AMOUNT_RE.finditer(text):
        value = match.group(0).strip()
        if any(token in value.upper() for token in ("원", "KRW", "USD", "달러")):
            return True
    return False


def repair_mojibake(text: str) -> str:
    if not text:
        return ""
    if any(marker in text for marker in ("ì", "ë", "í", "ê")):
        try:
            return text.encode("latin1").decode("utf-8")
        except UnicodeError:
            return text
    return text


def clean_text(value: Any) -> str:
    return repair_mojibake(str(value or "").strip())


def is_placeholder(value: Any) -> bool:
    text = clean_text(value)
    return (
        text in PLACEHOLDER_TEXTS
        or text.startswith("%evtprm")
        or text.startswith("%SMS")
        or text.startswith("%MMS")
        or text.startswith("%N")
    )


def first_real_text(*values: Any) -> str:
    for value in values:
        text = clean_text(value)
        if text and not is_placeholder(text):
            return text
    return ""


def looks_like_package_name(text: str) -> bool:
    return bool(re.fullmatch(r"[a-zA-Z][\w]*(?:\.[\w]+)+", text or ""))


def message_body(payload: dict[str, Any]) -> str:
    notification_text = first_real_text(
        payload.get("notification_text"),
        payload.get("notification_big_text"),
        payload.get("notification_subtext"),
    )
    notification_title = first_real_text(payload.get("notification_title"))
    if notification_title and notification_text and notification_text != notification_title:
        notification_body = "\n".join((notification_title, notification_text))
    else:
        notification_body = first_real_text(notification_title, notification_text, payload.get("notification_messages"))
    sms_type = clean_text(payload.get("sms_type")).upper()
    if sms_type == "MMS":
        return first_real_text(
            payload.get("mms_body"),
            payload.get("legacy_body"),
            payload.get("sms_body"),
            payload.get("body"),
            payload.get("text"),
            notification_body,
            payload.get("mms_subject"),
            payload.get("legacy_mms_subject"),
        )
    return first_real_text(
        payload.get("body"),
        payload.get("text"),
        notification_body,
        payload.get("sms_body"),
        payload.get("legacy_body"),
        payload.get("mms_body"),
        payload.get("mms_subject"),
        payload.get("legacy_mms_subject"),
    )


def extract_merchant(text: str, amount: int | None) -> str:
    if not amount:
        return ""
    amount_text = f"{amount:,}"
    compact = text.replace("원", " 원")
    after = compact.split(amount_text, 1)
    if len(after) == 2:
        candidate = after[1].strip(" .,/[]")
        candidate = re.sub(r"^(원|KRW)\s*", "", candidate, flags=re.IGNORECASE).strip(" .,/[]")
        lines = [line.strip(" .,/[]") for line in candidate.splitlines() if line.strip(" .,/[]")]
        for line in lines:
            normalized_line = line.strip(" .,/[]()")
            if re.search(r"^(고객명|승인시각|누적|잔액|카드|체크|일시불|할부)$", normalized_line):
                continue
            line = re.sub(r"^\(?\s*(일시불|할부|승인|사용|결제|출금|입금)\s*\)?\s*", "", line).strip(" .,/[]")
            if not line or re.search(r"^(고객명|승인시각|누적|잔액|카드|체크|일시불|할부)", line):
                continue
            line = re.sub(r"(승인시각|승인|사용|결제|출금|입금|잔액|누적|일시불|체크|카드).*", "", line).strip()
            if line:
                return line[:40]
    return ""


def classify(payload: dict[str, Any], rules: dict[str, Any] | None = None) -> dict[str, Any]:
    rules = rules or load_rules()
    body = message_body(payload)
    received_at = normalize_received_at(payload.get("received_at"))
    sender = first_real_text(
        payload.get("notification_sender"),
        payload.get("notification_conversation"),
        payload.get("contact"),
        payload.get("sender"),
        payload.get("legacy_sender"),
        payload.get("sender_name"),
        payload.get("legacy_sender_name"),
        payload.get("package"),
        payload.get("app_name"),
    )
    if looks_like_package_name(sender):
        sender = ""
    sender = clean_sender(sender)
    amount = extract_amount(body)
    amount_signal = has_amount_signal(body)

    best_key = "notification"
    best_score = 0
    for key, lane in rules["lanes"].items():
        score = 0
        for keyword in lane.get("keywords", []):
            if keyword.lower() in body.lower() or keyword.lower() in sender.lower():
                score += 1
        if lane.get("amount_required") and not amount_signal:
            score = 0
        if score > best_score:
            best_key = key
            best_score = score

    if best_score == 0:
        best_key = "notification"

    task_triggers = rules.get("task_triggers", {})
    must_task = any(k.lower() in body.lower() for k in task_triggers.get("must_task_keywords", []))
    never_task = any(k.lower() in body.lower() for k in task_triggers.get("never_task_keywords", []))
    lane = rules["lanes"][best_key]
    action_needed = bool((lane.get("task_default") or must_task) and not never_task)

    if best_key == "deposit":
        direction = "income"
    elif best_key in ("withdrawal", "card_usage"):
        direction = "expense"
    else:
        direction = "neutral"

    privacy_level = "safe"
    if best_key in ("card_usage", "deposit", "withdrawal"):
        privacy_level = "financial"
    if best_key == "verification":
        privacy_level = "secret"

    redacted = redact_text(body, best_key)
    event_id_base = "|".join(
        [
            received_at,
            sender,
            body,
        ]
    )
    event_id = "sms_" + hashlib.sha256(event_id_base.encode("utf-8")).hexdigest()[:20]
    confidence = min(0.95, 0.45 + (best_score * 0.2))

    return {
        "id": event_id,
        "received_at": received_at,
        "source": str(payload.get("source") or "manual"),
        "sender_hash": sender_hash(sender),
        "sender_label": sender_label(sender),
        "sender_display": sender,
        "category": lane["label"],
        "category_key": best_key,
        "direction": direction,
        "amount": amount,
        "merchant": extract_merchant(body, amount),
        "redacted_text": redacted,
        "raw_text": body if rules.get("privacy", {}).get("local_raw_text", True) else "",
        "action_needed": action_needed,
        "privacy_level": privacy_level,
        "confidence": round(confidence, 2),
        "created_at": now_iso(),
        "payload": payload,
    }


def task_markdown(event: dict[str, Any]) -> tuple[str, str]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    task_id = f"task-sms-{stamp}-{event['id'][-6:]}"
    title = f"문자 문의 확인: {event['redacted_text'][:42]}"
    content = f"""---
id: {task_id}
workspace_layer: processed
workspace_type: task
status: open
priority: medium
origin: local-workspace
source_channel: sms
source_input_path: {event.get('input_path', '')}
created_at: {now_iso()}
source_event_id: {event['id']}
---

# {title}

## 다음 행동

- 문자 내용을 확인하고 필요한 답변 또는 처리를 진행한다.

## 문자 요약

- 분류: {event['category']}
- 수신 시각: {event['received_at']}
- 발신자: {event['sender_label']}
- 내용: {event['redacted_text']}

## 로컬 원장

- SMS Event ID: `{event['id']}`
- 입력 파일: `{event.get('input_path', '')}`
- DB: `ledger/sms/sms-events.sqlite`
"""
    return task_id, content


def input_markdown(event: dict[str, Any]) -> tuple[str, str]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    input_id = f"input-sms-{stamp}-{event['id'][-6:]}"
    content = f"""---
id: {input_id}
workspace_layer: input
source_channel: sms
source: {event['source']}
received_at: {event['received_at']}
sender_label: {event['sender_label']}
category_candidate: {event['category']}
privacy_level: {event['privacy_level']}
action_needed: {str(event['action_needed']).lower()}
created_at: {now_iso()}
source_event_id: {event['id']}
---

# SMS 입력

## 원문

{event['redacted_text']}

## Local workspace 판정 초안

- 분류 후보: {event['category']}
- category_key: {event['category_key']}
- direction: {event['direction']}
- amount: {event['amount'] or ''}
- merchant: {event['merchant']}
- confidence: {event['confidence']}
"""
    return input_id, content


def processed_markdown(event: dict[str, Any], artifact_id: str, workspace_type: str) -> str:
    title = f"{event['category']} SMS: {event['redacted_text'][:48]}"
    return f"""---
id: {artifact_id}
workspace_layer: processed
workspace_type: {workspace_type}
origin: local-workspace
source_channel: sms
source_input_path: {event.get('input_path', '')}
status: captured
created_at: {now_iso()}
source_event_id: {event['id']}
privacy_level: {event['privacy_level']}
---

# {title}

## 요약

- 분류: {event['category']}
- 수신 시각: {event['received_at']}
- 발신자: {event['sender_label']}
- 방향: {event['direction']}
- 금액: {event['amount'] or ''}
- 사용처/상대: {event['merchant']}
- 내용: {event['redacted_text']}

## 로컬 원장

- 입력 파일: `{event.get('input_path', '')}`
- SMS Event ID: `{event['id']}`
- DB: `ledger/sms/sms-events.sqlite`
"""


def processed_dir_for_event(event: dict[str, Any]) -> tuple[Path, str]:
    key = event["category_key"]
    if key in {"card_usage", "deposit", "withdrawal"}:
        return FINANCE_DIR, "finance"
    if key == "inquiry":
        return QUESTIONS_DIR, "question"
    if key in {"verification", "notification"}:
        return NOISE_DIR, "noise"
    return MEMOS_DIR, "memo"


def write_input(event: dict[str, Any]) -> str:
    input_id, content = input_markdown(event)
    path = SMS_INPUT_DIR / f"{input_id}.md"
    path.write_text(content, encoding="utf-8")
    return str(path.relative_to(ROOT))


def write_task(event: dict[str, Any]) -> str:
    task_id, content = task_markdown(event)
    path = TASKS_DIR / f"{task_id}.md"
    path.write_text(content, encoding="utf-8")
    return str(path.relative_to(ROOT))


def write_processed(event: dict[str, Any]) -> str:
    if event["action_needed"]:
        return write_task(event)
    target_dir, workspace_type = processed_dir_for_event(event)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    artifact_id = f"sms-{workspace_type}-{stamp}-{event['id'][-6:]}"
    path = target_dir / f"{artifact_id}.md"
    path.write_text(processed_markdown(event, artifact_id, workspace_type), encoding="utf-8")
    return str(path.relative_to(ROOT))


def persist_event(event: dict[str, Any], create_task: bool = True) -> dict[str, Any]:
    init_db()
    event = dict(event)
    event["input_path"] = write_input(event)
    task_path = ""
    task_id = ""
    artifact_path = ""
    if create_task:
        artifact_path = write_processed(event)
        if event["action_needed"]:
            task_path = artifact_path
            task_id = Path(task_path).stem

    event["task_id"] = task_id
    event["task_path"] = task_path
    event["artifact_path"] = artifact_path

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO sms_events (
                id, received_at, source, sender_hash, sender_label, category, direction,
                amount, merchant, redacted_text, raw_text, action_needed, task_id,
                privacy_level, confidence, created_at, input_path, artifact_path, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["id"],
                event["received_at"],
                event["source"],
                event["sender_hash"],
                event["sender_label"],
                event["category"],
                event["direction"],
                event["amount"],
                event["merchant"],
                event["redacted_text"],
                event["raw_text"],
                1 if event["action_needed"] else 0,
                event["task_id"],
                event["privacy_level"],
                event["confidence"],
                event["created_at"],
                event["input_path"],
                event["artifact_path"],
                json.dumps(event["payload"], ensure_ascii=False),
            ),
        )

    with JSONL_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def ingest_payload(payload: dict[str, Any], create_task: bool = True) -> dict[str, Any]:
    event = classify(payload)
    return persist_event(event, create_task=create_task)


def load_payloads(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.json:
        return [json.loads(args.json)]
    if args.file:
        path = Path(args.file)
        text = path.read_text(encoding="utf-8").strip()
        if path.suffix.lower() == ".jsonl":
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        return [json.loads(text)]
    if not sys.stdin.isatty():
        text = sys.stdin.read().strip()
        if text:
            if "\n" in text and not text.lstrip().startswith("{"):
                return [json.loads(line) for line in text.splitlines() if line.strip()]
            return [json.loads(text)]
    return []


def self_test() -> None:
    ensure_dirs()
    sample_path = SMS_DIR / "sample-payloads.jsonl"
    payloads = [json.loads(line) for line in sample_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    results = [classify(payload) for payload in payloads]
    categories = [result["category"] for result in results]
    assert "카드 사용" in categories
    assert "문의" in categories
    assert "인증" in categories
    assert "입금" in categories
    print(json.dumps(results, ensure_ascii=False, indent=2))


def main() -> int:
    force_utf8_stdio()
    parser = argparse.ArgumentParser(description="Ingest SMS payloads into the local workspace SMS ledger.")
    parser.add_argument("--json", help="Single JSON payload string.")
    parser.add_argument("--file", help="JSON or JSONL payload file.")
    parser.add_argument("--dry-run", action="store_true", help="Classify only; do not write DB/tasks.")
    parser.add_argument("--no-task", action="store_true", help="Do not create task markdown even when action is needed.")
    parser.add_argument("--init-db", action="store_true", help="Initialize local SQLite database.")
    parser.add_argument("--self-test", action="store_true", help="Run classifier self-test against sample payloads.")
    args = parser.parse_args()

    if args.init_db:
        init_db()
        print(f"initialized {DB_PATH}")
        return 0
    if args.self_test:
        self_test()
        return 0

    payloads = load_payloads(args)
    if not payloads:
        parser.error("provide --json, --file, or stdin JSON")

    output = []
    for payload in payloads:
        event = classify(payload)
        if not args.dry_run:
            event = persist_event(event, create_task=not args.no_task)
        output.append(event)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
