#!/usr/bin/env python3
"""
Slack agent router for Claude Code and Codex.

This is a local Windows-friendly variant built from the Agent Bootstrap idea:
one Slack app, one Socket Mode daemon, two CLI backends.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from slack_sdk import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

HOME = Path.home()
BASE_DIR = Path(os.environ.get("AGENT_ROUTER_HOME", str(HOME / ".agent-router-kit" / "slack-agent-router"))).expanduser()
SESSIONS_DIR = BASE_DIR / "sessions"
LOGS_DIR = BASE_DIR / "logs"
RUNS_DIR = BASE_DIR / "runs"
STATE_DIR = BASE_DIR / "state"
for directory in (SESSIONS_DIR, LOGS_DIR, RUNS_DIR, STATE_DIR):
    directory.mkdir(parents=True, exist_ok=True)

DEFAULT_ENV = HOME / ".agent-router-kit" / "secrets" / "slack-agent-router.env"
ENV_PATH = Path(os.environ.get("AGENT_ROUTER_ENV", str(DEFAULT_ENV)))


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        raise FileNotFoundError(f"env file not found: {path}")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        values[key.strip()] = value
    return values


ENV = os.environ.copy()
ENV.update(_read_env_file(ENV_PATH))


def env_required(name: str) -> str:
    value = ENV.get(name, "").strip()
    if not value:
        raise RuntimeError(f"required env missing: {name}")
    return value


SLACK_BOT_TOKEN = env_required("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = env_required("SLACK_APP_TOKEN")
SLACK_CHANNEL = env_required("SLACK_CHANNEL")
USER_SLACK_ID = ENV.get("USER_SLACK_ID", "").strip()
BOT_USER_ID = ENV.get("BOT_USER_ID", "").strip()
USER_NAME = ENV.get("USER_NAME", "사용자").strip() or "사용자"
BOT_NAME = ENV.get("SLACK_BOT_NAME", "Slack Agent Router").strip() or "Slack Agent Router"
DEFAULT_AGENT = (ENV.get("DEFAULT_AGENT", "claude").strip().lower() or "claude")
AGENT_WORKDIR = Path(ENV.get("AGENT_WORKDIR", str(HOME / "agent-router-workspace"))).expanduser()
PROJECT_ROOT = Path(ENV.get("PROJECT_ROOT", str(HOME / "agent-router-projects"))).expanduser()
WORKSPACE_ROOT = Path(ENV.get("WORKSPACE_ROOT", ENV.get("MANAGER_ROOT", str(HOME / "agent-router-workspace")))).expanduser()
MANAGER_ROOT = WORKSPACE_ROOT
MANAGER_SHARED_CONTEXT = MANAGER_ROOT / "workspace" / "system" / "slack" / "shared-context.md"
MANAGER_SLACK_SYNC = MANAGER_ROOT / "scripts" / "sync-slack-outbox.ps1"
KMS_ROOT = MANAGER_ROOT / "workspace" / "kms"
KMS_INPUTS_DIR = KMS_ROOT / "inputs"
KMS_PROCESSED_DIR = KMS_ROOT / "processed"
KMS_TASKS_DIR = KMS_PROCESSED_DIR / "tasks"
KMS_KAKAO_INPUTS_DIR = KMS_INPUTS_DIR / "kakao"
KMS_KAKAO_LEDGER_DIR = KMS_ROOT / "ledger" / "kakao"
LEGACY_TASKS_DIR = MANAGER_ROOT / "workspace" / "user" / "tasks"
CLAUDE_EXE = ENV.get("CLAUDE_EXE", "claude")
CLAUDE_MODEL = ENV.get("CLAUDE_MODEL", "").strip()
CODEX_EXE = ENV.get("CODEX_EXE", ENV.get("CODEX_PS1", "codex")).strip() or "codex"
POWERSHELL_EXE = ENV.get("POWERSHELL_EXE", "pwsh")
AGENT_TIMEOUT_SEC = int(ENV.get("AGENT_TIMEOUT_SEC", "900"))
AGENT_DISPLAY = {
    "claude": "클로",
    "codex": "덱스",
}
DEBATE_STATE_TTL_SEC = int(ENV.get("DEBATE_STATE_TTL_SEC", str(12 * 60 * 60)))
DEBATE_MESSAGE_DELAY_SEC = float(ENV.get("DEBATE_MESSAGE_DELAY_SEC", "0.35"))

web = WebClient(token=SLACK_BOT_TOKEN)
if not BOT_USER_ID:
    try:
        BOT_USER_ID = str(web.auth_test().get("user_id", ""))
    except Exception:
        BOT_USER_ID = ""
sock = SocketModeClient(app_token=SLACK_APP_TOKEN, web_client=web)


def log(message: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {message}"
    print(line, flush=True)
    today = time.strftime("%Y-%m-%d")
    with (LOGS_DIR / f"{today}.log").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def agent_environment() -> dict[str, str]:
    """Return a child-process environment without Slack router secrets."""
    child_env = os.environ.copy()
    for key in (
        "SLACK_BOT_TOKEN",
        "SLACK_APP_TOKEN",
        "SLACK_CHANNEL",
        "USER_SLACK_ID",
        "BOT_USER_ID",
        "AGENT_ROUTER_ENV",
    ):
        child_env.pop(key, None)
    return child_env


def _safe_channel(channel: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", channel)


def session_path(agent: str, channel: str) -> Path:
    return SESSIONS_DIR / f"{agent}-{_safe_channel(channel)}.txt"


def get_session(agent: str, channel: str) -> str:
    path = session_path(agent, channel)
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = str(uuid.uuid4())
    path.write_text(value, encoding="utf-8")
    return value


def get_or_create_session(agent: str, channel: str) -> tuple[str, bool]:
    path = session_path(agent, channel)
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value, False
    value = str(uuid.uuid4())
    path.write_text(value, encoding="utf-8")
    return value, True


def set_session(agent: str, channel: str, session_id: str) -> None:
    session_path(agent, channel).write_text(session_id, encoding="utf-8")


def reset_session(agent: str, channel: str) -> str:
    value = str(uuid.uuid4())
    set_session(agent, channel, value)
    return value


def delete_session(agent: str, channel: str) -> None:
    try:
        session_path(agent, channel).unlink()
    except FileNotFoundError:
        pass


def state_path(kind: str, channel: str) -> Path:
    return STATE_DIR / f"{kind}-{_safe_channel(channel)}.json"


def _read_json(path: Path) -> dict[str, object]:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log(f"state read failed {path.name}: {exc}")
    return {}


def _write_json(path: Path, value: dict[str, object]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_debate_state(channel: str) -> dict[str, object]:
    return _read_json(state_path("debate", channel))


def save_debate_state(channel: str, state: dict[str, object]) -> None:
    state["updated_at"] = _local_iso_timestamp()
    state["updated_epoch"] = time.time()
    _write_json(state_path("debate", channel), state)


def clear_debate_state(channel: str) -> None:
    try:
        state_path("debate", channel).unlink()
    except FileNotFoundError:
        pass


def is_debate_state_active(state: dict[str, object]) -> bool:
    if not state or state.get("mode") != "debate":
        return False
    updated_epoch = state.get("updated_epoch")
    if not isinstance(updated_epoch, (int, float)):
        return True
    return (time.time() - updated_epoch) <= DEBATE_STATE_TTL_SEC


def load_recent_context(channel: str) -> dict[str, object]:
    return _read_json(state_path("recent", channel))


def _clip(value: str, limit: int = 5000) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...truncated"


def record_recent_exchange(
    channel: str,
    user_text: str,
    assistant_text: str,
    *,
    mode: str = "chat",
    topic: str = "",
) -> None:
    state = {
        "mode": mode,
        "topic": topic,
        "last_user_text": _clip(user_text, 2000),
        "last_assistant_text": _clip(assistant_text, 6000),
        "updated_at": _local_iso_timestamp(),
        "updated_epoch": time.time(),
    }
    _write_json(state_path("recent", channel), state)


SYSTEM_PROMPT = f"""You are a Slack-based coding assistant for {USER_NAME}.

