# ==============================================================================
# MeshCore Bridge - Installation and Launch for Windows PowerShell
# Version: 3.0.0 (Production)
# Architecture: CPython >= 3.14.8 | FastAPI ASGI | LoRa MeshCore Companion
# ==============================================================================

<#
.SYNOPSIS
Set up MeshCore Bridge in a local Python virtual environment.
.DESCRIPTION
Requires stable CPython 3.14.8 or newer. Creates or reuses .venv, installs
production dependencies when missing, and preserves an existing .env.
Windows setup does not install a service or an MQTT broker. NO_COLOR disables
terminal colors; redirected output uses plain text.
.PARAMETER Run
Start the bridge after setup using the local virtual environment.
.PARAMETER InstallDeps
Reinstall production dependencies from requirements.txt.
.PARAMETER InstallDev
Install development tools and Chromium. This does not run test suites.
.PARAMETER Simulate
Launch the isolated interactive virtual mesh demo after setup.
.EXAMPLE
.\install.ps1
.EXAMPLE
.\install.ps1 -Run
.EXAMPLE
.\install.ps1 -InstallDev
#>
[CmdletBinding()]
param (
    [switch]$Run,
    [switch]$InstallDeps,
    [switch]$InstallDev,
    [switch]$Simulate
)

$ErrorActionPreference = "Stop"
$UseColor = -not [Console]::IsOutputRedirected -and
    $null -eq [Environment]::GetEnvironmentVariable('NO_COLOR') -and
    $env:TERM -ne 'dumb'

function Write-Terminal {
    param(
        [string]$Message = '',
        [ConsoleColor]$ForegroundColor = [ConsoleColor]::Gray,
        [switch]$NoNewline
    )
    if ($UseColor) {
        Write-Host $Message -ForegroundColor $ForegroundColor -NoNewline:$NoNewline
    } else {
        Write-Host $Message -NoNewline:$NoNewline
    }
}

# Terminal presentation helpers
function Write-Step {
    param([string]$Step, [string]$Title)
    Write-Terminal ""
    Write-Terminal "$Step  " -ForegroundColor Cyan -NoNewline
    Write-Terminal "$Title" -ForegroundColor White
}

function Write-Success {
    param([string]$Message)
    Write-Terminal "  OK    " -ForegroundColor Green -NoNewline
    Write-Terminal "$Message" -ForegroundColor Gray
}

function Write-Info {
    param([string]$Message)
    Write-Terminal "  INFO  " -ForegroundColor Cyan -NoNewline
    Write-Terminal "$Message" -ForegroundColor Gray
}

function Write-Warn {
    param([string]$Message)
    Write-Terminal "  WARN  " -ForegroundColor Yellow -NoNewline
    Write-Terminal "$Message" -ForegroundColor Yellow
}

function Write-Fail {
    param([string]$Message)
    Write-Terminal "  ERROR " -ForegroundColor Red -NoNewline
    Write-Terminal "$Message" -ForegroundColor Red
}

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory=$true)][scriptblock]$Command,
        [Parameter(Mandatory=$true)][string]$ErrorMessage
    )
    $prevEAP = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $Command
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "$ErrorMessage (exit code: $LASTEXITCODE)"
            exit $LASTEXITCODE
        }
    } finally {
        $ErrorActionPreference = $prevEAP
    }
}

function Test-RuntimeDependencies {
    param([string]$PythonPath, [string]$ScriptDir)
    $prevEAP = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $null = & $PythonPath "$ScriptDir\scripts\check_runtime_dependencies.py" --profile web 2>&1
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $prevEAP
    }
}

function Test-PythonRuntime {
    param([string]$PythonPath)
    if (-not (Test-Path -LiteralPath $PythonPath)) { return $false }
    $prevEAP = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $PythonPath -c "import sys, venv, ensurepip; raise SystemExit(0 if sys.implementation.name == 'cpython' and sys.version_info[:3] >= (3, 14, 8) and sys.version_info.releaselevel == 'final' else 1)" 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $prevEAP
    }
}

function Get-PythonVersionString {
    param([string]$PythonPath)
    $vOutput = & $PythonPath --version 2>&1
    if ($vOutput) {
        return ($vOutput -replace '^Python\s*', '').Trim()
    }
    return "unknown"
}

