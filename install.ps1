# ==============================================================================
# MeshCore Bridge - Script de Instalacion y Ejecucion para Windows PowerShell
# Version: 3.0.0 (Produccion)
# Arquitectura: CPython >= 3.11 | FastAPI ASGI | LoRa MeshCore Companion
# ==============================================================================

[CmdletBinding()]
param (
    [switch]$Run,
    [switch]$InstallDeps,
    [switch]$InstallDev,
    [switch]$Simulate
)

$ErrorActionPreference = "Stop"

# Helpers de formato visual y estados
function Write-Step {
    param([string]$Step, [string]$Title)
    Write-Host ""
    Write-Host "[$Step] " -ForegroundColor Cyan -NoNewline
    Write-Host "$Title" -ForegroundColor White
}

function Write-Success {
    param([string]$Message)
    Write-Host "  [OK] " -ForegroundColor Green -NoNewline
    Write-Host "$Message" -ForegroundColor Gray
}

function Write-Info {
    param([string]$Message)
    Write-Host "  [..] " -ForegroundColor Cyan -NoNewline
    Write-Host "$Message" -ForegroundColor Gray
}

function Write-Warn {
    param([string]$Message)
    Write-Host "  [!]  " -ForegroundColor Yellow -NoNewline
    Write-Host "$Message" -ForegroundColor Yellow
}

function Write-Fail {
    param([string]$Message)
    Write-Host "  [ERR] " -ForegroundColor Red -NoNewline
    Write-Host "$Message" -ForegroundColor Red
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
            Write-Fail "$ErrorMessage (Codigo de salida: $LASTEXITCODE)"
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
    if (-not (Test-Path $PythonPath)) { return $false }
    & $PythonPath -c "import sys, venv, ensurepip; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Get-PythonVersionString {
    param([string]$PythonPath)
    $vOutput = & $PythonPath --version 2>&1
    if ($vOutput) {
        return ($vOutput -replace '^Python\s*', '').Trim()
    }
    return "3.11+"
}

function Find-PythonRuntime {
    if ($env:MESHCORE_PYTHON) {
        if (-not (Test-PythonRuntime -PythonPath $env:MESHCORE_PYTHON)) {
            throw "MESHCORE_PYTHON ($env:MESHCORE_PYTHON) no es compatible. Se requiere CPython >= 3.11 con venv/ensurepip."
        }
        return $env:MESHCORE_PYTHON
    }

    $Candidates = @()
    foreach ($Name in @('python3.14', 'python3.13', 'python3.12', 'python3.11', 'python')) {
        $Command = Get-Command $Name -ErrorAction SilentlyContinue
        if ($Command) { $Candidates += $Command.Source }
    }

    $Launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($Launcher) {
        $Installed = & $Launcher.Source -0p 2>$null
        if ($LASTEXITCODE -eq 0) {
            foreach ($Line in $Installed) {
                if ($Line -match '^\s*-(?:V:)?(3\.(?:1[1-9]|[2-9][0-9]))(?:-\d+)?\s+\*?\s*(.+?)\s*$') {
                    $Candidates += $Matches[2]
                }
            }
        }
    }

    foreach ($Candidate in $Candidates) {
        if (Test-PythonRuntime -PythonPath $Candidate) { return $Candidate }
    }

    throw "No se encontro CPython >= 3.11 compatible en el sistema. Instalalo desde https://python.org o define la variable MESHCORE_PYTHON."
}

# ==============================================================================
# Banner de Presentacion
# ==============================================================================
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "    MESHCORE BRIDGE - GESTOR DE INSTALACION Y ENTORNO" -ForegroundColor Cyan
Write-Host "    LoRa Companion <-> MQTT <-> WebSocket <-> Web Station SPA v3.0" -ForegroundColor Yellow
Write-Host "==================================================================" -ForegroundColor Cyan

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# 1. Comprobar / Crear entorno virtual de Python
Write-Step "1/5" "Verificando runtime de Python y entorno virtual (.venv)..."