Answer in Korean unless the user asks otherwise. Be concise in Slack.
Start from the configured Slack agent workspace.
Use project materials only when the user explicitly asks with "자료", "프로젝트", or the Korean context alias "업무".
"업무" means the user's main KMS workspace. "작업" means the light inbox/workspace context.
When answering 업무, 오늘 할 일, 할 일, 일정, or 참고 일정, use the KMS shared context first if it is provided.
When the router provides Debate Mode instructions, stay inside debate: do not inspect inbox/outbox or run file routing unless the user explicitly asks for file or folder handling.
When project materials are enabled, treat them as reference-only unless the user explicitly asks for edits.
Do not print secrets or tokens."""


def call_claude(prompt: str, channel: str, project_access: bool = False, timeout: int = AGENT_TIMEOUT_SEC) -> str:
    session_id, is_new = get_or_create_session("claude", channel)
    base_command = [
        CLAUDE_EXE,
        "--print",
        "--permission-mode",
        "bypassPermissions",
        "--dangerously-skip-permissions",
        "--output-format",
        "text",
        "--append-system-prompt",
        SYSTEM_PROMPT,
    ]
    base_command.extend(["--add-dir", str(AGENT_WORKDIR)])
    if project_access:
        base_command.extend(["--add-dir", str(PROJECT_ROOT)])
    if CLAUDE_MODEL:
        base_command.extend(["--model", CLAUDE_MODEL])
    command = base_command + (["--session-id", session_id] if is_new else ["--resume", session_id])

    run_env = agent_environment()
    run_env["CLAUDE_SKIP_HOOKS"] = "1"
    try:
        result = subprocess.run(
            command,
            input=prompt,
            capture_output=True,
            text=True,
            cwd=str(AGENT_WORKDIR),
            env=run_env,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return f"Timeout: Claude did not finish within {timeout} seconds."

    stderr = result.stderr or ""
    if result.returncode != 0 and not is_new and "No conversation found" in stderr:
        session_id = reset_session("claude", channel)
        command = base_command + ["--session-id", session_id]
        result = subprocess.run(
            command,
            input=prompt,
            capture_output=True,
            text=True,
            cwd=str(AGENT_WORKDIR),
            env=run_env,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )

    if result.returncode != 0:
        log(f"claude failed rc={result.returncode}: {stderr[-500:]}")
        return "Claude 실행 중 오류가 났습니다. 로그를 확인해 주세요."
    return (result.stdout or "").strip()


SESSION_RE = re.compile(r"session id:\s*([0-9a-fA-F-]{36})")


def _codex_base_command() -> list[str]:
    if CODEX_EXE.lower().endswith(".ps1"):
        return [
            POWERSHELL_EXE,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            CODEX_EXE,
        ]
    return [
        CODEX_EXE,
    ]


def _read_answer(path: Path, fallback: str) -> str:
    if path.exists():
        value = path.read_text(encoding="utf-8", errors="replace").strip()
        if value:
            return value
    return fallback.strip()


def call_codex(prompt: str, channel: str, project_access: bool = False, timeout: int = AGENT_TIMEOUT_SEC) -> str:
    existing_session = session_path("codex", channel)
    session_id = existing_session.read_text(encoding="utf-8").strip() if existing_session.exists() else ""
    answer_file = RUNS_DIR / f"codex-{_safe_channel(channel)}-{int(time.time())}.txt"

    if project_access:
        command = _codex_base_command() + [
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "-s",
            "read-only",
            "-C",
            str(AGENT_WORKDIR),
            "--add-dir",
            str(PROJECT_ROOT),
            "-o",
            str(answer_file),
            f"{prompt}\n\n프로젝트 자료 루트: {PROJECT_ROOT}\n자료는 기본적으로 읽기/참고용으로만 사용하세요.",
        ]
    elif session_id:
        command = _codex_base_command() + [
            "exec",
            "resume",
            "--skip-git-repo-check",
            "-o",
            str(answer_file),
            session_id,
            prompt,
        ]
    else:
        command = _codex_base_command() + [
            "exec",
            "--skip-git-repo-check",
            "-s",
            "workspace-write",
            "-C",
            str(AGENT_WORKDIR),
            "-o",
            str(answer_file),
            prompt,
        ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=str(AGENT_WORKDIR),
            env=agent_environment(),
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return f"Timeout: Codex did not finish within {timeout} seconds."

    stdout = result.stdout or ""
    stderr = result.stderr or ""
    match = SESSION_RE.search(stdout)
    if match:
        set_session("codex", channel, match.group(1))

    if result.returncode != 0 and session_id:
        log(f"codex resume failed; retrying fresh session rc={result.returncode}: {stderr[-500:]}")
        delete_session("codex", channel)
        return call_codex(prompt, channel, project_access, timeout)

    if result.returncode != 0:
        log(f"codex failed rc={result.returncode}: {stderr[-500:]}")
        return "Codex 실행 중 오류가 났습니다. 로그를 확인해 주세요."
    return _read_answer(answer_file, stdout)


def strip_project_prefix(text: str) -> tuple[bool, str]:
    stripped = text.strip()
    lowered = stripped.lower()
    prefixes = (
        "자료 호출 ",
        "자료 호출:",
        "자료 ",
        "자료:",
        "프로젝트 자료 ",
        "프로젝트 자료:",
        "프로젝트 호출 ",
        "프로젝트 호출:",
        "프로젝트 ",
        "프로젝트:",
    )
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return True, stripped[len(prefix) :].strip()
    return False, stripped


CONTEXTS = {
    "project": {
        "label": "자료",
        "path": PROJECT_ROOT,
        "project_access": True,
        "note": "넓은 프로젝트 자료 호출입니다. 필요한 자료만 읽고, 기본은 참고용으로 다루세요.",
    },
    "work": {
        "label": "업무",
        "path": MANAGER_ROOT,
        "project_access": True,
        "note": "깊은 업무/KMS workspace 기준입니다. 일정, 콘텐츠, 고민, 운영 판단은 이 폴더 맥락을 우선하세요.",
    },
    "light": {
        "label": "작업",
        "path": AGENT_WORKDIR,
        "project_access": False,
        "note": "가벼운 폴더 작업/인박스 기준입니다. 임시 자료 처리, 빠른 정리, 수집함 작업으로 다루세요.",
    },
}


def strip_named_context_prefix(text: str) -> tuple[dict[str, object] | None, str]:
    stripped = text.strip()
    lowered = stripped.lower()
    context_prefixes = (
        ("work", ("업무 ", "업무:", "work ", "work:", "깊은 업무 ", "깊은업무 ", "kms ", "kms:")),
        ("light", ("작업 ", "작업:", "가벼운 작업 ", "가벼운작업 ", "인박스 ", "인박스:", "수집함 ", "수집함:")),
    )
    for context_name, prefixes in context_prefixes:
        for prefix in prefixes:
            if lowered.startswith(prefix):
                return CONTEXTS[context_name], stripped[len(prefix) :].strip()
    return None, stripped


def consume_context_prefix(text: str) -> tuple[bool, str, dict[str, object] | None]:
    project_access, stripped = strip_project_prefix(text)
    context = CONTEXTS["project"] if project_access else None
    named_context, stripped = strip_named_context_prefix(stripped)
    if named_context:
        context = named_context
        project_access = bool(named_context["project_access"])
    return project_access, stripped, context


def apply_context_note(prompt: str, context: dict[str, object] | None) -> str:
    clean_prompt = prompt.strip() or "무엇을 도와드릴까요?"
    if not context:
        return clean_prompt
    return (
        f"{clean_prompt}\n\n"
        f"호출 컨텍스트: {context['label']}\n"
        f"기준 폴더: {context['path']}\n"
        f"처리 기준: {context['note']}"
    )


def _strip_optional_agent_prefix(text: str) -> str:
    stripped = text.strip()
    lowered = stripped.lower()
    prefixes = (
        "클로야",
        "클로:",
        "클로,",
        "클로 ",
        "!클로",
        "/클로",
        "클로드야",
        "클로드:",
        "클로드,",
        "클로드 ",
        "!claude",
        "/claude",
        "claude:",
        "덱스야",
        "덱스:",
        "덱스,",
        "덱스 ",
        "!덱스",
        "/덱스",
        "코덱스야",
        "코덱스:",
        "코덱스,",
        "코덱스 ",
        "!codex",
        "/codex",
        "codex:",
    )
    for prefix in prefixes:
        if lowered.startswith(prefix.lower()):
            return stripped[len(prefix) :].strip()
    return stripped


def parse_manager_task_command(text: str) -> str | None:
    stripped = _strip_optional_agent_prefix(text)
    _, stripped, context = consume_context_prefix(stripped)
    if not context or context.get("label") != "업무":
        return None

    lowered = stripped.lower()
    prefixes = (
        "할 일 추가 ",
        "할일 추가 ",
        "할 일 등록 ",
        "할일 등록 ",
        "해야 할 일 추가 ",
        "해야할 일 추가 ",
        "해야 할 일 등록 ",
        "해야할 일 등록 ",
        "할 일 ",
        "할일 ",
        "추가 ",
        "등록 ",
    )
    for prefix in prefixes:
        if lowered.startswith(prefix):
            task = stripped[len(prefix) :].strip()
            return task or None
    return None


def strip_both_agents_prefix(text: str) -> tuple[bool, str]:
    stripped = text.strip()
    lowered = stripped.lower()
    prefixes = (
        "둘 다 ",
        "둘다 ",
        "둘 모두 ",
        "둘이 ",
        "둘 다:",
        "둘다:",
        "덱스랑 클로 ",
        "클로랑 덱스 ",
        "덱스와 클로 ",
        "클로와 덱스 ",
        "덱스 클로 ",
        "클로 덱스 ",
    )
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return True, stripped[len(prefix) :].strip()
    return False, stripped


def parse_route(text: str) -> tuple[str, str, bool]:
    stripped = text.strip()
    project_access, stripped, context = consume_context_prefix(stripped)
    lowered = stripped.lower()
    routes = [
        ("claude", ("클로야", "클로:", "클로,", "클로 ", "!클로", "/클로", "클로드야", "클로드:", "클로드,", "클로드 ", "!claude", "/claude", "claude:")),
        ("codex", ("덱스야", "덱스:", "덱스,", "덱스 ", "!덱스", "/덱스", "코덱스야", "코덱스:", "코덱스,", "코덱스 ", "!codex", "/codex", "codex:")),
    ]
    for agent, prefixes in routes:
        for prefix in prefixes:
            if lowered.startswith(prefix.lower()):
                prompt = stripped[len(prefix) :].strip()
                extra_project_access, prompt, extra_context = consume_context_prefix(prompt)
                context = extra_context or context
                return agent, apply_context_note(prompt, context), project_access or extra_project_access
    return DEFAULT_AGENT if DEFAULT_AGENT in ("claude", "codex") else "claude", apply_context_note(stripped, context), project_access


def has_agent_prefix(text: str) -> bool:
    _, stripped, _ = consume_context_prefix(text)
    lowered = stripped.strip().lower()
    prefixes = (
        "클로야",
        "클로:",
        "클로,",
        "클로 ",
        "!클로",
        "/클로",
        "클로드야",
        "클로드:",
        "클로드,",
        "클로드 ",
        "!claude",
        "/claude",
        "claude:",
        "덱스야",
        "덱스:",
        "덱스,",
        "덱스 ",
        "!덱스",
        "/덱스",
        "코덱스야",
        "코덱스:",
        "코덱스,",
        "코덱스 ",
        "!codex",
        "/codex",
        "codex:",
    )
    return lowered.startswith(prefixes)


def parse_routes(text: str) -> list[tuple[str, str, bool]]:
    project_access, without_context_prefix, context = consume_context_prefix(text)
    both_agents, both_prompt = strip_both_agents_prefix(without_context_prefix)
    if both_agents:
        extra_project_access, both_prompt, extra_context = consume_context_prefix(both_prompt)
        context = extra_context or context
        prompt = apply_context_note(both_prompt or "한 문장으로 인사해 주세요.", context)
        access = project_access or extra_project_access
        return [("codex", prompt, access), ("claude", prompt, access)]

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) <= 1:
        return [parse_route(text)]

    parsed = [parse_route(line) for line in lines]
    explicit_count = sum(1 for line in lines if has_agent_prefix(line))
    has_multiple_agents = len({agent for agent, _, _ in parsed}) > 1
    if has_multiple_agents or explicit_count == len(parsed):
        return parsed
    return [parse_route(text)]


def normalize_agent_name(value: str) -> str:
    normalized = value.strip().lower()
    aliases = {
        "클로": "claude",
        "클로드": "claude",
        "claude": "claude",
        "덱스": "codex",
        "코덱스": "codex",
        "codex": "codex",
    }
    return aliases.get(normalized, normalized)


def help_text() -> str:
    return "\n".join(
        [
            "*사용법*",
            "`클로 할 일` - 클로로 실행",
            "`덱스 할 일` - 덱스로 실행",
            "`둘 다 할 일` - 덱스와 클로 둘 다 실행",
            "`slack agent router app으로 뭐 할 수 있어?` - 이 로컬 라우터의 기능 확인",
            "`덱스 카카오 나에게 보내기 할 일 정리해줘` - KMS 카카오 입력에서 할 일 확인",
            "`토론 주제` - Steelman/Double Crux/변증법을 합친 확장 티키타카 토론",
            "`계속` / `다음` / `진행해봐` - 직전 토론의 다음 라운드 진행",
            "`짧게 보고서 형태로 정리해줘` - 활성 토론을 보고서형으로만 요약",
            "`클로야 할 일` / `덱스야 할 일`도 가능",
            "`업무 ...` - KMS workspace 기준의 깊은 작업",
            "`업무 할일 ...` - KMS task 원장에 할 일 추가 후 Today Brief 갱신",
            "`작업 ...` - 인박스/가벼운 작업 폴더 기준",
            "`자료 ...` / `프로젝트 ...` - 전체 프로젝트 폴더를 읽기용으로 호출",
            "`리셋 클로` - 클로 세션 초기화",
            "`리셋 덱스` - 덱스 세션 초기화",
            "`리셋 토론` - Debate Mode 상태 초기화",
            f"기본 라우팅: `{AGENT_DISPLAY.get(DEFAULT_AGENT, DEFAULT_AGENT)}`",
        ]
    )


def post_message(channel: str, text: str, thread_ts: str | None = None) -> dict:
    clean = text.strip() or "(empty)"
    if len(clean) > 35000:
        clean = clean[:35000] + "\n\n...truncated"
    payload = {"channel": channel, "text": clean, "mrkdwn": True}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    return web.chat_postMessage(**payload)


def _local_iso_timestamp() -> str:
    offset = time.strftime("%z")
    if len(offset) == 5:
        offset = offset[:3] + ":" + offset[3:]
    return time.strftime("%Y-%m-%dT%H:%M:%S") + offset


def _yaml_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _split_task_text(text: str) -> tuple[str, str]:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    lines = [line for line in lines if line.strip()]
    if not lines:
        return "Slack 업무 할 일", ""
    title = lines[0].strip()
    body = "\n".join(lines[1:]).strip()
    return title, body


def create_manager_task(task_text: str) -> tuple[Path, str]:
    title, body = _split_task_text(task_text)
    now_iso = _local_iso_timestamp()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    task_id = f"task-slack-{stamp}"
    KMS_TASKS_DIR.mkdir(parents=True, exist_ok=True)
    path = KMS_TASKS_DIR / f"{task_id}.md"
    body_block = body or "Slack에서 추가한 업무 할 일입니다."
    content = f"""---
