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
    $SystemPython = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $SystemPython) {
        $SystemPython = (Get-Command py -ErrorAction SilentlyContinue).Source
    }

    if (-not $SystemPython) {
        Write-Host "[ERROR] Python no fue encontrado en el PATH. Por favor instala Python 3.10+ desde python.org." -ForegroundColor Red
        exit 1
    }

    Write-Host "[*] Creando entorno virtual aislado en $ScriptDir\.venv..." -ForegroundColor Cyan
    Invoke-NativeCommand { & $SystemPython -m venv "$ScriptDir\.venv" } "Fallo al crear el entorno virtual."
    $PythonPath = $VenvPython
    Write-Host "[OK] Entorno virtual creado: $PythonPath" -ForegroundColor Green
}

# 2. Instalar dependencias de producción
if ($InstallDeps -or -not (Test-Path "$ScriptDir\.venv\Lib\site-packages\paho")) {
    Write-Host "[2/4] Instalando / verificando dependencias en requirements.txt..." -ForegroundColor Blue
    Invoke-NativeCommand { & $PythonPath -m pip install --upgrade pip -q } "Fallo al actualizar pip."
    Invoke-NativeCommand { & $PythonPath -m pip install -r "$ScriptDir\requirements.txt" -q } "Fallo al instalar requirements.txt."
    Write-Host "[OK] Dependencias instaladas correctamente." -ForegroundColor Green
} else {
    Write-Host "[2/4] Dependencias ya disponibles." -ForegroundColor Green
}

# 2.1 Instalar tooling de desarrollo / QA / auditoría
if ($InstallDev) {
    Write-Host "[3/4] Instalando herramientas de desarrollo (pytest, mypy, ruff, bandit, playwright, amqtt)..." -ForegroundColor Blue
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
Write-Host "🌐 Cliente Web Station SPA: http://localhost:8080 (o http://localhost:8085 en simulación)" -ForegroundColor Green
Write-Host "Para iniciar el servicio en producción:" -ForegroundColor Cyan
Write-Host "    .\install.ps1 -Run" -ForegroundColor Yellow
Write-Host "Para iniciar la simulación con 8 nodos LoRa y Heltec v4 USB:" -ForegroundColor Cyan
Write-Host "    .\install.ps1 -Simulate" -ForegroundColor Yellow
Write-Host ""

Push-Location $ScriptDir
try {
    if ($Simulate) {
        Write-Host "Iniciando simulación interactiva con 8 nodos LoRa..." -ForegroundColor Cyan
        Invoke-NativeCommand { & $PythonPath "$ScriptDir\scripts\simulate_heltec_v4_mesh.py" --live } "La simulación finalizó con error."
    } elseif ($Run) {
        Write-Host "Iniciando MeshCore Bridge en producción..." -ForegroundColor Cyan
        Invoke-NativeCommand { & $PythonPath -m src } "MeshCore Bridge finalizó con error."
    }
} finally {
    Pop-Location
}