$VenvPython = "$ScriptDir\.venv\Scripts\python.exe"
$NeedNewVenv = $true

if (Test-Path $VenvPython) {
    if (Test-PythonRuntime -PythonPath $VenvPython) {
        $PythonPath = $VenvPython
        $vStr = Get-PythonVersionString -PythonPath $PythonPath
        Write-Success "Entorno virtual existente detectado: Python $vStr ($PythonPath)"
        $NeedNewVenv = $false
    } else {
        Write-Warn "El entorno virtual existente en .venv no cumple con CPython >= 3.11. Se recreara..."
        Remove-Item "$ScriptDir\.venv" -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if ($NeedNewVenv) {
    Write-Info "Buscando interprete Python compatible (>= 3.11) en el sistema..."
    $SystemPython = Find-PythonRuntime
    $sysVer = Get-PythonVersionString -PythonPath $SystemPython
    Write-Success "Interprete base detectado: Python $sysVer ($SystemPython)"

    Write-Info "Creando entorno virtual aislado en $ScriptDir\.venv..."
    Invoke-NativeCommand { & $SystemPython -m venv "$ScriptDir\.venv" } "Fallo al crear el entorno virtual."
    $PythonPath = $VenvPython
    Write-Success "Entorno virtual inicializado exitosamente."
}

# 2. Instalar dependencias de produccion
Write-Step "2/5" "Instalando dependencias del ecosistema MeshCore Bridge..."

$DepsValid = Test-RuntimeDependencies -PythonPath $PythonPath -ScriptDir $ScriptDir

if ($InstallDeps -or -not $DepsValid) {
    Write-Info "Actualizando pip y herramientas de empaquetado..."
    & $PythonPath -m pip install --upgrade pip setuptools wheel -q 2>$null

    Write-Info "Instalando paquetes desde requirements.txt..."
    Write-Host "     * paho-mqtt (2.1.0)        * meshcore SDK (2.3.15)" -ForegroundColor DarkGray
    Write-Host "     * pyserial (3.5)           * python-dotenv (1.2.4)" -ForegroundColor DarkGray
    Write-Host "     * fastapi (0.143.0)        * uvicorn (0.54.0)" -ForegroundColor DarkGray
    Write-Host "     * pydantic (2.14.0)        * websockets (17.2)" -ForegroundColor DarkGray
    Write-Host "     * starlette & h11 (ASGI)   * bleak & pycayennelpp" -ForegroundColor DarkGray

    Invoke-NativeCommand { & $PythonPath -m pip install -r "$ScriptDir\requirements.txt" } "Fallo al instalar requirements.txt."

    Write-Info "Verificando integridad de dependencias instaladas (perfil web)..."
    Invoke-NativeCommand { & $PythonPath "$ScriptDir\scripts\check_runtime_dependencies.py" --profile web } "Dependencias incompletas o incompatibles tras la instalacion."
    Write-Success "Todas las dependencias de produccion se encuentran instaladas y certificadas."
} else {
    Write-Success "Todas las dependencias de produccion ya se encuentran disponibles y verificadas."
}

# 3. Herramientas de desarrollo / QA / auditoria (opcional)
if ($InstallDev) {
    Write-Step "3/5" "Instalando herramientas de desarrollo y QA (pytest, mypy, ruff, playwright)..."
    Invoke-NativeCommand { & $PythonPath -m pip install -r "$ScriptDir\requirements-dev.txt" -q } "Fallo al instalar requirements-dev.txt."
    Invoke-NativeCommand { & $PythonPath -m pip install -e "$ScriptDir" -q } "Fallo al instalar el paquete en modo editable."
    $PlaywrightExe = "$ScriptDir\.venv\Scripts\playwright.exe"
    if (Test-Path $PlaywrightExe) {
        Write-Info "Instalando navegador Chromium para pruebas E2E..."
        Invoke-NativeCommand { & $PlaywrightExe install chromium } "Fallo al instalar Chromium para Playwright."
    }
    Write-Success "Tooling de desarrollo y suites de prueba instalados."
} else {
    Write-Step "3/5" "Omitiendo herramientas de desarrollo (usa -InstallDev si las requieres)."
}

# 4. Deteccion de puertos y transceptores LoRa conectados
Write-Step "4/5" "Detectando puertos serie y transceptores USB conectados..."

$DetectedPorts = @()
try {
    $Ports = [System.IO.Ports.SerialPort]::GetPortNames()
    if ($Ports -and $Ports.Count -gt 0) {
        $DetectedPorts = $Ports | Sort-Object -Unique
    }
} catch {}

if ($DetectedPorts.Count -gt 0) {
    Write-Success "Puertos COM detectados: $($DetectedPorts -join ', ')"
    $DefaultPort = $DetectedPorts[0]
} else {
    Write-Warn "No se detectaron transceptores USB conectados actualmente. Se usara modo 'AUTO'."
    $DefaultPort = "AUTO"
}

# 5. Configurar .env si no existe
Write-Step "5/5" "Verificando archivo de configuracion local (.env)..."

if (-not (Test-Path "$ScriptDir\.env")) {
    if (Test-Path "$ScriptDir\.env.example") {
        Copy-Item "$ScriptDir\.env.example" "$ScriptDir\.env" -Force
        if ($DefaultPort -ne "AUTO") {
            (Get-Content "$ScriptDir\.env") -replace '^SERIAL_PORT=.*', "SERIAL_PORT=$DefaultPort" | Set-Content "$ScriptDir\.env"
        }
        Write-Success "Archivo .env creado a partir de .env.example (SERIAL_PORT=$DefaultPort)."
    } else {
        Write-Warn "No se encontro .env.example para generar la plantilla."
    }
} else {
    Write-Success "Archivo .env existente conservado intacto."
}

# ==============================================================================
# Tarjeta de Resumen y Comandos Rapidos
# ==============================================================================
Write-Host ""
Write-Host "==================================================================" -ForegroundColor Green
Write-Host "    INSTALACION DE MESHCORE BRIDGE COMPLETADA EXITOSAMENTE" -ForegroundColor Green
Write-Host "==================================================================" -ForegroundColor Green
Write-Host "  Directorio del servicio:  $ScriptDir" -ForegroundColor Gray
Write-Host "  Interprete Python (.venv): $PythonPath" -ForegroundColor Gray
Write-Host "  Web Station SPA:          http://localhost:8080" -ForegroundColor Yellow
Write-Host "  Broker MQTT Local:        127.0.0.1:1883 (Canal meshcore/#)" -ForegroundColor Gray
Write-Host "  Puerto Serial LoRa:       $DefaultPort" -ForegroundColor Gray
Write-Host "------------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "  Comandos de Ejecucion:" -ForegroundColor Cyan
Write-Host "    * Iniciar en Produccion:    .\install.ps1 -Run" -ForegroundColor White
Write-Host "    * Iniciar Simulacion LoRa:  .\install.ps1 -Simulate" -ForegroundColor White
Write-Host "    * Reinstalar Dependencias:  .\install.ps1 -InstallDeps" -ForegroundColor White
Write-Host "==================================================================" -ForegroundColor Green
Write-Host ""

Push-Location $ScriptDir
try {
    if ($Simulate) {
        Write-Host "Iniciando simulacion interactiva con malla virtual..." -ForegroundColor Cyan
        Invoke-NativeCommand { & $PythonPath "$ScriptDir\run_interactive_demo.py" } "La simulacion finalizo con error."
    } elseif ($Run) {
        Write-Host "Iniciando MeshCore Bridge en produccion..." -ForegroundColor Cyan
        Invoke-NativeCommand { & $PythonPath -m src } "MeshCore Bridge finalizo con error."
    }
} finally {
    Pop-Location
}