id: {task_id}
title: {_yaml_quote(title)}
status: in_progress
priority: medium
tags:
  - slack
  - capture
owner: kongdon
source: slack
updated_at: {now_iso}
---

{body_block}

## Progress Log

### {time.strftime("%Y-%m-%d")}

- Slack에서 업무 할 일로 추가됨.
"""
    path.write_text(content, encoding="utf-8")
    LEGACY_TASKS_DIR.mkdir(parents=True, exist_ok=True)
    legacy_path = LEGACY_TASKS_DIR / f"{task_id}.md"
    legacy_path.write_text(content + f"\n<!-- KMS primary: {path} -->\n", encoding="utf-8")
    return path, title


def refresh_manager_today_brief(timeout: int = 180) -> tuple[bool, str]:
    launcher = MANAGER_ROOT / "kk.ps1"
    if not launcher.exists():
        return False, f"kk.ps1 not found: {launcher}"
    try:
        result = subprocess.run(
            [
                POWERSHELL_EXE,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(launcher),
                "today",
            ],
            capture_output=True,
            text=True,
            cwd=str(MANAGER_ROOT),
            env=agent_environment(),
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return False, f"Today brief refresh timed out after {timeout} seconds."
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "unknown error").strip()
    return True, (result.stdout or "").strip()


def refresh_manager_shared_context(timeout: int = 90) -> tuple[bool, str]:
    if not MANAGER_SLACK_SYNC.exists():
        return False, f"sync-slack-outbox.ps1 not found: {MANAGER_SLACK_SYNC}"
    try:
        result = subprocess.run(
            [
                POWERSHELL_EXE,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(MANAGER_SLACK_SYNC),
                "-Root",
                str(MANAGER_ROOT),
                "-Quiet",
            ],
            capture_output=True,
            text=True,
            cwd=str(MANAGER_ROOT),
            env=agent_environment(),
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return False, f"Shared context refresh timed out after {timeout} seconds."
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "unknown error").strip()
    return True, (result.stdout or "").strip()


def should_use_manager_shared_context(prompt: str, context: dict[str, object] | None) -> bool:
    if context and context.get("label") == "업무":
        return True
    if "호출 컨텍스트: 업무" in prompt:
        return True
    keywords = ("오늘 할 일", "오늘할일", "할 일", "할일", "일정", "참고 일정", "참고일정")
    lowered = prompt.lower()
    return any(keyword in lowered for keyword in keywords)


def is_file_mode_request(text: str) -> bool:
    lowered = text.lower()
    file_terms = ("inbox", "인박스", "outbox", "아웃박스", "폴더", "파일", "routing-rules", "라우팅")
    action_terms = ("확인", "처리", "분류", "봐", "열어", "읽어", "정리")
    return any(term in lowered for term in file_terms) and any(term in lowered for term in action_terms)


def is_router_capability_question(text: str) -> bool:
    stripped = _strip_optional_agent_prefix(text)
    lowered = stripped.lower()
    normalized = _normalize_short_text(stripped)
    router_terms = (
        "slack agent router",
        "agent router",
        "slack agent router app",
        "라우터 앱",
        "라우터로",
        "이 앱",
        "슬랙 앱",
    )
    capability_terms = (
        "무엇을 할 수",
        "뭘 할 수",
        "뭐 할 수",
        "어디까지",
        "사용법",
        "기능",
        "가능",
        "명령",
        "할수",
    )
    has_router = any(term in lowered for term in router_terms) or "slackagentrouter" in normalized
    has_capability = any(term in lowered or term in normalized for term in capability_terms)
    return has_router and has_capability


def router_capability_text() -> str:
    return "\n".join(
        [
            "*Slack Agent Router App에서 할 수 있는 일*",
            "",
            "이 앱은 Slack을 KMS의 조종석처럼 쓰게 해주는 로컬 라우터입니다. 일반 Slack 검색 봇이 아니라, Slack 메시지를 읽고 현재 의도를 분류해서 덱스/클로, KMS, 카카오/SMS/폴더 입력, 작업 생성으로 보내는 역할입니다.",
            "",
            "1. *에이전트 실행*",
            "- `덱스 ...`: Codex로 실행",
            "- `클로 ...`: Claude Code로 실행",
            "- `둘 다 ...`: 덱스와 클로 둘 다 실행",
            "",
            "2. *KMS 운영 명령*",
            "- `업무 오늘 할 일 정리해줘`",
            "- `업무 할일 새 콘텐츠 초안 만들기`",
            "- `작업 inbox 확인해줘`",
            "",
            "3. *입력 채널 참조*",
            "- `덱스 카카오 나에게 보내기 할 일 정리해줘`",
            "- `문자에서 들어온 문의만 정리해줘`",
            "- `폴더 인박스 처리해줘`",
            "",
            "4. *토론 모드*",
            "- `둘이 토론해`로 덱스와 클로가 구조/실행 관점과 브랜드/독자 관점으로 토론합니다.",
            "- `다음`, `계속`, `진행해봐`는 활성 토론이 있을 때만 이어갑니다.",
            "",
            "5. *중요한 경계*",
            "- Slack은 기본적으로 조종석입니다. 일반 대화는 자동으로 KMS에 저장하지 않습니다.",
            "- 저장하려면 `저장`, `캡처`, `아카이브`, `등록`처럼 명시해야 합니다.",
            f"- KMS 기준 폴더: `{KMS_ROOT}`",
            f"- KMS task 폴더: `{KMS_TASKS_DIR}`",
        ]
    )


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    normalized = _normalize_short_text(text)
    return any(term.lower() in lowered or _normalize_short_text(term) in normalized for term in terms)


def is_explicit_kms_action_request(text: str) -> bool:
    stripped = _strip_optional_agent_prefix(text)
    if is_explicit_debate_request(stripped):
        return False
    project_access, contextless, context = consume_context_prefix(stripped)
    _ = project_access
    combined = " ".join(part for part in (stripped, contextless) if part)
    target_terms = (
        "카카오",
        "카톡",
        "kakao",
        "나에게 보내기",
        "나에게 보내는 방",
        "문자",
        "sms",
        "알림",
        "notification",
        "kms",
        "슬랙 저장",
        "slack 저장",
        "inbox",
        "인박스",
        "outbox",
        "아웃박스",
        "폴더",
        "파일",
        "일정",
        "캘린더",
        "할 일",
        "할일",
        "task",
    )
    action_terms = (
        "정리",
        "참조",
        "읽어",
        "확인",
        "봐",
        "할 일",
        "할일",
        "task",
        "등록",
        "추가",
        "요약",
        "분류",
        "처리",
        "저장",
        "캡처",
        "아카이브",
        "보내",
    )
    target_hit = bool(context and context.get("label") in ("업무", "작업")) or _has_any(combined, target_terms)
    action_hit = _has_any(combined, action_terms)
    return target_hit and action_hit


def is_context_repair_request(text: str) -> bool:
    normalized = _normalize_short_text(_strip_optional_agent_prefix(text))
    return normalized in {
        "문맥을제대로파악해",
        "문맥파악해",
        "맥락을제대로파악해",
        "맥락파악해",
        "내말을제대로이해해",
    }


def apply_kms_action_note(prompt: str, channel: str) -> str:
    recent = load_recent_context(channel)
    recent_block = ""
    if recent:
        recent_block = (
            "\n\n최근 라우터 상태 참고:\n"
            f"- last mode: {recent.get('mode', '')}\n"
            f"- last user: {_clip(str(recent.get('last_user_text', '')), 500)}"
        )
    return (
        f"{prompt.strip()}\n\n"
        "KMS 라우팅 지침:\n"
        "- 이 요청은 현재 사용자 명령을 우선합니다. 이전 Debate Mode 주제를 이어가지 마세요.\n"
        "- Slack은 조종석이고 KMS가 운영체제입니다. 필요한 경우 KMS 로컬 파일을 읽어 근거로 답하세요.\n"
        f"- KMS root: {KMS_ROOT}\n"
        f"- Kakao inputs: {KMS_KAKAO_INPUTS_DIR}\n"
        f"- Kakao ledger: {KMS_KAKAO_LEDGER_DIR}\n"
        f"- KMS tasks: {KMS_TASKS_DIR}\n"
        "- 카카오/문자/폴더에서 실제 수집된 데이터가 없으면 없다고 말하고, 지어내지 마세요.\n"
        "- 할 일 정리 요청이면 실행 가능한 TASK 후보와 출처를 짧게 나누어 답하세요."
        f"{recent_block}"
    )


def classify_router_intent(text: str, channel: str = SLACK_CHANNEL) -> dict[str, object]:
    lowered = text.strip().lower()
    if lowered in ("!help", "!도움말", "도움말"):
        return {"intent": "help", "clear_debate": False}
    if lowered.startswith("!reset") or lowered.startswith("리셋 "):
        return {"intent": "reset", "clear_debate": False}
    if is_router_capability_question(text):
        return {"intent": "capability", "clear_debate": True}
    if parse_manager_task_command(text):
        return {"intent": "manager_task", "clear_debate": True}
    if is_file_mode_request(text):
        return {"intent": "file_mode", "clear_debate": True}
    if is_explicit_kms_action_request(text):
        return {"intent": "kms_action", "clear_debate": True}
    if is_context_repair_request(text):
        return {"intent": "repair_or_clarify", "clear_debate": False}
    debate_intent = classify_debate_intent(text, channel)
    if debate_intent:
        return {"intent": f"debate_{debate_intent.get('mode', 'new')}", "clear_debate": False, "debate": debate_intent}
    return {"intent": "agent_chat", "clear_debate": False}


def _normalize_short_text(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", text.lower(), flags=re.UNICODE)


def is_debate_continuation(text: str) -> bool:
    normalized = _normalize_short_text(text)
    if not normalized:
        return False
    exact = {
        "계속",
        "다음",
        "다음라운드",
        "진행",
        "진행해",
        "진행해봐",
        "그래진행해봐",
        "좋아진행해봐",
        "응진행해봐",
        "이어가",
        "이어가봐",
    }
    return normalized in exact


def is_debate_report_style_request(text: str) -> bool:
    normalized = _normalize_short_text(text)
    lowered = text.lower()
    if not normalized and not lowered:
        return False
    report_terms = (
        "보고서",
        "보고서형",
        "보고서형태",
        "정리해줘",
        "정리해",
        "요약해줘",
        "요약해",
        "짧게",
        "간단히",
        "brief",
        "summary",
    )
    return any(term in normalized or term in lowered for term in report_terms)


def is_active_debate_report_request(text: str) -> bool:
    if is_file_mode_request(text) or is_explicit_kms_action_request(text):
        return False
    normalized = _normalize_short_text(text)
    lowered = text.lower()
    report_guard_terms = (
        "토론",
        "debate",
        "보고서",
        "보고서형",
        "요약",
        "짧게",
        "간단히",
        "summary",
    )
    return is_debate_report_style_request(text) and any(
        term in normalized or term in lowered for term in report_guard_terms
    )


def is_explicit_debate_request(text: str) -> bool:
    lowered = text.lower()
    terms = (
        "토론",
        "둘이 토론",
        "둘 다 토론",
        "덱스와 클로",
        "덱스랑 클로",
        "클로랑 덱스",
        "반박",
        "합의안",
        "라운드",
        "기준표",
        "전략을 비교",
        "의견 나눠",
        "debate",
    )
    return any(term in lowered for term in terms)


def clean_debate_topic(text: str) -> str:
    topic = text.strip()
    project_access, topic, _ = consume_context_prefix(topic)
    _, topic = strip_both_agents_prefix(topic)
    topic = _strip_optional_agent_prefix(topic)
    _, topic, _ = consume_context_prefix(topic)
    cleanup_patterns = (
        r"^(토론해줘|토론해|토론하자|찬반\s*토론|서로\s*토론|의견\s*나눠|토론)\s*[:：-]?\s*",
        r"\s*(에\s*대해\s*)?(를|을)?\s*(두고|가지고|기준으로)?\s*(토론해줘|토론해|토론하자|토론|찬반\s*토론해줘|찬반\s*토론|상반된\s*입장으로\s*봐줘|의견\s*나눠줘|의견\s*나눠)\s*$",
        r"\s*(를|을)?\s*(두고|가지고|기준으로)\s*$",
    )
    for pattern in cleanup_patterns:
        topic = re.sub(pattern, "", topic, flags=re.IGNORECASE).strip()
    return topic.strip(" .。:：-")


def _looks_generic_topic(topic: str) -> bool:
    normalized = _normalize_short_text(topic)
    return not normalized or normalized in {
        "토론",
        "토론해",
        "토론해줘",
        "둘이토론해",
        "둘다토론해",
        "현재안건",
        "진행",
        "진행해봐",
        "계속",
        "다음",
    }


def infer_topic_from_recent(raw_text: str, channel: str, debate_state: dict[str, object] | None = None) -> str:
    cleaned = clean_debate_topic(raw_text)
    recent = load_recent_context(channel)
    recent_blob = "\n".join(
        str(recent.get(key, ""))
        for key in ("topic", "last_user_text", "last_assistant_text")
    )

    if "threads" in (cleaned + recent_blob).lower() and "기준표" in (cleaned + recent_blob):
        return "Threads 계정 분석 기준표: 퍼스널 브랜딩 발전 목표에 충분한가?"
    if not _looks_generic_topic(cleaned):
        return cleaned
    if debate_state and is_debate_state_active(debate_state):
        topic = str(debate_state.get("next_round_topic") or debate_state.get("topic") or "").strip()
        if topic:
            return topic
    recent_topic = str(recent.get("topic") or "").strip()
    if recent_topic:
        return recent_topic
    recent_user = str(recent.get("last_user_text") or "").strip()
    if recent_user:
        return _clip(recent_user, 180)
    return "직전 산출물과 현재 안건"


def classify_debate_intent(text: str, channel: str) -> dict[str, object] | None:
    if is_file_mode_request(text) or is_explicit_kms_action_request(text) or is_router_capability_question(text):
        return None

    project_access, _, context = consume_context_prefix(text)
    debate_state = load_debate_state(channel)
    active_debate = is_debate_state_active(debate_state)

    if is_debate_continuation(text):
        if not active_debate:
            return None
        return {
            "mode": "continuation",
            "topic": str(debate_state.get("next_round_topic") or debate_state.get("topic") or "직전 토론"),
            "context": context,
            "project_access": bool(debate_state.get("project_access") or project_access),
            "previous_state": debate_state,
            "output_style": "dialogue",
        }

    if active_debate and is_active_debate_report_request(text):
        return {
            "mode": "continuation",
            "topic": str(debate_state.get("next_round_topic") or debate_state.get("topic") or "직전 토론"),
            "context": context,
            "project_access": bool(debate_state.get("project_access") or project_access),
            "previous_state": debate_state,
            "output_style": "report",
        }

    if not is_explicit_debate_request(text):
        return None

    topic = infer_topic_from_recent(text, channel, debate_state)
    inherited_project_access = bool(debate_state.get("project_access")) if active_debate else False
    return {
        "mode": "new",
        "topic": topic,
        "context": context,
        "project_access": project_access or bool(context and context.get("project_access")) or inherited_project_access,
        "previous_state": debate_state if active_debate else {},
        "output_style": "report" if is_debate_report_style_request(text) else "dialogue",
    }


def parse_debate_request(text: str, channel: str = SLACK_CHANNEL) -> tuple[str, dict[str, object] | None, bool] | None:
    intent = classify_debate_intent(text, channel)
    if not intent:
        return None
    return (
        str(intent["topic"]),
        intent.get("context") if isinstance(intent.get("context"), dict) else None,
        bool(intent.get("project_access")),
    )


def _debate_context_block(
    context: dict[str, object] | None,
    previous_state: dict[str, object] | None,
    channel: str,
) -> str:
    lines = []
    recent = load_recent_context(channel)
    if context:
        lines.extend(
            [
                f"호출 컨텍스트: {context['label']}",
                f"기준 폴더: {context['path']}",
                f"처리 기준: {context['note']}",
            ]
        )
    if context and context.get("label") == "업무":
        shared_ok, shared_detail = refresh_manager_shared_context()
        if not shared_ok:
            log(f"shared context refresh failed before debate: {shared_detail[-500:]}")
        lines.extend(
            [
                f"KMS 공유 기준 파일: {MANAGER_SHARED_CONTEXT}",
                "가능하면 위 파일을 먼저 읽고, 현재 할 일/참고 일정과 충돌하지 않는 결론을 내세요.",
            ]
        )
    if previous_state and is_debate_state_active(previous_state):
        lines.extend(
            [
                "",
                "<previous-debate>",
                f"protocol: {previous_state.get('protocol', '')}",
                f"round: {previous_state.get('round', 1)}",
                f"topic: {previous_state.get('topic', '')}",
                f"last_summary: {_clip(str(previous_state.get('last_summary', '')), 3000)}",
                f"next_round_topic: {previous_state.get('next_round_topic', '')}",
                "</previous-debate>",
            ]
        )
    if recent:
        lines.extend(
            [
                "",
                "<recent-exchange>",
                f"mode: {recent.get('mode', '')}",
                f"topic: {recent.get('topic', '')}",
                f"user: {_clip(str(recent.get('last_user_text', '')), 1200)}",
                f"assistant: {_clip(str(recent.get('last_assistant_text', '')), 3500)}",
                "</recent-exchange>",
            ]
        )
    lines.extend(
        [
            "",
            "Debate Mode safety:",
            "- 이 모드에서는 inbox/outbox 확인, routing-rules 실행, 파일 분류, 로컬 폴더 처리로 전환하지 마세요.",
            "- 사용자가 명시적으로 파일/폴더 처리를 요구할 때만 작업 실행 모드로 전환합니다.",
        ]
    )
    return "\n".join(lines)


def _debate_output_protocol(output_style: str) -> str:
    if output_style == "report":
        return """사용자가 명시적으로 짧게/요약/보고서형 정리를 요청했습니다.