function Find-PythonRuntime {
    if ($env:MESHCORE_PYTHON) {
        if (-not (Test-PythonRuntime -PythonPath $env:MESHCORE_PYTHON)) {
            throw "MESHCORE_PYTHON ($env:MESHCORE_PYTHON) is unsupported. Stable CPython >= 3.14.8 with venv/ensurepip is required."
        }
        return $env:MESHCORE_PYTHON
    }

    $Candidates = @()
    foreach ($Name in @('python3.15', 'python3.14', 'python3', 'python')) {
        $Command = Get-Command $Name -ErrorAction SilentlyContinue
        if ($Command) { $Candidates += $Command.Source }
    }

    $Launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($Launcher) {
        $Installed = & $Launcher.Source -0p 2>$null
        if ($LASTEXITCODE -eq 0) {
            foreach ($Line in $Installed) {
                if ($Line -match '^\s*-(?:V:)?(3\.\d+)(?:-\d+)?\s+\*?\s*(.+?)\s*$') {
                    $Candidates += $Matches[2]
                }
            }
        }
    }

    foreach ($Candidate in $Candidates) {
        if (Test-PythonRuntime -PythonPath $Candidate) { return $Candidate }
    }

    throw "No supported stable CPython >= 3.14.8 was found. Install it from https://python.org or set MESHCORE_PYTHON to its executable path."
}

# ==============================================================================
# Welcome
# ==============================================================================
Write-Terminal ""
Write-Terminal "MeshCore Bridge  3.0 | Windows setup" -ForegroundColor Cyan
Write-Terminal "  LoRa Companion / MQTT / Web Station" -ForegroundColor DarkGray
Write-Terminal "  Mode: $(if ($Simulate) { 'setup + virtual demo' } elseif ($Run) { 'setup + launch' } elseif ($InstallDev) { 'development setup' } else { 'setup' })"

$ScriptDir = [System.IO.Path]::GetFullPath((Split-Path -Parent $MyInvocation.MyCommand.Path))

# 1. Check or create the Python environment
Write-Step "1/5" "Check Python runtime and virtual environment"

$VenvPython = "$ScriptDir\.venv\Scripts\python.exe"
$NeedNewVenv = $true
$SystemPython = $null

if (Test-Path $VenvPython) {
    if (Test-PythonRuntime -PythonPath $VenvPython) {
        $PythonPath = $VenvPython
        $vStr = Get-PythonVersionString -PythonPath $PythonPath
        Write-Success "Existing environment: Python $vStr ($PythonPath)"
        $NeedNewVenv = $false
    } else {
        Write-Warn "The existing .venv requires stable CPython >= 3.14.8. Recreating it."
        # Locate a supported replacement before removing the old environment.
        $SystemPython = Find-PythonRuntime
        $VenvDirectory = [System.IO.Path]::GetFullPath((Join-Path $ScriptDir '.venv'))
        if ([System.IO.Path]::GetDirectoryName($VenvDirectory) -ne $ScriptDir -or
            [System.IO.Path]::GetFileName($VenvDirectory) -ne '.venv') {
            throw "Virtual environment path is outside the project: $VenvDirectory"
        }
        $VenvItem = Get-Item -LiteralPath $VenvDirectory -Force
        if ($VenvItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            throw "Refusing to remove a linked virtual environment: $VenvDirectory"
        }
        Remove-Item -LiteralPath $VenvDirectory -Recurse -Force
    }
}

if ($NeedNewVenv) {
    Write-Info "Find stable CPython >= 3.14.8"
    if (-not $SystemPython) { $SystemPython = Find-PythonRuntime }
    $sysVer = Get-PythonVersionString -PythonPath $SystemPython
    Write-Success "Base runtime: Python $sysVer ($SystemPython)"

    Write-Info "Create isolated environment in $ScriptDir\.venv"
    Invoke-NativeCommand { & $SystemPython -m venv "$ScriptDir\.venv" } "Could not create the virtual environment."
    $PythonPath = $VenvPython
    Write-Success "Virtual environment created."
}

# 2. Install production dependencies
Write-Step "2/5" "Check production dependencies"

$DepsValid = Test-RuntimeDependencies -PythonPath $PythonPath -ScriptDir $ScriptDir

if ($InstallDeps -or -not $DepsValid) {
    Write-Info "Update pip and packaging tools"
    Invoke-NativeCommand { & $PythonPath -m pip install --upgrade pip setuptools wheel -q } "Could not update pip and packaging tools."

    Write-Info "Install packages from requirements.txt"
    Write-Info "MeshCore SDK, MQTT, serial access and the FastAPI/Uvicorn web stack"

    Invoke-NativeCommand { & $PythonPath -m pip install -r "$ScriptDir\requirements.txt" } "Could not install requirements.txt."

    Write-Info "Verify dependency imports and versions for the web profile"
    Invoke-NativeCommand { & $PythonPath "$ScriptDir\scripts\check_runtime_dependencies.py" --profile web } "Dependencies are missing or incompatible after installation."
    Write-Success "Production dependencies installed; imports and versions verified."
} else {
    Write-Success "Production dependencies are already available; imports and versions verified."
}

