# Feature Reference

`agent-router-kit`은 Slack에서 짧게 명령하고, 로컬 컴퓨터의 Claude Code와 Codex가 일을 처리하게 하는 개인 라우터입니다.

## 기능 한눈에 보기

| 기능 | 설명 | 기본/선택 |
|---|---|---|
| Slack router | Slack 메시지를 읽고 Claude Code 또는 Codex로 보냅니다. | 기본 |
| Agent aliases | `코덱스`, `클로드` 호출명과 별칭을 바꿀 수 있습니다. | 기본 |
| Both agents | 한 요청을 Claude Code와 Codex 둘 다에게 보냅니다. | 기본 |
| Debate Mode | 두 도우미가 서로 반박하고 통합안을 냅니다. | 기본 |
| Context guard | 이전 토론 문맥이 업무 명령을 덮어쓰지 않게 막습니다. | 기본 |
| local workspace | 입력, 처리 결과, 원장을 로컬 폴더에 정리합니다. | 기본 권장 |
| SMS input | 문자 이벤트를 분류하고 필요한 것은 TASK로 만듭니다. | 선택 |
| Kakao input | Kakao 메시지를 local workspace 입력으로 모읍니다. | 선택 |
| Auto start | 컴퓨터 로그인 시 라우터를 자동 실행합니다. | 선택 |

## Slack 명령

| 명령 | 뜻 |
|---|---|
| `코덱스 ...` | Codex로 실행합니다. |
| `클로드 ...` | Claude Code로 실행합니다. |
| `둘 다 ...` | Claude Code와 Codex 둘 다 실행합니다. |
| `둘이 토론해` | Debate Mode를 시작합니다. |
| `다음` | 직전 Debate Mode가 살아 있을 때 다음 라운드를 진행합니다. |
| `계속` | 직전 Debate Mode 또는 대화 흐름을 이어갑니다. |
| `리셋 토론` | Debate Mode 상태를 지웁니다. |
| `업무 할일 ...` | local workspace에 작업 후보로 처리합니다. |
| `자료 ...` | 자료나 폴더 맥락을 보고 정리합니다. |
| `slack agent router app으로 뭐 할 수 있어?` | agent-router-kit 기능을 설명합니다. |

## 별칭

공식 설명에서는 Claude Code와 Codex를 사용합니다. 한국어 기본 호출명은 `클로드`, `코덱스`입니다.

`덱스`, `클로`는 짧은 별칭 예시일 뿐입니다. 사용자는 env에서 마음대로 바꿀 수 있습니다.

```env
CLAUDE_DISPLAY_NAME=클로드
CODEX_DISPLAY_NAME=코덱스
CLAUDE_ALIASES=클로드,claude,클로
CODEX_ALIASES=코덱스,codex,덱스
```

## env 변수

| 변수 | 설명 | 예시 |
|---|---|---|
| `SLACK_BOT_TOKEN` | Bot User OAuth Token | `xoxb-your-bot-token` |
| `SLACK_APP_TOKEN` | Socket Mode App-Level Token | `xapp-your-app-token` |
| `SLACK_CHANNEL` | 라우터가 답할 채널 ID | `C0XXXXXXXXX` |
| `USER_SLACK_ID` | 사용자 멤버 ID | `U0XXXXXXXXX` |
| `DEFAULT_AGENT` | 접두사 없는 메시지의 기본 대상 | `codex` 또는 `claude` |
| `CLAUDE_EXE` | Claude Code 실행 명령 | `claude` |
| `CODEX_EXE` | Codex 실행 명령 | `codex` |
| `CLAUDE_DISPLAY_NAME` | Slack 응답에 보일 Claude 이름 | `클로드` |
| `CODEX_DISPLAY_NAME` | Slack 응답에 보일 Codex 이름 | `코덱스` |
| `CLAUDE_ALIASES` | Claude 호출명 목록 | `클로드,claude,클로` |
| `CODEX_ALIASES` | Codex 호출명 목록 | `코덱스,codex,덱스` |
| `WORKSPACE_ROOT` | local workspace 위치 | `{USER_HOME}/agent-router-workspace` |
| `PROJECT_ROOT` | 프로젝트 자료 기본 위치 | `{USER_HOME}/agent-router-projects` |
| `ENABLE_WORKSPACE` | local workspace 사용 여부 | `1` |
| `ENABLE_SMS` | SMS 입력 사용 여부 | `0` 또는 `1` |
| `ENABLE_KAKAO` | Kakao 입력 사용 여부 | `0` 또는 `1` |