이번 응답만 보고서형으로 정리하세요.
보고서형에서도 Steelman, Double Crux, Principled Negotiation, Slow Dialogue, Dialectic Synthesis의 핵심 결과를 압축해 반영하세요.

출력 형식:
## 토론 안건
{현재 토론 안건}

## 요약 판단
{핵심 결론을 2~3문장으로 정리}

## 덱스
- {구조/실행 관점 핵심 판단}
- {측정 가능성 또는 반복 가능성 관점 보강점}

## 클로
- {브랜드/독자 경험 관점 핵심 판단}
- {문체, 감정선, 기억성 관점 보강점}

## 충돌 지점
- {쟁점 1}
- {쟁점 2}

## 합의안
- {최종 합의 1}
- {최종 합의 2}
- {최종 합의 3}

## 최고의 답변
{현재 안건에 대한 최종 통합 답변}

## 다음 라운드
{다음에 다룰 주제 한 문장}"""

    return """기본 출력은 보고서형 분석이 아니라 다중 라운드 티키타카형 토론입니다.
덱스와 클로가 서로의 말을 받아 Steelman, Double Crux, Principled Negotiation, Slow Dialogue, Dialectic Synthesis를 한 번에 적용하고, 마지막에 최고의 통합 답변을 도출하세요.
처음부터 결론을 정리하지 말고, 충분히 부딪히고 기준을 좁힌 뒤 마지막에만 합의안과 최종 답변을 제시하세요.