# 3. Optional development and quality tools
if ($InstallDev) {
    Write-Step "3/5" "Install development tools"
    Invoke-NativeCommand { & $PythonPath -m pip install -r "$ScriptDir\requirements-dev.txt" -q } "Could not install requirements-dev.txt."
    Invoke-NativeCommand { & $PythonPath -m pip install -e "$ScriptDir" -q } "Could not install the package in editable mode."
    $PlaywrightExe = "$ScriptDir\.venv\Scripts\playwright.exe"
    if (Test-Path $PlaywrightExe) {
        Write-Info "Install Chromium for Playwright"
        Invoke-NativeCommand { & $PlaywrightExe install chromium } "Could not install Chromium for Playwright."
    }
    Write-Success "Development tools installed. No test suites have been run."
} else {
    Write-Step "3/5" "Skip development tools (enable with -InstallDev)"
}

# 4. Detect connected serial devices
Write-Step "4/5" "Detect USB serial devices"

$DetectedPorts = @()
try {
    $Ports = [System.IO.Ports.SerialPort]::GetPortNames()
    if ($Ports -and $Ports.Count -gt 0) {
        $DetectedPorts = $Ports | Sort-Object -Unique
    }
} catch {}

if ($DetectedPorts.Count -gt 0) {
    Write-Success "Available COM ports: $($DetectedPorts -join ', ')"
    $DefaultPort = $DetectedPorts[0]
} else {
    Write-Warn "No connected serial device detected. Using AUTO discovery."
    $DefaultPort = "AUTO"
}

# 5. Create configuration if missing
Write-Step "5/5" "Check local configuration"

$ConfigCreated = $false
if (-not (Test-Path "$ScriptDir\.env")) {
    if (Test-Path "$ScriptDir\.env.example") {
        Copy-Item "$ScriptDir\.env.example" "$ScriptDir\.env" -Force
        if ($DefaultPort -ne "AUTO") {
            (Get-Content "$ScriptDir\.env") -replace '^SERIAL_PORT=.*', "SERIAL_PORT=$DefaultPort" | Set-Content "$ScriptDir\.env"
        }
        $ConfigCreated = $true
        Write-Success "Created .env from .env.example (SERIAL_PORT=$DefaultPort)."
    } else {
        Write-Warn "No .env.example found; create your configuration before launch."
    }
} else {
    Write-Success "Existing .env preserved."
}

# ==============================================================================
# Setup summary and launch commands
# ==============================================================================
Write-Terminal ""
Write-Terminal "Local environment ready" -ForegroundColor Green
Write-Terminal "------------------------------------------------------------" -ForegroundColor DarkGray
Write-Terminal "  Project       $ScriptDir"
Write-Terminal "  Python        $PythonPath"
Write-Terminal "  Configuration $(if (Test-Path -LiteralPath "$ScriptDir\.env") { "$ScriptDir\.env" } else { 'Missing; create .env before launch' })"
Write-Terminal "  Web default   http://localhost:8080 (after launch; see .env)"
Write-Terminal "  MQTT          Configure an existing broker in .env"
Write-Terminal "  Serial port   $(if ($ConfigCreated) { $DefaultPort } elseif (Test-Path -LiteralPath "$ScriptDir\.env") { 'Existing .env setting preserved' } else { 'Configure SERIAL_PORT in .env' })"
Write-Terminal ""
Write-Terminal "Next steps" -ForegroundColor Cyan
Write-Terminal "  Review     Edit .env for your radio, MQTT broker and web access"
Write-Terminal "  Start      .\install.ps1 -Run"
Write-Terminal "  Demo       .\install.ps1 -Simulate"
Write-Terminal "  Refresh    .\install.ps1 -InstallDeps"
Write-Terminal "  Develop    .\install.ps1 -InstallDev"
Write-Terminal ""

Push-Location $ScriptDir
try {
    if ($Simulate) {
        Write-Terminal "Start the interactive virtual mesh demo" -ForegroundColor Cyan
        Invoke-NativeCommand { & $PythonPath "$ScriptDir\run_interactive_demo.py" } "The virtual mesh demo exited with an error."
    } elseif ($Run) {
        Write-Terminal "Start MeshCore Bridge" -ForegroundColor Cyan
        Invoke-NativeCommand { & $PythonPath -m src } "MeshCore Bridge exited with an error."
    }
} finally {
    Pop-Location
}
