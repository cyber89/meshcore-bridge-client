# ==============================================================================
# MeshCore Bridge - Script de Instalación y Ejecución para Windows PowerShell
# Versión: 2.1.0 (Producción)
# ==============================================================================

[CmdletBinding()]
param (
    [switch]$Run,
    [switch]$InstallDeps
)

$ErrorActionPreference = "Stop"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "    🚀 GESTOR DE MESHCORE BRIDGE PARA WINDOWS (v2.1.0)" -ForegroundColor Green
Write-Host "    Heltec / LilyGO / RAKwireless / Seeed / RP2040 <-> MQTT <-> n8n" -ForegroundColor Yellow
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host ""

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# 1. Comprobar Python
Write-Host "[1/3] Verificando entorno Python..." -ForegroundColor Blue
$PythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $PythonPath) {
    $PythonPath = (Get-Command py -ErrorAction SilentlyContinue).Source
}

if (-not $PythonPath) {
    Write-Host "[ERROR] Python no fue encontrado en el PATH. Por favor instala Python 3.10+ desde python.org." -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Python encontrado: $PythonPath" -ForegroundColor Green

# 2. Instalar dependencias
if ($InstallDeps -or -not (Test-Path "$ScriptDir\.venv")) {
    Write-Host "[2/3] Instalando / verificando dependencias en requirements.txt..." -ForegroundColor Blue
    & $PythonPath -m pip install --upgrade pip -q
    & $PythonPath -m pip install -r "$ScriptDir\requirements.txt" -q
    Write-Host "[OK] Dependencias instaladas correctamente." -ForegroundColor Green
} else {
    Write-Host "[2/3] Dependencias ya disponibles." -ForegroundColor Green
}

# 3. Configurar .env si no existe
if (-not (Test-Path "$ScriptDir\.env")) {
    Write-Host "[3/3] Generando archivo .env por defecto..." -ForegroundColor Blue
    Copy-Item "$ScriptDir\.env.example" "$ScriptDir\.env" -Force
    Write-Host "[OK] Archivo .env generado a partir de .env.example." -ForegroundColor Green
} else {
    Write-Host "[3/3] Archivo .env existente detectado." -ForegroundColor Green
}

Write-Host ""
Write-Host "🎉 Configuración de MeshCore Bridge completada." -ForegroundColor Green
Write-Host "🌐 Cliente Web Station SPA: http://localhost:8080" -ForegroundColor Green
Write-Host "Para iniciar el servicio ejecuta:" -ForegroundColor Cyan
Write-Host "    python -m src" -ForegroundColor Yellow
Write-Host ""

if ($Run) {
    Write-Host "Iniciando MeshCore Bridge..." -ForegroundColor Cyan
    & $PythonPath -m src
}