적용할 토론법:
- Steelman: 반박 전에 상대 주장을 가장 강한 형태로 요약한다.
- Double Crux: 두 사람의 결론을 바꿀 핵심 갈림 조건을 찾는다.
- Principled Negotiation: 입장이 아니라 이해관계, 선택지, 객관 기준으로 판단한다.
- Slow Dialogue: 중간에 속도를 늦추고 독자 감정, 브랜드 인식, 맥락 손상을 점검한다.
- Dialectic Synthesis: 덱스의 작동성 thesis와 클로의 인간미 antithesis를 넘어 제3안을 만든다.

출력 형식:
## 토론 안건
{현재 토론 안건}

## 적용 토론법
- Steelman
- Double Crux
- Principled Negotiation
- Slow Dialogue
- Dialectic Synthesis

## 티키타카 토론

**덱스:**  
{1턴. 구조/실행 관점의 첫 주장. 2~4문장}

**클로:**  
{2턴. 덱스 주장을 Steelman으로 요약한 뒤 브랜드/독자 관점에서 반박. 2~4문장}

**덱스:**  
{3턴. 클로 주장을 Steelman으로 요약한 뒤 일부 수용 또는 재반박. 2~4문장}

**클로:**  
{4턴. Double Crux 후보를 제시한다. 무엇이 확인되면 클로의 판단이 바뀌는지 말한다. 2~4문장}

