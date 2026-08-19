# MeshCore Bridge - Paquete Listo para Despliegue (Deploy Bundle v3.0.0)

Este directorio contiene todos los archivos necesarios para realizar una instalación limpia y completa de **MeshCore Bridge v3.0.0** en servidores Linux (Orange Pi, Raspberry Pi, Ubuntu, Debian, Proxmox LXC) o Windows.

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
.\install.ps1 -InstallDeps -Run
```

Para arrancar el simulador interactivo de 8 nodos:
```powershell
.\install.ps1 -Simulate
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
