#!/usr/bin/env python3
"""
MeshCore Bridge - Deployment Bundle Synchronizer & Packager
Sincroniza y empaqueta de forma determinista todos los archivos de producción
necesarios para una instalación limpia en la carpeta 'deploy/' y genera paquetes
comprimidos (.tar.gz, .zip) y sumas de verificación SHA256.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
import tarfile
import zipfile
from pathlib import Path

# Asegurar compatibilidad de salida UTF-8 en consolas Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

ROOT_DIR = Path(__file__).resolve().parent.parent
DEPLOY_DIR = ROOT_DIR / "deploy"
VERSION = "3.0.0"

# Archivos raíz esenciales para el despliegue
ROOT_FILES = [
    "config.py",
    "meshcore_bridge.py",
    "requirements.txt",
    "pyproject.toml",
    ".env.example",
    "install.sh",
    "install.ps1",
    "meshcore-bridge.service",
    "n8n_workflow_meshcore.json",
    "README.md",
]

# Directorios de producción a copiar íntegramente
DIRS_TO_COPY = [
    ("src", "src"),
    ("scripts", "scripts"),
    ("docs", "docs"),
]


def ignore_cache_and_temps(directory: str, files: list[str]) -> set[str]:
    """Filtra archivos temporales, cachés y bases de datos transaccionales."""
    ignored: set[str] = set()
    for f in files:
        if f in ("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".coverage", "artifacts"):
            ignored.add(f)
        elif f.endswith((".pyc", ".pyo", ".pyd", ".db", ".db-wal", ".db-shm", ".log", ".tar.gz", ".zip")):
            ignored.add(f)
    return ignored


def calculate_sha256(file_path: Path) -> str:
    """Calcula el hash SHA256 de un archivo."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def sync_deploy_bundle() -> None:
    """Genera y sincroniza la carpeta deploy/ con la última versión del proyecto y crea archivos comprimidos."""
    print(f"📦 [DEPLOY] Iniciando empaquetado y sincronización hacia: {DEPLOY_DIR}")

    # 1. Crear directorio deploy
    DEPLOY_DIR.mkdir(parents=True, exist_ok=True)

    # 2. Copiar archivos raíz individuales
    for filename in ROOT_FILES:
        src_file = ROOT_DIR / filename
        if src_file.exists():
            dst_file = DEPLOY_DIR / filename
            shutil.copy2(src_file, dst_file)
            print(f"  ✓ Copiado: {filename}")
        else:
            print(f"  ⚠ Advertencia: No se encontró {filename}", file=sys.stderr)

    # 3. Copiar directorios completos
    for src_rel, dst_rel in DIRS_TO_COPY:
        src_path = ROOT_DIR / src_rel
        dst_path = DEPLOY_DIR / dst_rel

        if src_path.exists():
            if dst_path.exists():
                shutil.rmtree(dst_path)
            shutil.copytree(src_path, dst_path, ignore=ignore_cache_and_temps)
            print(f"  ✓ Sincronizado directorio: {src_rel}/ -> {dst_rel}/")

    # 4. Generar README específico dentro de deploy/
    deploy_readme = DEPLOY_DIR / "README.md"
    deploy_readme_content = f"""# MeshCore Bridge - Paquete Listo para Despliegue (Deploy Bundle v{VERSION})

Este directorio contiene todos los archivos necesarios para realizar una instalación limpia y completa de **MeshCore Bridge v{VERSION}** en servidores Linux (Orange Pi, Raspberry Pi, Ubuntu, Debian, Proxmox LXC) o Windows.

---

## ⚡ Instalación en Linux / Proxmox (1 Comando)

```bash
# 1. Acceder al directorio
cd deploy

# 2. Ejecutar instalador automatizado
sudo bash install.sh
```

El script `install.sh`:
- Instala dependencias del sistema y Python 3.10+.
- Configura el broker MQTT Mosquitto local.
- Detecta automáticamente el transceptor MeshCore USB (Heltec, LilyGO, RAK, Seeed, RP2040).
- Configura el entorno virtual en `/opt/meshcore-bridge`.
- Registra e inicia el servicio en `systemd` (`meshcore-bridge.service`).

---

## ⚡ Actualización de una Instalación Existente

```bash
sudo bash install.sh --update
```

---

## ⚡ Instalación en Windows (PowerShell)

```powershell
cd deploy
.\\install.ps1 -InstallDeps -Run
```

Para arrancar el simulador interactivo de 8 nodos:
```powershell
.\\install.ps1 -Simulate
```

---

## 🌐 Acceso a la Interfaz Web SPA
Una vez en ejecución, la estación web estará disponible en:
- **`http://localhost:8080`** (o `http://<IP_DEL_SERVIDOR>:8080`)
- **`http://localhost:8085`** (en modo simulación)

---

## 📡 Integración con n8n y Home Assistant
- **Workflow n8n listo para importar**: `n8n_workflow_meshcore.json`
- **MQTT Auto-Discovery Home Assistant**: Activado por defecto en `homeassistant/sensor/#`
"""
    deploy_readme.write_text(deploy_readme_content, encoding="utf-8")
    print("  ✓ Generado README de despliegue en: deploy/README.md")

    # 5. Generar archivo TAR.GZ para Linux
    tar_name = f"meshcore-bridge-v{VERSION}.tar.gz"
    tar_path_deploy = DEPLOY_DIR / tar_name
    tar_path_root = ROOT_DIR / tar_name

    with tarfile.open(tar_path_deploy, "w:gz") as tar:
        for item in DEPLOY_DIR.iterdir():
            if item.name not in (tar_name, f"meshcore-bridge-v{VERSION}.zip", "SHA256SUMS"):
                tar.add(item, arcname=item.name)
    shutil.copy2(tar_path_deploy, tar_path_root)
    print(f"  ✓ Generado paquete comprimido Linux: {tar_name}")

    # 6. Generar archivo ZIP para Windows / Multiplataforma
    zip_name = f"meshcore-bridge-v{VERSION}.zip"
    zip_path_deploy = DEPLOY_DIR / zip_name
    zip_path_root = ROOT_DIR / zip_name

    with zipfile.ZipFile(zip_path_deploy, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for root, _, files in shutil.os.walk(DEPLOY_DIR):
            for file in files:
                if file in (zip_name, tar_name, "SHA256SUMS"):
                    continue
                file_full = Path(root) / file
                rel_path = file_full.relative_to(DEPLOY_DIR)
                zip_file.write(file_full, arcname=str(rel_path))
    shutil.copy2(zip_path_deploy, zip_path_root)
    print(f"  ✓ Generado paquete comprimido ZIP: {zip_name}")

    # 7. Generar sumas de verificación SHA256
    sha_file = DEPLOY_DIR / "SHA256SUMS"
    sha_lines = [
        f"{calculate_sha256(tar_path_deploy)}  {tar_name}",
        f"{calculate_sha256(zip_path_deploy)}  {zip_name}",
    ]
    sha_file.write_text("\n".join(sha_lines) + "\n", encoding="utf-8")
    shutil.copy2(sha_file, ROOT_DIR / "SHA256SUMS")
    print("  ✓ Generado archivo de sumas de verificación: SHA256SUMS")

    print("\n🎉 [DEPLOY] Sincronización y empaquetado completados con éxito.")
    print(f"📁 Directorio de instalación: {DEPLOY_DIR}")
    print(f"📦 Paquete Linux: {tar_path_root}")
    print(f"📦 Paquete ZIP:   {zip_path_root}")


if __name__ == "__main__":
    sync_deploy_bundle()