**덱스:**  
{5턴. 덱스의 Double Crux 후보를 제시하고, 측정 가능한 객관 기준을 제안한다. 2~4문장}

**클로:**  
{6턴. Slow Dialogue로 속도를 늦추고 독자 감정, 말투, 기억성을 점검한다. 2~4문장}

**덱스:**  
{7턴. Principled Negotiation 방식으로 입장 대신 이해관계와 선택지를 재구성한다. 2~4문장}

**클로:**  
{8턴. 선택지 중 브랜드 온도를 해치지 않는 조건을 붙인다. 2~4문장}

**덱스:**  
{9턴. Dialectic Synthesis로 실행 가능한 제3안을 제시한다. 2~4문장}

**클로:**  
{10턴. 제3안이 사람에게 어떻게 기억될지 최종 보완한다. 2~4문장}

## 충돌 지점
- {쟁점 1}
- {쟁점 2}
- {쟁점 3}

## 합의안
- {최종 합의 1}
- {최종 합의 2}
- {최종 합의 3}

## 최고의 답변
{토론을 통해 도출된 최종 답변. 실행 가능성과 브랜드 인간미를 함께 만족해야 한다.}

## 다음 라운드
{다음에 다룰 주제 한 문장}

금지:
- `덱스 의견`, `클로 의견`, `현재 토론 안건 확인`, `서로의 반박` 같은 보고서형 목차로 쓰지 마세요.
- 덱스와 클로의 발언을 병렬 요약으로 나열하지 마세요.
- 합의안을 티키타카 토론보다 먼저 제시하지 마세요."""


def _next_round_topic(topic: str, synthesis: str) -> str:
    lines = synthesis.splitlines()
    for index, line in enumerate(lines):
        clean = line.strip(" #*\t")
        if clean == "다음 라운드":
            for follow in lines[index + 1 :]:
                follow_clean = follow.strip(" -*`")
                if follow_clean:
                    return _clip(follow_clean, 220)

    for line in reversed(synthesis.splitlines()):
        clean = line.strip(" -*`")
        if not clean:
            continue
        if "다음" in clean or "라운드" in clean:
            return _clip(clean, 220)
    return f"{topic}: 합의안 적용 기준을 한 단계 더 좁혀 검증"


DEBATE_SPLIT_SECTION_HEADINGS = {
    "토론 안건",
    "적용 토론법",
    "충돌 지점",
    "합의안",
    "최고의 답변",
    "다음 라운드",
}


def _flush_debate_block(parts: list[str], current: list[str]) -> None:
    text = "\n".join(line.rstrip() for line in current).strip()
    if text:
        parts.append(text)
    current.clear()


def split_debate_reply(reply: str) -> list[str]:
    """Split dialogue-mode debate output into Slack-sized conversational beats."""
    lines = reply.strip().splitlines()
    parts: list[str] = []
    current: list[str] = []
    in_dialogue = False
    found_dialogue_turn = False

    for raw in lines:
        line = raw.rstrip()
        heading = line.strip().lstrip("#").strip()
        is_heading = line.strip().startswith("## ")
        is_speaker = line.strip().startswith("**덱스:**") or line.strip().startswith("**클로:**")

        if is_heading:
            if heading == "티키타카 토론":
                _flush_debate_block(parts, current)
                in_dialogue = True
                continue
            if heading in DEBATE_SPLIT_SECTION_HEADINGS:
                _flush_debate_block(parts, current)
                in_dialogue = False
                current.append(line)
                continue

        if in_dialogue and is_speaker:
            _flush_debate_block(parts, current)
            current.append(line)
            found_dialogue_turn = True
            continue

        current.append(line)

    _flush_debate_block(parts, current)

    if not found_dialogue_turn or len(parts) <= 1:
        return [reply.strip()] if reply.strip() else []
    return parts


def post_debate_messages(channel: str, reply: str, output_style: str) -> None:
    if output_style == "report":
        post_message(channel, reply)
        return

    parts = split_debate_reply(reply)
    if len(parts) <= 1:
        post_message(channel, reply)
        return

    for index, part in enumerate(parts):
        post_message(channel, part)
        if index < len(parts) - 1 and DEBATE_MESSAGE_DELAY_SEC > 0:
            time.sleep(DEBATE_MESSAGE_DELAY_SEC)


def handle_debate_message(event: dict) -> bool:
    channel = event.get("channel") or ""
    text = (event.get("text") or "").strip()
    intent = classify_debate_intent(text, channel)
    if not intent:
        return False

    topic = str(intent["topic"])
    context = intent.get("context") if isinstance(intent.get("context"), dict) else None
    project_access = bool(intent.get("project_access"))
    previous_state = intent.get("previous_state") if isinstance(intent.get("previous_state"), dict) else {}
    mode = str(intent.get("mode") or "new")
    output_style = str(intent.get("output_style") or "dialogue")
    ts = event.get("ts") or ""
    context_block = _debate_context_block(context, previous_state, channel)
    output_protocol = _debate_output_protocol(output_style)
    if context and context.get("label") == "업무":
        project_access = True

    try:
        web.reactions_add(channel=channel, timestamp=ts, name="hourglass_flowing_sand")
    except Exception as exc:
        log(f"reaction add failed: {exc}")

    codex_prompt = f"""KMS Debate Mode입니다.

현재 토론 안건:
{topic}

진행 유형: {mode}

{context_block}

