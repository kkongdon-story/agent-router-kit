param(
    [string]$PythonExe = "python",
    [switch]$SkipRealInstall
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$TempRoot = Join-Path $env:TEMP "agent-router-kit-release-verify"
$TempInstall = Join-Path $TempRoot "install"
$TempWorkspace = Join-Path $TempRoot "workspace"
$TempProjects = Join-Path $TempRoot "projects"

function Say($Message) {
    Write-Host "[verify-release] $Message"
}

function Invoke-Checked($Label, [scriptblock]$Action) {
    Say $Label
    & $Action
}

function Remove-SafeTemp($Path) {
    if (-not $Path) {
        return
    }
    $full = [System.IO.Path]::GetFullPath($Path)
    $temp = [System.IO.Path]::GetFullPath($env:TEMP)
    if (-not $full.StartsWith($temp, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove non-temp path: $full"
    }
    if ((Split-Path -Leaf $full) -notlike "agent-router-kit-*") {
        throw "Refusing to remove unexpected temp folder: $full"
    }
    if (Test-Path -LiteralPath $full) {
        Remove-Item -LiteralPath $full -Recurse -Force
    }
}

Push-Location $RepoRoot
try {
    Invoke-Checked "Python version" {
        & $PythonExe --version
    }

    Invoke-Checked "Public safety, docs, and workspace input tests" {
        & $PythonExe -m unittest `
            tests.test_public_safety `
            tests.test_docs_consistency `
            tests.test_workspace_inputs
    }

    Invoke-Checked "Python syntax check" {
        $compileTargets = @(
            "templates\slack-agent-router\daemon.py",
            "templates\workspace-inputs\sms_ingest.py",
            "templates\workspace-inputs\sms_receiver.py",
            "templates\workspace-inputs\kakao_self_ingest.py"
        )
        & $PythonExe -m py_compile @compileTargets
    }

    Invoke-Checked "Windows installer dry run" {
        & (Join-Path $RepoRoot "scripts\install-windows.ps1") `
            -DryRun `
            -EnableWorkspace `
            -EnableSms `
            -EnableKakao `
            -InstallRoot $TempInstall `
            -WorkspaceRoot $TempWorkspace `
            -ProjectRoot $TempProjects `
            -PythonExe $PythonExe
    }

    if (-not $SkipRealInstall) {
        Invoke-Checked "Clean previous temp install" {
            Remove-SafeTemp $TempRoot
        }

        Invoke-Checked "Windows temp real install" {
            & (Join-Path $RepoRoot "scripts\install-windows.ps1") `
                -EnableWorkspace `
                -EnableSms `
                -EnableKakao `
                -InstallRoot $TempInstall `
                -WorkspaceRoot $TempWorkspace `
                -ProjectRoot $TempProjects `
                -PythonExe $PythonExe
        }

        Invoke-Checked "Installed artifact check" {
            $required = @(
                (Join-Path $TempInstall "slack-agent-router\daemon.py"),
                (Join-Path $TempInstall "slack-agent-router\run.ps1"),
                (Join-Path $TempInstall "secrets\slack-agent-router.env"),
                (Join-Path $TempWorkspace "scripts\sms_ingest.py"),
                (Join-Path $TempWorkspace "scripts\kakao_self_ingest.py")
            )
            foreach ($path in $required) {
                if (-not (Test-Path -LiteralPath $path)) {
                    throw "Missing installed artifact: $path"
                }
            }
        }

        Invoke-Checked "Router intent tests with installed venv" {
            $venvPython = Join-Path $TempInstall "slack-agent-router\venv\Scripts\python.exe"
            & $venvPython -m unittest tests.test_router_intent
        }
    }

    Invoke-Checked "macOS installer dry run when Git Bash is available" {
        $bash = "C:\Program Files\Git\bin\bash.exe"
        if (Test-Path -LiteralPath $bash) {
            & $bash ./scripts/install-macos.sh --dry-run --enable-workspace --enable-sms --enable-kakao
        } else {
            Say "Git Bash not found; skipped macOS dry-run on this Windows host."
        }
    }

    Say "All release verification steps completed."
}
finally {
    Pop-Location
}
