# ==============================================================================
# MeshCore Bridge - Script de Instalación y Ejecución para Windows PowerShell
# Versión: 3.0.0 (Producción)
# ==============================================================================

[CmdletBinding()]
param (
    [switch]$Run,
    [switch]$InstallDeps,
    [switch]$InstallDev,
    [switch]$Simulate
)

$ErrorActionPreference = "Stop"

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory=$true)][scriptblock]$Command,
        [Parameter(Mandatory=$true)][string]$ErrorMessage
    )
    & $Command
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] $ErrorMessage (Código de salida: $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

function Test-RuntimeDependencies {
    param([string]$PythonPath, [string]$ScriptDir)
    & $PythonPath "$ScriptDir\scripts\check_runtime_dependencies.py" --profile web | Out-Host
    return ($LASTEXITCODE -eq 0)
}

function Test-PythonRuntime {
    param([string]$PythonPath)
    & $PythonPath -c 'import sys, venv, ensurepip; raise SystemExit(0 if sys.version_info >= (3, 14, 8) and sys.version_info.releaselevel == "final" else 1)' 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Find-PythonRuntime {
    if ($env:MESHCORE_PYTHON) {
        if (-not (Test-PythonRuntime -PythonPath $env:MESHCORE_PYTHON)) {
            throw "MESHCORE_PYTHON debe señalar CPython >=3.14.8 estable con venv/ensurepip."
        }
        return $env:MESHCORE_PYTHON
    }
    $Candidates = @()
    foreach ($Name in @('python3.14', 'python')) {
        $Command = Get-Command $Name -ErrorAction SilentlyContinue
        if ($Command) { $Candidates += $Command.Source }
    }
    $Launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($Launcher) {
        # Listing installed interpreters cannot trigger the install manager's
        # automatic download, unlike requesting an absent version with py -3.14.
        $Installed = & $Launcher.Source -0p 2>$null
        if ($LASTEXITCODE -eq 0) {
            foreach ($Line in $Installed) {
                if ($Line -match '^\s*-(?:V:)?3\.14(?:-\d+)?\s+\*?\s*(.+?)\s*$') {
                    $Candidates += $Matches[1]
                }
            }
        }
    }
    foreach ($Candidate in $Candidates) {
        if (Test-PythonRuntime -PythonPath $Candidate) { return $Candidate }
    }
    throw "CPython >=3.14.8 estable no está disponible. Instálalo desde python.org o indica MESHCORE_PYTHON; no se usará un intérprete anterior."
}

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "    🚀 GESTOR DE MESHCORE BRIDGE PARA WINDOWS (v3.0.0)" -ForegroundColor Green
Write-Host "    Heltec / LilyGO / RAKwireless / Seeed / RP2040 <-> MQTT <-> n8n" -ForegroundColor Yellow
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host ""

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# 1. Comprobar / Crear entorno virtual de Python
Write-Host "[1/4] Verificando entorno Python..." -ForegroundColor Blue

$VenvPython = "$ScriptDir\.venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $PythonPath = $VenvPython
    Write-Host "[OK] Entorno virtual existente detectado: $PythonPath" -ForegroundColor Green
} else {
    $SystemPython = Find-PythonRuntime

    Write-Host "[*] Creando entorno virtual aislado en $ScriptDir\.venv..." -ForegroundColor Cyan
    Invoke-NativeCommand { & $SystemPython -m venv "$ScriptDir\.venv" } "Fallo al crear el entorno virtual."
    $PythonPath = $VenvPython
    Write-Host "[OK] Entorno virtual creado: $PythonPath" -ForegroundColor Green
}

if (-not (Test-PythonRuntime -PythonPath $PythonPath)) {
    Write-Host "[ERROR] El entorno requiere CPython >=3.14.8 estable. Conserva sus datos y recrea .venv con el intérprete indicado antes de instalar paquetes." -ForegroundColor Red
    exit 1
}

# 2. Instalar dependencias de producción
if ($InstallDeps -or -not (Test-RuntimeDependencies -PythonPath $PythonPath -ScriptDir $ScriptDir)) {
    Write-Host "[2/4] Instalando / verificando dependencias en requirements.txt..." -ForegroundColor Blue
    Invoke-NativeCommand { & $PythonPath -m pip install -r "$ScriptDir\requirements.txt" -q } "Fallo al instalar requirements.txt."
    Invoke-NativeCommand { & $PythonPath "$ScriptDir\scripts\check_runtime_dependencies.py" --profile web } "Dependencias incompletas o incompatibles tras instalar."
    Write-Host "[OK] Dependencias instaladas correctamente." -ForegroundColor Green
} else {
    Write-Host "[2/4] Dependencias ya disponibles." -ForegroundColor Green
}

# 2.1 Instalar tooling de desarrollo / QA / auditoría
if ($InstallDev) {
    Write-Host "[3/4] Instalando herramientas de desarrollo (pytest, mypy, ruff, bandit, playwright, httpx)..." -ForegroundColor Blue
    Invoke-NativeCommand { & $PythonPath -m pip install -r "$ScriptDir\requirements-dev.txt" -q } "Fallo al instalar requirements-dev.txt."
    Invoke-NativeCommand { & $PythonPath -m pip install -e "$ScriptDir" -q } "Fallo al instalar el paquete en modo editable."
    $PlaywrightExe = "$ScriptDir\.venv\Scripts\playwright.exe"
    if (Test-Path $PlaywrightExe) {
        Invoke-NativeCommand { & $PlaywrightExe install chromium } "Fallo al instalar Chromium para Playwright."
    }
    Write-Host "[OK] Tooling de desarrollo instalado." -ForegroundColor Green
}

# 3. Configurar .env si no existe
if (-not (Test-Path "$ScriptDir\.env")) {
    Write-Host "[4/4] Generando archivo .env por defecto..." -ForegroundColor Blue
    Copy-Item "$ScriptDir\.env.example" "$ScriptDir\.env" -Force
    Write-Host "[OK] Archivo .env generado a partir de .env.example." -ForegroundColor Green
} else {
    Write-Host "[4/4] Archivo .env existente detectado." -ForegroundColor Green
}

Write-Host ""
Write-Host "🎉 Configuración de MeshCore Bridge completada." -ForegroundColor Green
Write-Host "🌐 Producción: puerto configurado; simulación: puerto loopback temporal mostrado al arrancar." -ForegroundColor Green
Write-Host "Para iniciar el servicio en producción:" -ForegroundColor Cyan
Write-Host "    .\install.ps1 -Run" -ForegroundColor Yellow
Write-Host "Para iniciar la simulación con 8 nodos LoRa y Heltec v4 USB:" -ForegroundColor Cyan
Write-Host "    .\install.ps1 -Simulate" -ForegroundColor Yellow
Write-Host ""

Push-Location $ScriptDir
try {
    if ($Simulate) {
        Write-Host "Iniciando simulación interactiva con 8 nodos LoRa..." -ForegroundColor Cyan
        Invoke-NativeCommand { & $PythonPath "$ScriptDir\run_interactive_demo.py" } "La simulación finalizó con error."
    } elseif ($Run) {
        Write-Host "Iniciando MeshCore Bridge en producción..." -ForegroundColor Cyan
        Invoke-NativeCommand { & $PythonPath -m src } "MeshCore Bridge finalizó con error."
    }
} finally {
    Pop-Location
}
