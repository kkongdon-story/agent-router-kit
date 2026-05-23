#!/usr/bin/env bash
set -euo pipefail

INSTALL_ROOT="$HOME/.agent-router-kit"
WORKSPACE_ROOT="$HOME/agent-router-workspace"
PROJECT_ROOT="$HOME/agent-router-projects"
PYTHON_EXE="python3"
REGISTER_LAUNCHD=0
ENABLE_KMS=0
ENABLE_SMS=0
ENABLE_KAKAO=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-root) INSTALL_ROOT="$2"; shift 2 ;;
    --workspace-root) WORKSPACE_ROOT="$2"; shift 2 ;;
    --project-root) PROJECT_ROOT="$2"; shift 2 ;;
    --python) PYTHON_EXE="$2"; shift 2 ;;
    --register-launchd) REGISTER_LAUNCHD=1; shift ;;
    --enable-kms) ENABLE_KMS=1; shift ;;
    --enable-sms) ENABLE_SMS=1; ENABLE_KMS=1; shift ;;
    --enable-kakao) ENABLE_KAKAO=1; ENABLE_KMS=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ROUTER_SOURCE="$REPO_ROOT/templates/slack-agent-router"
KMS_SOURCE="$REPO_ROOT/templates/kms"
ROUTER_HOME="$INSTALL_ROOT/slack-agent-router"
SECRETS_DIR="$INSTALL_ROOT/secrets"
ENV_FILE="$SECRETS_DIR/slack-agent-router.env"
RUN_FILE="$ROUTER_HOME/run.sh"
VENV_DIR="$ROUTER_HOME/venv"
VENV_PYTHON="$VENV_DIR/bin/python"
PLIST="$HOME/Library/LaunchAgents/com.agent-router-kit.slack-agent-router.plist"

say() { printf '[agent-router-kit] %s\n' "$*"; }
run() {
  say "$1"
  shift
  if [[ "$DRY_RUN" -eq 0 ]]; then
    "$@"
  fi
}

run "Create install folders" mkdir -p "$ROUTER_HOME/logs" "$ROUTER_HOME/runs" "$ROUTER_HOME/sessions" "$ROUTER_HOME/state" "$SECRETS_DIR" "$WORKSPACE_ROOT" "$PROJECT_ROOT"
run "Copy Slack router template" cp "$ROUTER_SOURCE/daemon.py" "$ROUTER_SOURCE/README.md" "$ROUTER_HOME/"

if [[ "$ENABLE_KMS" -eq 1 ]]; then
  say "Create KMS workspace and copy optional SMS/Kakao scripts"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    mkdir -p "$WORKSPACE_ROOT"/workspace/kms/inputs/{slack,sms,kakao,folder}
    mkdir -p "$WORKSPACE_ROOT"/workspace/kms/processed/{tasks,memos,finance,schedules,content,questions,noise}
    mkdir -p "$WORKSPACE_ROOT"/workspace/kms/ledger/{sms,kakao,logs}
    mkdir -p "$WORKSPACE_ROOT/scripts"
    cp "$KMS_SOURCE"/*.py "$WORKSPACE_ROOT/scripts/"
  fi
fi

if [[ "$ENABLE_KAKAO" -eq 1 ]]; then
  say "Kakao input is Windows PC Kakao first in v1. macOS installs the workspace only; see modules/04-kakao-input.md."
fi

say "Create Python virtual environment and install dependencies"
if [[ "$DRY_RUN" -eq 0 ]]; then
  if [[ ! -x "$VENV_PYTHON" ]]; then
    "$PYTHON_EXE" -m venv "$VENV_DIR"
  fi
  "$VENV_PYTHON" -m pip install --upgrade pip
  "$VENV_PYTHON" -m pip install -r "$REPO_ROOT/requirements.txt"
fi

say "Create env file if missing"
if [[ "$DRY_RUN" -eq 0 && ! -f "$ENV_FILE" ]]; then
  sed "s|{USER_HOME}|$HOME|g; s|WORKSPACE_ROOT=.*|WORKSPACE_ROOT=$WORKSPACE_ROOT|; s|AGENT_WORKDIR=.*|AGENT_WORKDIR=$WORKSPACE_ROOT|; s|PROJECT_ROOT=.*|PROJECT_ROOT=$PROJECT_ROOT|; s|ENABLE_KMS=.*|ENABLE_KMS=$ENABLE_KMS|; s|ENABLE_SMS=.*|ENABLE_SMS=$ENABLE_SMS|; s|ENABLE_KAKAO=.*|ENABLE_KAKAO=$ENABLE_KAKAO|" "$ROUTER_SOURCE/slack-agent-router.env.example" > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
fi

say "Create run.sh"
if [[ "$DRY_RUN" -eq 0 ]]; then
  sed "s|{ENV_FILE}|$ENV_FILE|g; s|{AGENT_ROUTER_HOME}|$ROUTER_HOME|g; s|{PYTHON_EXE}|$VENV_PYTHON|g; s|{DAEMON_PY}|$ROUTER_HOME/daemon.py|g" "$ROUTER_SOURCE/run.sh.tmpl" > "$RUN_FILE"
  chmod +x "$RUN_FILE"
fi

if [[ "$REGISTER_LAUNCHD" -eq 1 ]]; then
  say "Register launchd agent"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    mkdir -p "$(dirname "$PLIST")"
    cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.agent-router-kit.slack-agent-router</string>
  <key>ProgramArguments</key>
  <array><string>$RUN_FILE</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$ROUTER_HOME/logs/launchd.out.log</string>
  <key>StandardErrorPath</key><string>$ROUTER_HOME/logs/launchd.err.log</string>
</dict>
</plist>
PLIST
    launchctl unload "$PLIST" >/dev/null 2>&1 || true
    launchctl load "$PLIST"
  fi
fi

cat <<EOF
InstalledTo=$INSTALL_ROOT
RouterHome=$ROUTER_HOME
EnvFile=$ENV_FILE
RunFile=$RUN_FILE
WorkspaceRoot=$WORKSPACE_ROOT
ProjectRoot=$PROJECT_ROOT
KmsEnabled=$ENABLE_KMS
SmsEnabled=$ENABLE_SMS
KakaoEnabled=$ENABLE_KAKAO
LaunchdRegistered=$REGISTER_LAUNCHD
DryRun=$DRY_RUN
EOF
