# Beginner Tutorial

이 문서는 자동화가 처음인 사람이 `agent-router-kit`을 설치하고 첫 테스트까지 가는 순서입니다.

핵심은 간단합니다.

- Slack은 명령을 보내는 리모컨입니다.
- Slack Agent Router는 어느 도우미에게 보낼지 정하는 교통정리 담당입니다.
- Claude Code와 Codex는 실제 일을 처리하는 두 도우미입니다.
- local workspace는 결과와 입력을 적어두는 로컬 공책입니다.
- SMS와 Kakao는 Slack 말고도 들어올 수 있는 다른 입구입니다.

## 1. 설치 전 준비

필요한 것은 네 가지입니다.

| 준비물 | 왜 필요한가 |
|---|---|
| Python 3 | 라우터를 실행합니다. |
| Slack workspace | 명령을 보낼 공간입니다. |
| Claude Code 또는 Codex CLI | 실제 작업을 처리할 도우미입니다. |
| 이 repo | 설치 스크립트와 템플릿이 들어 있습니다. |

처음에는 선택 모듈을 모두 켜지 말고 `Slack router + local workspace`만 설치하세요. SMS와 Kakao는 기본 동작을 확인한 뒤 붙이는 편이 안전합니다.

## 2. repo 받기

Git을 아는 사용자는 clone 합니다.

```powershell
git clone https://github.com/YOUR_NAME/agent-router-kit.git
cd agent-router-kit
```

Git이 익숙하지 않으면 GitHub 페이지에서 ZIP으로 내려받고 압축을 풉니다.

## 3. AI에게 설치를 맡기기

Claude Code 또는 Codex에 아래처럼 말합니다.

```text
이 폴더의 INSTALL_WITH_AI.md와 SKILL.md를 읽고 agent-router-kit 설치를 도와줘.
토큰은 내가 로컬 env 파일에 직접 넣을 테니 채팅창에는 절대 붙여넣지 않게 안내해줘.
먼저 DryRun으로 확인하고, 그다음 Slack router + local workspace 기준으로 설치해줘.
```

AI가 해야 할 일은 설치 스크립트를 실행하고, env 파일 위치를 알려주고, 실행 방법을 안내하는 것입니다.

## 4. Windows 설치

먼저 DryRun으로 확인합니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1 -DryRun -EnableWorkspace
```

문제가 없으면 실제 설치를 실행합니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1 -EnableWorkspace
```

자동 시작까지 원하면 다음처럼 실행합니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1 -EnableWorkspace -RegisterTask
```

설치 후 중요한 위치는 다음입니다.

| 항목 | 기본 위치 |
|---|---|
| env 파일 | `%USERPROFILE%\.agent-router-kit\secrets\slack-agent-router.env` |
| 실행 파일 | `%USERPROFILE%\.agent-router-kit\slack-agent-router\run.ps1` |
| local workspace | `%USERPROFILE%\agent-router-workspace` |

## 5. macOS 설치

먼저 DryRun으로 확인합니다.

```bash
bash ./scripts/install-macos.sh --dry-run --enable-workspace
```

문제가 없으면 실제 설치를 실행합니다.

```bash
bash ./scripts/install-macos.sh --enable-workspace
```

로그인할 때 자동 실행하려면 다음처럼 실행합니다.

```bash
bash ./scripts/install-macos.sh --enable-workspace --register-launchd
```

## 6. Slack App 만들기

Slack에서 직접 해야 하는 단계입니다. 토큰은 AI 채팅창에 붙여넣지 않습니다.

1. Slack API 페이지에서 새 앱을 만듭니다.
2. Socket Mode를 켭니다.
3. App-Level Token을 만들고 `connections:write` 권한을 줍니다.
4. Bot Token Scopes를 추가합니다.
5. 앱을 workspace에 설치합니다.
6. 봇을 테스트용 비공개 채널에 초대합니다.
7. 채널 ID, 내 사용자 ID, 토큰을 로컬 env 파일에 직접 입력합니다.

필수 스코프는 다음입니다.

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

## 7. env 파일 입력

env 파일에는 다음 값이 필요합니다.

```env
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
SLACK_CHANNEL=C0XXXXXXXXX
USER_SLACK_ID=U0XXXXXXXXX
DEFAULT_AGENT=codex
```

호출명은 바꿀 수 있습니다.

```env
CLAUDE_DISPLAY_NAME=클로드
CODEX_DISPLAY_NAME=코덱스
CLAUDE_ALIASES=클로드,claude,클로
CODEX_ALIASES=코덱스,codex,덱스
```

`덱스`, `클로`는 공식 이름이 아니라 짧은 별칭 예시입니다. 원하는 이름으로 바꿔도 됩니다.

## 8. 라우터 실행

Windows:

```powershell
& "$env:USERPROFILE\.agent-router-kit\slack-agent-router\run.ps1"
```

macOS:

```bash
~/.agent-router-kit/slack-agent-router/run.sh
```

터미널에 Socket Mode 연결 로그가 나오면 Slack에서 테스트합니다.

## 9. 첫 테스트

Slack 테스트 채널에서 순서대로 보냅니다.

```text
코덱스 안녕
클로드 안녕
둘 다 한 문장으로 인사해
둘이 토론해
업무 할일 테스트 작업 추가
slack agent router app으로 뭐 할 수 있어?
```

기대 동작은 다음입니다.

| 입력 | 기대 결과 |
|---|---|
| `코덱스 안녕` | Codex가 답합니다. |
| `클로드 안녕` | Claude Code가 답합니다. |
| `둘 다 ...` | 두 도우미가 각각 답합니다. |
| `둘이 토론해` | Debate Mode가 시작됩니다. |
| `업무 할일 ...` | local workspace 작업으로 처리됩니다. |
| capability 질문 | generic Slack 기능이 아니라 agent-router-kit 기능을 설명합니다. |

## 10. 자동 시작

Windows는 설치할 때 `-RegisterTask`를 붙이면 작업 스케줄러에 등록됩니다.

macOS는 `--register-launchd`를 붙이면 LaunchAgent에 등록됩니다.

자동 시작은 편하지만, 처음 하루는 수동 실행으로 로그를 확인해 보는 것을 추천합니다.

## 11. 선택 모듈

SMS와 Kakao는 기본 설치 뒤에 붙입니다.

| 모듈 | 언제 켜나 |
|---|---|
| SMS | 카드 사용, 입금, 문의, 인증 같은 휴대폰 문자를 local workspace에 모으고 싶을 때 |
| Kakao | Windows PC Kakao에서 의도적으로 연 대화방을 local workspace 입력으로 모으고 싶을 때 |

SMS는 Android Tasker 또는 iPhone Shortcuts가 필요합니다. Kakao는 v1에서 Windows PC Kakao 중심입니다.

## 12. 안전 습관

- 토큰은 AI 채팅창에 붙여넣지 않습니다.
- 토큰은 GitHub에 올리지 않습니다.
- 처음에는 비공개 테스트 채널에서만 씁니다.
- local workspace에는 민감한 내용이 들어올 수 있으니 백업과 공유 범위를 확인합니다.
- SMS/Kakao는 필요한 입력만 켭니다.