## local workspace 구조

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

| 폴더 | 역할 |
|---|---|
| `inputs/slack` | Slack에서 저장하도록 요청한 입력 |
| `inputs/sms` | SMS에서 들어온 원본 요약 |
| `inputs/kakao` | Kakao에서 들어온 원본 요약 |
| `processed/tasks` | 실제 해야 할 일 |
| `processed/memos` | 참고 메모 |
| `processed/finance` | 카드 사용, 입금, 출금 기록 |
| `processed/questions` | 문의나 답변이 필요한 내용 |
| `processed/noise` | 인증, 광고, 알림처럼 보관만 하거나 무시할 내용 |
| `ledger` | SQLite, JSONL, 로그 같은 원장 |

## SMS input

SMS input은 문자 내용을 다음처럼 분류합니다.

| 분류 | 예시 | 기본 처리 |
|---|---|---|
| 카드 사용 | 카드 승인, 사용, 결제 | finance |
| 입금 | 입금, 이체입금 | finance |
| 출금 | 출금, 자동이체 | finance |
| 문의 | 미팅 가능, 답변 요청 | tasks |
| 인증 | 인증번호, OTP | noise |
| 알림 | 배송, 공지, 안내 | noise |

SMS는 로컬에 저장되며, 민감한 값은 가능한 범위에서 마스킹합니다.

## Kakao input

Kakao input은 v1에서 Windows PC Kakao 중심입니다. 사용자가 의도적으로 준비한 대화방 또는 나에게 보내기 방을 읽고 local workspace에 정리합니다.

권장 사용:

```text
코덱스 카카오 나에게 보내기 방에서 들어온 할 일 정리해줘
```

## 실패 대응 표

| 증상 | 확인 위치 | 해결 행동 |
|---|---|---|
| Slack에서 응답이 없음 | 라우터 터미널 로그 | 라우터가 실행 중인지 확인합니다. |
| `xapp-` 토큰 오류 | env 파일 | App-Level Token과 Bot Token을 바꿔 넣지 않았는지 확인합니다. |
| 채널에서 봇이 안 보임 | Slack 채널 | 봇을 테스트 채널에 초대합니다. |
| `코덱스`가 안 됨 | `CODEX_EXE` | Codex CLI 명령이 터미널에서 실행되는지 확인합니다. |
| `클로드`가 안 됨 | `CLAUDE_EXE` | Claude Code 명령이 터미널에서 실행되는지 확인합니다. |
| `다음`이 엉뚱한 토론으로 감 | Slack에서 `리셋 토론` | Debate Mode 상태를 초기화합니다. |
| 업무 명령이 토론으로 감 | 명령 문장 | `업무`, `작업`, `자료`, `카카오`, `문자`처럼 대상을 명확히 씁니다. |
| SMS/Kakao 파일이 안 생김 | `WORKSPACE_ROOT/scripts` | 선택 모듈 스크립트가 설치 후 workspace 안에 있는지 확인합니다. |

## 활용 시나리오

| 하고 싶은 일 | Slack에서 보내는 말 |
|---|---|
| Codex에게 질문하기 | `코덱스 이 에러 원인 봐줘` |
| Claude Code에게 문장 다듬기 | `클로드 이 문장 자연스럽게 고쳐줘` |
| 둘 다에게 비교 검토시키기 | `둘 다 이 기획의 장단점 봐줘` |
| 토론시키기 | `둘이 토론해` |
| 할 일 저장하기 | `업무 할일 내일 오전 자료 정리` |
| 자료 폴더 참조하기 | `자료 이 폴더 구조 요약해줘` |
| SMS 입력 모으기 | `문자에서 오늘 들어온 문의 정리해줘` |
| Kakao 입력 모으기 | `카카오 나에게 보내기 방에서 할 일 뽑아줘` |
| 자동 시작하기 | Windows `-RegisterTask`, macOS `--register-launchd` |
