# INSTALL_WITH_AI

아래 내용을 Claude Code 또는 Codex에게 그대로 보여주세요.

```text
이 repo는 agent-router-kit입니다.
이 파일과 SKILL.md를 읽고, 내 컴퓨터에 Slack Agent Router를 설치해 주세요.

원칙:
- 토큰은 절대 채팅창에 붙여넣지 않게 안내하세요.
- 실제 토큰은 로컬 secrets env 파일에만 입력하게 해 주세요.
- 설치 전 DryRun을 먼저 실행해 주세요.
- 내 OS가 Windows인지 macOS인지 확인하고 해당 스크립트를 사용해 주세요.
- 기본 설치는 Slack Router + local workspace입니다.
- SMS/Kakao는 선택 모듈로, 내가 명시적으로 원할 때만 켜 주세요.

최종 확인:
- Slack에서 "코덱스 안녕" 테스트
- Slack에서 "클로드 안녕" 테스트
- Slack에서 "둘이 토론해" 테스트
- "slack agent router app으로 뭐 할 수 있어?" 질문이 generic Slack 기능이 아니라 agent-router-kit 기능으로 답하는지 확인
```

## 사용자가 직접 해야 하는 일

1. Slack App을 생성합니다.
2. Socket Mode를 켭니다.
3. Bot Token Scopes와 App-Level Token을 설정합니다.
4. Bot을 테스트 채널에 초대합니다.
5. 생성된 토큰과 채널 ID, 사용자 ID를 로컬 env 파일에 직접 입력합니다.

AI에게 토큰 값을 보내지 마세요.

## AI가 처리해야 하는 일

1. `SKILL.md`를 읽고 설치 절차를 따른다.
2. `scripts/install-windows.ps1 -DryRun` 또는 `scripts/install-macos.sh --dry-run`을 먼저 실행한다.
3. 실제 설치를 실행한다.
4. env 파일 위치를 알려주고, 사용자가 직접 값을 넣도록 안내한다.
5. 라우터를 실행하고 로그를 확인한다.
6. Slack 테스트 메시지로 동작을 검증한다.

## 추천 기본값

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1 -EnableWorkspace
```

macOS:

```bash
bash ./scripts/install-macos.sh --enable-workspace
```

자동 시작까지 원하면 Windows는 `-RegisterTask`, macOS는 `--register-launchd`를 추가합니다.
