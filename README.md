# agent-router-kit

AI가 설치를 도와주는 Slack 기반 개인 에이전트 라우터입니다.

Slack을 명령 입구로 쓰고, 로컬 컴퓨터의 Claude Code와 Codex를 호출합니다. 기본은 Slack 라우터이고, 필요하면 local workspace, SMS 입력, Kakao 입력을 선택 모듈로 붙입니다.

이 프로젝트는 [orot-ai/agent-bootstrap](https://github.com/orot-ai/agent-bootstrap)에서 영감을 받았습니다. 자세한 출처 표기는 `NOTICE`를 보세요.

## 5분 요약

1. 이 repo를 clone 또는 download 합니다.
2. Claude Code나 Codex를 열고 `INSTALL_WITH_AI.md`를 읽혀 설치를 시작합니다.
3. Slack App을 만들고 Socket Mode, Bot Token, App Token을 준비합니다.
4. AI가 `.agent-router-kit/secrets/slack-agent-router.env` 위치를 만들어 주면 토큰은 직접 입력합니다.
5. Slack 채널에서 `코덱스 안녕`, `클로드 안녕`, `둘이 토론해`를 테스트합니다.

## 무엇을 할 수 있나

- Slack에서 `코덱스 ...`로 Codex 실행
- Slack에서 `클로드 ...`로 Claude Code 실행
- `덱스`, `클로` 같은 짧은 이름은 사용자가 정한 별칭이며 env에서 변경 가능
- `둘 다 ...`로 두 에이전트 호출
- `둘이 토론해`, `다음`, `계속`, `리셋 토론`으로 Debate Mode 사용
- `업무 ...`, `작업 ...`, `자료 ...`로 local workspace 맥락 사용
- 선택 모듈로 SMS, Kakao, folder input을 로컬 markdown/SQLite 자료로 수집

## 공개 인터페이스

환경 파일은 `.env.example` 또는 `templates/slack-agent-router/slack-agent-router.env.example`을 기준으로 합니다.

```env
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
SLACK_CHANNEL=C0XXXXXXXXX
USER_SLACK_ID=U0XXXXXXXXX

DEFAULT_AGENT=codex
CLAUDE_DISPLAY_NAME=클로드
CODEX_DISPLAY_NAME=코덱스
CLAUDE_ALIASES=클로드,claude,클로
CODEX_ALIASES=코덱스,codex,덱스
CLAUDE_EXE=claude
CODEX_EXE=codex

WORKSPACE_ROOT={USER_HOME}/agent-router-workspace
PROJECT_ROOT={USER_HOME}/agent-router-projects

ENABLE_WORKSPACE=1
ENABLE_SMS=0
ENABLE_KAKAO=0
```

토큰은 절대 GitHub, Slack, AI 채팅창에 붙여넣지 마세요. 로컬 env 파일에만 저장합니다.

## 빠른 설치

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1 -EnableWorkspace
```

macOS:

```bash
bash ./scripts/install-macos.sh --enable-workspace
```

설치 전에 안전하게 확인하려면 `-DryRun` 또는 `--dry-run`을 사용합니다.

## Slack 명령 예시

```text
코덱스 안녕
클로드 이 문장 더 자연스럽게 고쳐줘
둘 다 이 아이디어의 장단점 봐줘
둘이 토론해
다음
업무 할일 테스트 작업 추가
자료 이 폴더 구조 요약해줘
slack agent router app으로 뭐 할 수 있어?
```

## 로컬 데이터 구조

```text
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

Slack은 기본적으로 조작 인터페이스입니다. 명시적으로 저장, 분류, 업무 등록, Kakao/SMS 수집을 요청했을 때만 local workspace 입력으로 보냅니다.

## 문서

- `INSTALL_WITH_AI.md`: Claude/Codex에게 그대로 던지는 설치 안내
- `SKILL.md`: AI 설치 에이전트용 상세 절차
- `docs/beginner-tutorial.md`: 자동화 입문자용 설치 튜토리얼
- `docs/feature-reference.md`: 명령, env, 폴더, 선택 모듈 레퍼런스
- `docs/e2e-checklist.md`: 새 설치 기준 실전 E2E 체크리스트
- `modules/01-slack-router.md`: Slack router 설정
- `modules/02-local-workspace.md`: local workspace 구조
- `modules/03-sms-input.md`: Android Tasker/iPhone Shortcuts SMS 입력
- `modules/04-kakao-input.md`: Kakao 입력 가이드
- `docs/security.md`: 보안 체크리스트
- `docs/troubleshooting.md`: 자주 막히는 지점
- `docs/demo-script.md`: 설치 시연 흐름
- `docs/presentation/agent-router-kit-deck.json`: PPT 제작용 범용 JSON
- `docs/presentation/agent-router-kit-script.md`: 8분 발표 대본

## 배포 전 검증

릴리스 전에 다음 명령으로 공개 안전 스캔, 설치 smoke, router intent, 문서 일관성, 선택 입력 모듈을 확인합니다.

```powershell
.\scripts\verify-release.ps1
```

Python 경로를 직접 지정해야 하면 다음처럼 실행합니다.

```powershell
.\scripts\verify-release.ps1 -PythonExe "C:\Path\To\python.exe"
```

## v1 범위

포함:

- Windows/macOS Slack router
- Claude/Codex 호출
- Debate Mode와 context guard
- Local workspace
- 선택 SMS/Kakao input module

제외:

- Notion, Google Drive, Google Calendar 자동 동기화
- 클라우드 상시 서버 배포
- Slack workspace 관리자 기능

이 프로젝트의 v1 목표는 “비개발자가 AI와 함께 설치해서 자기 컴퓨터에서 돌리는 개인 운영 라우터”입니다.
