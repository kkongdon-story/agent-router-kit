param(
    [string]$InstallRoot = "$env:USERPROFILE\.agent-router-kit",
    [string]$WorkspaceRoot = "$env:USERPROFILE\agent-router-workspace",
    [string]$ProjectRoot = "$env:USERPROFILE\agent-router-projects",
    [string]$PythonExe = "python",
    [switch]$RegisterTask,
    [switch]$EnableWorkspace,
    [switch]$EnableSms,
    [switch]$EnableKakao,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$RouterSource = Join-Path $RepoRoot "templates\slack-agent-router"
$InputSource = Join-Path $RepoRoot "templates\workspace-inputs"
$RouterHome = Join-Path $InstallRoot "slack-agent-router"
$SecretsDir = Join-Path $InstallRoot "secrets"
$EnvFile = Join-Path $SecretsDir "slack-agent-router.env"
$RunFile = Join-Path $RouterHome "run.ps1"
$VenvDir = Join-Path $RouterHome "venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$TaskName = "AgentRouterKit"

function Say($Message) {
    Write-Host "[agent-router-kit] $Message"
}

function Do-Step($Message, [scriptblock]$Action) {
    Say $Message
    if (-not $DryRun) {
        & $Action
    }
}

Do-Step "Create install folders" {
    New-Item -ItemType Directory -Force -Path $RouterHome, $SecretsDir, $WorkspaceRoot, $ProjectRoot | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $RouterHome "logs"), (Join-Path $RouterHome "runs"), (Join-Path $RouterHome "sessions"), (Join-Path $RouterHome "state") | Out-Null
}

Do-Step "Copy Slack router template" {
    Copy-Item -LiteralPath (Join-Path $RouterSource "daemon.py") -Destination (Join-Path $RouterHome "daemon.py") -Force
    Copy-Item -LiteralPath (Join-Path $RouterSource "README.md") -Destination (Join-Path $RouterHome "README.md") -Force
}

if ($EnableSms -or $EnableKakao) {
    $EnableWorkspace = $true
}

if ($EnableWorkspace) {
    Do-Step "Create local workspace and copy optional SMS/Kakao scripts" {
        $workspaceDirs = @(
            "inputs\slack",
            "inputs\sms",
            "inputs\kakao",
            "inputs\folder",
            "processed\tasks",
            "processed\memos",
            "processed\finance",
            "processed\schedules",
            "processed\content",
            "processed\questions",
            "processed\noise",
            "ledger\sms",
            "ledger\kakao",
            "ledger\logs",
            "system\slack",
            "scripts"
        )
        foreach ($dir in $workspaceDirs) {
            New-Item -ItemType Directory -Force -Path (Join-Path $WorkspaceRoot $dir) | Out-Null
        }
        Copy-Item -Path (Join-Path $InputSource "*.py") -Destination (Join-Path $WorkspaceRoot "scripts") -Force
    }
}

Do-Step "Create Python virtual environment and install dependencies" {
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        & $PythonExe -m venv $VenvDir
    }
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r (Join-Path $RepoRoot "requirements.txt")
}

Do-Step "Create env file if missing" {
    if (-not (Test-Path -LiteralPath $EnvFile)) {
        $envTemplate = Get-Content -Raw -LiteralPath (Join-Path $RouterSource "slack-agent-router.env.example")
        $envContent = $envTemplate.Replace("{USER_HOME}", $env:USERPROFILE).Replace("/", "\")
        $envContent = $envContent -replace "WORKSPACE_ROOT=.*", "WORKSPACE_ROOT=$WorkspaceRoot"
        $envContent = $envContent -replace "AGENT_WORKDIR=.*", "AGENT_WORKDIR=$WorkspaceRoot"
        $envContent = $envContent -replace "PROJECT_ROOT=.*", "PROJECT_ROOT=$ProjectRoot"
        $envContent = $envContent -replace "ENABLE_WORKSPACE=.*", "ENABLE_WORKSPACE=$([int][bool]$EnableWorkspace)"
        $envContent = $envContent -replace "ENABLE_SMS=.*", "ENABLE_SMS=$([int][bool]$EnableSms)"
        $envContent = $envContent -replace "ENABLE_KAKAO=.*", "ENABLE_KAKAO=$([int][bool]$EnableKakao)"
        Set-Content -LiteralPath $EnvFile -Value $envContent -Encoding UTF8
    }
}

Do-Step "Create run.ps1" {
    $template = Get-Content -Raw -LiteralPath (Join-Path $RouterSource "run.ps1.tmpl")
    $content = $template.Replace("{ENV_FILE}", $EnvFile).Replace("{AGENT_ROUTER_HOME}", $RouterHome).Replace("{PYTHON_EXE}", $VenvPython).Replace("{DAEMON_PY}", (Join-Path $RouterHome "daemon.py"))
    Set-Content -LiteralPath $RunFile -Value $content -Encoding UTF8
}

Do-Step "Lock down local secrets ACL" {
    $Icacls = "C:\Windows\System32\icacls.exe"
    & $Icacls $SecretsDir /inheritance:r /grant:r "$($env:USERNAME):(OI)(CI)F" | Out-Null
    & $Icacls $EnvFile /inheritance:r /grant:r "$($env:USERNAME):F" | Out-Null
}

if ($RegisterTask) {
    Do-Step "Register Windows Scheduled Task" {
        $Pwsh = "C:\Program Files\PowerShell\7\pwsh.exe"
        if (-not (Test-Path -LiteralPath $Pwsh)) {
            $Pwsh = "powershell.exe"
        }
        $Action = New-ScheduledTaskAction -Execute $Pwsh -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$RunFile`""
        $Trigger = New-ScheduledTaskTrigger -AtLogOn
        $Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
        $Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
        Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null
    }
}

[pscustomobject]@{
    InstalledTo = $InstallRoot
    RouterHome = $RouterHome
    EnvFile = $EnvFile
    RunFile = $RunFile
    WorkspaceRoot = $WorkspaceRoot
    ProjectRoot = $ProjectRoot
    WorkspaceEnabled = [bool]$EnableWorkspace
    SmsEnabled = [bool]$EnableSms
    KakaoEnabled = [bool]$EnableKakao
    TaskRegistered = [bool]$RegisterTask
    DryRun = [bool]$DryRun
}