역할: 덱스
- 구조, 실행 가능성, 시스템 설계, 확장성, 검증 가능성을 본다.
- 말투는 직설적이고 실행 중심이다.
- 애매한 표현을 싫어하고 "측정 가능한가?", "반복 가능한가?", "전환 구조가 있는가?"를 따진다.
- 무조건 찬성하지 말고 구조가 약하면 반대하거나 보류한다.
- 기준표/전략/산출물이 실제 운영으로 이어지는지 검토한다.

출력:
덱스의 첫 주장과 클로가 반박할 만한 논점을 3~6문장으로 쓰세요.
Steelman, Double Crux, Principled Negotiation 단계에서 다룰 수 있는 핵심 갈림 조건도 1개 포함하세요.
최종 Slack 출력은 별도 합성 단계에서 티키타카 대화로 만들 예정이므로 보고서 목차를 쓰지 마세요."""

    try:
        codex_reply = call_codex(codex_prompt, channel, project_access=project_access)
        claude_prompt = f"""KMS Debate Mode입니다.

현재 토론 안건:
{topic}

진행 유형: {mode}

{context_block}

<dex-opening>
{codex_reply}
</dex-opening>

역할: 클로
- 브랜드 인식, 문체, 감정선, 인간미, 독자 경험을 본다.
- 말투는 섬세하고 독자 감각 중심이다.
- "이 사람답게 느껴지는가?", "독자가 어떤 감정을 느끼는가?", "기억되는 문장이 있는가?"를 따진다.
- 너무 시스템화되면 브랜드의 온도가 죽는다는 점을 경계한다.
- 무조건 반대하지 말고 브랜드/독자 관점에서 좋으면 승인한다.
- 기준표/전략/산출물이 사람에게 어떻게 보이는지 검토한다.

출력:
덱스의 말을 짧게 요약하거나 인용한 뒤, 클로 관점의 반박/보완을 3~6문장으로 쓰세요.
덱스 주장의 가장 좋은 버전을 먼저 인정한 뒤, 독자 감정과 브랜드 기억 관점에서 Double Crux 후보를 1개 제시하세요.
최종 Slack 출력은 별도 합성 단계에서 티키타카 대화로 만들 예정이므로 보고서 목차를 쓰지 마세요."""
        claude_reply = call_claude(claude_prompt, channel, project_access=project_access)
        codex_rebuttal_prompt = f"""KMS Debate Mode 추가 라운드입니다.

현재 토론 안건:
{topic}

진행 유형: {mode}

{context_block}

<dex-opening>
{codex_reply}
</dex-opening>

<clo-opening>
{claude_reply}
</clo-opening>

역할: 덱스
- 클로의 브랜드/독자 경험 주장을 Steelman으로 먼저 요약한다.
- 그다음 Double Crux를 좁힌다. 무엇이 확인되면 덱스의 판단이 바뀌는가?
- Principled Negotiation 방식으로 이해관계, 선택지, 객관 기준을 제안한다.

출력:
덱스의 재반박 또는 수정안을 4~7문장으로 쓰세요.
보고서 목차를 쓰지 말고, 클로의 말을 직접 받아서 반응하세요."""
        codex_rebuttal = call_codex(codex_rebuttal_prompt, channel, project_access=project_access)
        claude_refinement_prompt = f"""KMS Debate Mode 추가 라운드입니다.

현재 토론 안건:
{topic}

진행 유형: {mode}

{context_block}

<dex-opening>
{codex_reply}
</dex-opening>

<clo-opening>
{claude_reply}
</clo-opening>

<dex-rebuttal>
{codex_rebuttal}
</dex-rebuttal>

역할: 클로
- 덱스의 수정안을 Steelman으로 먼저 요약한다.
- Slow Dialogue 방식으로 속도를 늦추고, 독자 감정/문체/기억성 손상을 점검한다.
- Dialectic Synthesis를 위해 브랜드 온도를 해치지 않는 조건을 붙인다.

출력:
클로의 재보완 또는 수정안을 4~7문장으로 쓰세요.
보고서 목차를 쓰지 말고, 덱스의 말을 직접 받아서 반응하세요."""
        claude_refinement = call_claude(claude_refinement_prompt, channel, project_access=project_access)
        judge_prompt = f"""KMS Debate Mode 최종 출력 작성입니다.

현재 토론 안건:
{topic}

진행 유형: {mode}

{context_block}

<dex-raw-position>
{codex_reply}
</dex-raw-position>

<clo-raw-position>
{claude_reply}
</clo-raw-position>

<dex-rebuttal>
{codex_rebuttal}
</dex-rebuttal>

<clo-refinement>
{claude_refinement}
</clo-refinement>

출력 스타일: {output_style}

{output_protocol}

