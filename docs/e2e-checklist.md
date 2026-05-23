# Fresh Install E2E Checklist

이 체크리스트는 완전히 새로 설치하는 사용자가 실제 Slack 연결까지 확인하는 절차입니다.

자동 테스트는 토큰 없이 실행할 수 있습니다. 실제 Slack 앱 생성, 토큰 입력, 채널 초대는 사용자가 직접 해야 합니다.

## 1. 로컬 검증

```powershell
.\scripts\verify-release.ps1
```

Python 경로를 직접 지정해야 하면 다음처럼 실행합니다.

```powershell
.\scripts\verify-release.ps1 -PythonExe "C:\Path\To\python.exe"
```

검증 항목:

- 공개 안전 스캔
- 라우터 intent 테스트
- 문서 일관성 테스트
- workspace input 테스트
- Python 문법 검사
- Windows DryRun
- Windows temp 실제 설치
- macOS DryRun 가능 여부 확인

## 2. Slack 앱 생성

- [ ] 새 Slack App을 만든다.
- [ ] Socket Mode를 켠다.
- [ ] App-Level Token을 만들고 `connections:write`를 추가한다.
- [ ] Bot Token Scopes를 추가한다.
- [ ] 앱을 workspace에 설치한다.
- [ ] 봇을 비공개 테스트 채널에 초대한다.
- [ ] 채널 ID를 복사한다.
- [ ] 내 Slack 멤버 ID를 복사한다.

필수 Bot Token Scopes:

```text
app_mentions:read
channels:history
channels:read
chat:write
groups:history
groups:read
im:history
im:read
mpim:history
mpim:read
```

## 3. env 입력

env 파일을 엽니다.

Windows:

```text
%USERPROFILE%\.agent-router-kit\secrets\slack-agent-router.env
```

macOS:

```text
~/.agent-router-kit/secrets/slack-agent-router.env
```

다음 값을 직접 입력합니다.

- [ ] `SLACK_BOT_TOKEN=xoxb-...`
- [ ] `SLACK_APP_TOKEN=xapp-...`
- [ ] `SLACK_CHANNEL=C...` 또는 `G...`
- [ ] `USER_SLACK_ID=U...`
- [ ] `DEFAULT_AGENT=codex` 또는 `claude`
- [ ] `WORKSPACE_ROOT`가 원하는 위치인지 확인
- [ ] `ENABLE_WORKSPACE=1`

토큰을 AI 채팅창, GitHub, Slack 메시지에 붙여넣지 않습니다.

## 4. 라우터 실행

Windows:

```powershell
& "$env:USERPROFILE\.agent-router-kit\slack-agent-router\run.ps1"
```

macOS:

```bash
~/.agent-router-kit/slack-agent-router/run.sh
```

기대 로그:

```text
Slack Agent Router starting ...
Socket Mode connected
```

## 5. Slack 테스트

테스트 채널에서 순서대로 보냅니다.

| 테스트 | 입력 | 기대 결과 |
|---|---|---|
| Codex | `코덱스 안녕` | Codex 응답 |
| Claude Code | `클로드 안녕` | Claude Code 응답 |
| 둘 다 | `둘 다 한 문장으로 인사해` | 두 응답이 분리되어 표시 |
| Debate Mode | `둘이 토론해` | 토론 안건과 티키타카형 토론 |
| 업무 저장 | `업무 할일 테스트 작업 추가` | local workspace 작업 처리 |
| 기능 질문 | `slack agent router app으로 뭐 할 수 있어?` | agent-router-kit 기능 설명 |
| 상태 초기화 | `리셋 토론` | Debate Mode 초기화 |

## 6. 자동 시작 확인

Windows:

- [ ] 설치할 때 `-RegisterTask`를 붙였다.
- [ ] 작업 스케줄러에서 `AgentRouterKit`이 보인다.
- [ ] 로그온 후 라우터가 자동 실행된다.

macOS:

- [ ] 설치할 때 `--register-launchd`를 붙였다.
- [ ] `~/Library/LaunchAgents/com.agent-router-kit.slack-agent-router.plist`가 있다.
- [ ] 재로그인 후 라우터가 자동 실행된다.

## 7. 선택 모듈 확인

SMS:

- [ ] 설치 시 `-EnableSms` 또는 `--enable-sms`를 사용했다.
- [ ] `WORKSPACE_ROOT/scripts/sms_receiver.py`가 있다.
- [ ] Android Tasker 또는 iPhone Shortcuts에서 로컬 receiver로 보낸다.
- [ ] `inputs/sms`, `processed/tasks`, `ledger/sms`에 파일이 생긴다.

Kakao:

- [ ] 설치 시 `-EnableKakao` 또는 `--enable-kakao`를 사용했다.
- [ ] `WORKSPACE_ROOT/scripts/kakao_self_ingest.py`가 있다.
- [ ] Windows PC Kakao 쪽 reader가 준비되어 있다.
- [ ] `inputs/kakao`, `processed/tasks`, `ledger/kakao`에 파일이 생긴다.

## 8. 문제 해결

| 증상 | 확인 위치 | 해결 행동 |
|---|---|---|
| Slack 응답 없음 | 라우터 터미널 | 실행 중인지, Socket Mode 연결 로그가 있는지 확인 |
| 토큰 오류 | env 파일 | `xapp-`와 `xoxb-` 위치를 다시 확인 |
| 채널 이벤트가 안 옴 | Slack 채널 | 봇을 해당 채널에 초대 |
| 권한 오류 | Slack OAuth scopes | 스코프 추가 후 앱을 다시 설치 |
| Codex 실행 실패 | 라우터 로그 | `CODEX_EXE`를 터미널에서 직접 실행 |
| Claude Code 실행 실패 | 라우터 로그 | `CLAUDE_EXE`를 터미널에서 직접 실행 |
| 업무 명령이 토론으로 감 | Slack 입력 | `리셋 토론` 후 `업무 할일 ...`처럼 다시 입력 |
| 선택 모듈 파일 없음 | `WORKSPACE_ROOT/scripts` | 설치 스크립트를 `-EnableSms` 또는 `-EnableKakao`로 다시 실행 |