주의:
- inbox, outbox, routing-rules, 폴더 처리 이야기를 꺼내지 마세요.
- 실제 안건과 직전 산출물을 기준으로 토론하세요.
- 덱스와 클로가 서로의 말을 받아서 반응하게 만드세요.
- 대화형 출력에서는 덱스와 클로가 각각 최소 5번 이상 발언해야 합니다.
- 각 발언은 2~4문장으로 제한하세요.
- Steelman, Double Crux, Principled Negotiation, Slow Dialogue, Dialectic Synthesis가 모두 눈에 보이게 반영되어야 합니다.
- 마지막에는 `최고의 답변` 섹션으로 현재 안건의 최종 통합 답변을 제시하세요.
- 다음 라운드 제안은 한 문장으로 끝내세요.
- 한국어로 간결하게 답하세요."""
        synthesis = call_codex(judge_prompt, channel, project_access=project_access)
        reply = synthesis.strip()
        post_debate_messages(channel, reply, output_style)
        round_number = int(previous_state.get("round", 0) or 0) + 1
        save_debate_state(
            channel,
            {
                "mode": "debate",
                "topic": topic,
                "round": round_number,
                "project_access": project_access,
                "context_label": context.get("label") if context else "",
                "context_path": str(context.get("path")) if context else "",
                "last_user_text": text,
                "last_dex": _clip(f"{codex_reply}\n\n{codex_rebuttal}", 4000),
                "last_clo": _clip(f"{claude_reply}\n\n{claude_refinement}", 4000),
                "last_dex_rebuttal": _clip(codex_rebuttal, 3000),
                "last_clo_refinement": _clip(claude_refinement, 3000),
                "last_summary": _clip(reply, 6000),
                "next_round_topic": _next_round_topic(topic, reply),
                "output_style": output_style,
                "protocol": "KMS Steelman Dialectic Protocol",
            },
        )
        record_recent_exchange(channel, text, reply, mode="debate", topic=topic)
        final_reaction = "white_check_mark"
    except Exception as exc:
        log(f"debate failed: {exc}")
        post_message(channel, f"토론 실행 중 오류가 났습니다: `{type(exc).__name__}`")
        final_reaction = "warning"

    try:
        web.reactions_remove(channel=channel, timestamp=ts, name="hourglass_flowing_sand")
        web.reactions_add(channel=channel, timestamp=ts, name=final_reaction)
    except Exception as exc:
        log(f"reaction swap failed: {exc}")
    return True


def handle_manager_task_message(event: dict) -> bool:
    text = (event.get("text") or "").strip()
    task_text = parse_manager_task_command(text)
    if not task_text:
        return False

    channel = event.get("channel") or ""
    ts = event.get("ts") or ""
    try:
        web.reactions_add(channel=channel, timestamp=ts, name="hourglass_flowing_sand")
    except Exception as exc:
        log(f"reaction add failed: {exc}")

    task_path, title = create_manager_task(task_text)
    ok, detail = refresh_manager_today_brief()
    shared_ok, shared_detail = refresh_manager_shared_context()
    latest_brief = MANAGER_ROOT / "workspace" / "system" / "briefs" / "latest.md"
    if ok and shared_ok:
        reply = "\n".join(
            [
                "*업무 할 일 추가 완료*",
                f"- 제목: `{title}`",
                f"- task: `{task_path}`",
                f"- latest brief: `{latest_brief}`",
                f"- shared context: `{MANAGER_SHARED_CONTEXT}`",
            ]
        )
        final_reaction = "white_check_mark"
    else:
        log(f"manager refresh failed: today={detail[-500:]} shared={shared_detail[-500:]}")
        reply = "\n".join(
            [
                "*업무 할 일은 추가했지만 후속 갱신 일부가 실패했습니다.*",
                f"- 제목: `{title}`",
                f"- task: `{task_path}`",
                "- 나중에 `업무 오늘 해야 할 일 정리해줘`로 다시 확인해 주세요.",
            ]
        )
        final_reaction = "warning"
    post_message(channel, reply)
    record_recent_exchange(channel, text, reply, mode="task", topic=title)

    try:
        web.reactions_remove(channel=channel, timestamp=ts, name="hourglass_flowing_sand")
        web.reactions_add(channel=channel, timestamp=ts, name=final_reaction)
    except Exception as exc:
        log(f"reaction swap failed: {exc}")
    log(f"manager_task title={title[:80]} path={task_path}")
    return True


def handle_router_capability_message(event: dict) -> bool:
    text = (event.get("text") or "").strip()
    if not is_router_capability_question(text):
        return False
    channel = event.get("channel") or ""
    clear_debate_state(channel)
    reply = router_capability_text()
    post_message(channel, reply)
    record_recent_exchange(channel, text, reply, mode="capability", topic="Slack Agent Router App capabilities")
    return True


def handle_kms_action_message(event: dict) -> bool:
    text = (event.get("text") or "").strip()
    if not is_explicit_kms_action_request(text):
        return False

    channel = event.get("channel") or ""
    ts = event.get("ts") or ""
    clear_debate_state(channel)
    try:
        web.reactions_add(channel=channel, timestamp=ts, name="hourglass_flowing_sand")
    except Exception as exc:
        log(f"reaction add failed: {exc}")

    try:
        shared_ok, shared_detail = refresh_manager_shared_context()
        if not shared_ok:
            log(f"shared context refresh failed before kms action: {shared_detail[-500:]}")
        routes_to_run = parse_routes(text)
        responses: list[str] = []
        for agent, prompt, _project_access in routes_to_run:
            kms_prompt = apply_kms_action_note(prompt, channel)
            if shared_ok:
                kms_prompt += f"\n- KMS shared context: {MANAGER_SHARED_CONTEXT}"
            if agent == "codex":
                reply = call_codex(kms_prompt, channel, project_access=True)
            else:
                reply = call_claude(kms_prompt, channel, project_access=True)
            responses.append(f"*{AGENT_DISPLAY.get(agent, agent)}*\n{reply}")
        combined_reply = "\n\n".join(responses)
        post_message(channel, combined_reply)
        record_recent_exchange(channel, text, combined_reply, mode="kms_action", topic="KMS action")
        final_reaction = "white_check_mark"
    except Exception as exc:
        log(f"kms action handler failed: {exc}")
        post_message(channel, f"KMS 요청 처리 중 오류가 났습니다: `{type(exc).__name__}`")
        final_reaction = "warning"

    try:
        web.reactions_remove(channel=channel, timestamp=ts, name="hourglass_flowing_sand")
        web.reactions_add(channel=channel, timestamp=ts, name=final_reaction)
    except Exception as exc:
        log(f"reaction swap failed: {exc}")
    return True


def handle_context_repair_message(event: dict) -> bool:
    text = (event.get("text") or "").strip()
    if not is_context_repair_request(text):
        return False
    channel = event.get("channel") or ""
    recent = load_recent_context(channel)
    last_user_text = str(recent.get("last_user_text") or "").strip()
    if last_user_text and is_explicit_kms_action_request(last_user_text):
        repaired = dict(event)
        repaired["text"] = last_user_text
        return handle_kms_action_message(repaired)

    clear_debate_state(channel)
    reply = "맞아요. 직전 답변은 이전 토론 문맥에 끌려갔을 가능성이 큽니다. 다시 처리할 대상을 `카카오`, `문자`, `업무`, `작업`, `inbox` 중 하나와 함께 한 문장으로 보내주세요."
    post_message(channel, reply)
    record_recent_exchange(channel, text, reply, mode="repair_or_clarify", topic="context repair")
    return True


def handle_message(event: dict) -> None:
    text = (event.get("text") or "").strip()
    channel = event.get("channel") or ""
    ts = event.get("ts") or ""
    user = event.get("user") or ""
    bot_id = event.get("bot_id") or ""

    if not text or channel != SLACK_CHANNEL:
        return
    if BOT_USER_ID and user == BOT_USER_ID:
        return
    if bot_id:
        return
    if USER_SLACK_ID and user != USER_SLACK_ID:
        return

    lowered = text.lower()
    if lowered in ("!help", "!도움말", "도움말"):
        post_message(channel, help_text())
        return
    if lowered.startswith("!reset") or lowered.startswith("리셋 "):
        parts = lowered.split()
        target = normalize_agent_name(parts[1]) if len(parts) > 1 else "all"
        if target in ("claude", "all"):
            reset_session("claude", channel)
        if target in ("codex", "all"):
            delete_session("codex", channel)
        if target in ("debate", "토론", "all"):
            clear_debate_state(channel)
        target_label = "전체" if target == "all" else AGENT_DISPLAY.get(target, target)
        if target in ("debate", "토론"):
            target_label = "토론"
        post_message(channel, f"세션을 초기화했습니다: `{target_label}`")
        return
    if lowered in ("클로 리셋", "클로드 리셋", "claude reset"):
        reset_session("claude", channel)
        post_message(channel, "세션을 초기화했습니다: `클로`")
        return
    if lowered in ("덱스 리셋", "코덱스 리셋", "codex reset"):
        delete_session("codex", channel)
        post_message(channel, "세션을 초기화했습니다: `덱스`")
        return
    if handle_router_capability_message(event):
        return
    if handle_manager_task_message(event):
        return
    if handle_kms_action_message(event):
        return
    if handle_context_repair_message(event):
        return
    if handle_debate_message(event):
        return
    if is_file_mode_request(text):
        clear_debate_state(channel)

    routes_to_run = parse_routes(text)
    prepared_routes = []
    for agent, prompt, project_access in routes_to_run:
        _, _, context = consume_context_prefix(text)
        if should_use_manager_shared_context(prompt, context):
            shared_ok, shared_detail = refresh_manager_shared_context()
            if not shared_ok:
                log(f"shared context refresh failed: {shared_detail[-500:]}")
            prompt = (
                f"{prompt}\n\n"
                f"KMS 공유 기준 파일: {MANAGER_SHARED_CONTEXT}\n"
                "위 파일이 있으면 먼저 읽고, 오늘 할 일/참고 일정/슬랙 outbox 관련 질문은 그 기준으로 답하세요. "
                "충돌이 있으면 KMS workspace의 task/calendar 상태를 우선하세요."
            )
            project_access = True
        prepared_routes.append((agent, prompt, project_access))
    routes_to_run = prepared_routes
    log(f"routes={','.join(agent for agent, _, _ in routes_to_run)} user={user} text={text[:100]}")

    try:
        web.reactions_add(channel=channel, timestamp=ts, name="hourglass_flowing_sand")
    except Exception as exc:
        log(f"reaction add failed: {exc}")

    try:
        responses: list[str] = []
        for agent, prompt, project_access in routes_to_run:
            if agent == "codex":
                reply = call_codex(prompt, channel, project_access=project_access)
            else:
                reply = call_claude(prompt, channel, project_access=project_access)
            responses.append(f"*{AGENT_DISPLAY.get(agent, agent)}*\n{reply}")
        combined_reply = "\n\n".join(responses)
        post_message(channel, combined_reply)
        record_recent_exchange(channel, text, combined_reply, mode="chat", topic="")
        final_reaction = "white_check_mark"
    except Exception as exc:
        log(f"handler failed: {exc}")
        post_message(channel, f"실행 중 오류가 났습니다: `{type(exc).__name__}`")
        final_reaction = "warning"

    try:
        web.reactions_remove(channel=channel, timestamp=ts, name="hourglass_flowing_sand")
        web.reactions_add(channel=channel, timestamp=ts, name=final_reaction)
    except Exception as exc:
        log(f"reaction swap failed: {exc}")


def on_event(client: SocketModeClient, req: SocketModeRequest) -> None:
    client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
    if req.type != "events_api":
        return
    event = req.payload.get("event", {})
    if event.get("type") == "message" and not event.get("subtype"):
        threading.Thread(target=handle_message, args=(event,), daemon=True).start()


def main() -> None:
    log(f"{BOT_NAME} starting channel={SLACK_CHANNEL} default={DEFAULT_AGENT} cwd={AGENT_WORKDIR} project={PROJECT_ROOT}")
    sock.socket_mode_request_listeners.append(on_event)
    sock.connect()
    log("Socket Mode connected")
    while True:
        time.sleep(60)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log(f"fatal: {exc}")
        raise
