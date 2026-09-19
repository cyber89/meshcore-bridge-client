from __future__ import annotations

import importlib
import logging
import threading
import time
from typing import Any, Dict, List, Optional

from .registry import SensorRegistry


class SensorManager:
    """Load and read sensor plug-ins declared in config with background polling."""

    def __init__(
        self,
        config: Dict[str, Any],
        *,
        log: Optional[logging.Logger] = None,
        registry: type[SensorRegistry] = SensorRegistry,
    ):
        self.config = config if isinstance(config, dict) else {}
        self.log = log or logging.getLogger(self.__class__.__name__)
        self.registry = registry
        self.sensors = []

        # Background polling
        self._poll_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._latest_readings: List[Dict[str, Any]] = []
        self._readings_lock = threading.RLock()
        self._running = False

        self.reload()

    def _get_sensor_definitions(self) -> List[Dict[str, Any]]:
        """Extract sensor definitions from config."""
        section = self.config.get("sensors", {})
        if not isinstance(section, dict):
            return []
        global_auto_install = bool(section.get("auto_install_packages", False))
        definitions = section.get("definitions") or section.get("sensors")
        if not isinstance(definitions, list):
            return []
        out: List[Dict[str, Any]] = []
        for d in definitions:
            if not isinstance(d, dict):
                continue
            entry = dict(d)
            entry.setdefault("auto_install_packages", global_auto_install)
            out.append(entry)
        return out

    def _load_sensor_module(self, sensor_type: str) -> None:
        """Import sensor module so @SensorRegistry.register decorators execute."""
        module_name = str(sensor_type).strip().lower().replace("-", "_")
        package_name = __name__.rsplit(".", 1)[0]
        importlib.import_module(f"{package_name}.{module_name}")

    def reload(self) -> None:
        self.sensors = []
        for definition in self._get_sensor_definitions():
            if not definition.get("enabled", True):
                continue

            sensor_type = definition.get("type")
            name = definition.get("name") or str(sensor_type or "sensor")
            if not sensor_type:
                self.log.warning("Skipping sensor definition %r: missing type", name)
                continue

            try:
                self._load_sensor_module(sensor_type)
                sensor = self.registry.create(sensor_type, name=name, config=definition)
            except Exception as exc:
                self.log.warning("Skipping sensor %r of type %r: %s", name, sensor_type, exc)
                continue

            self.sensors.append(sensor)

    def start(self) -> None:
        if self._running:
            return
        self.reload()

        # Start background polling thread if enabled and sensors exist
        section = self.config.get("sensors", {})
        if not isinstance(section, dict) or not section.get("enabled", False):
            self.log.debug("Sensor manager disabled in config")
            return

        if not self.sensors:
            self.log.debug("No sensors loaded; skipping background polling")
            return

        self._stop_event.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop, name="sensor-manager", daemon=True
        )
        self._poll_thread.start()
        self._running = True
        self.log.info("Sensor manager polling started (%d sensors)", len(self.sensors))

    def stop(self) -> None:
        if not self._running:
            return
        self._stop_event.set()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=2.0)
        self._running = False
        self.log.info("Sensor manager polling stopped")

    def read_all(self) -> List[Dict[str, Any]]:
        readings: List[Dict[str, Any]] = []
        for sensor in self.sensors:
            readings.append(self._read_sensor(sensor))
        return readings

    def _read_sensor(self, sensor) -> Dict[str, Any]:
        try:
            return sensor.read()
        except Exception as exc:
            self.log.warning("Sensor manager caught read error for %s: %s", sensor.name, exc)
            return {
                "name": sensor.name,
                "type": getattr(sensor, "sensor_type", "sensor"),
                "ok": False,
                "timestamp": None,
                "data": {},
                "error": f"{type(exc).__name__}: {exc}",
            }

    @staticmethod
    def _sensor_poll_interval(sensor, default_interval: float) -> float:
        raw = getattr(sensor, "poll_interval_seconds", default_interval)
        try:
            interval = float(raw)
        except (TypeError, ValueError):
            interval = default_interval
        return max(0.1, interval)

    def _poll_loop(self) -> None:
        """Background thread: poll sensors at configured interval and cache readings."""
        section = self.config.get("sensors", {})
        poll_interval = 30.0
        if isinstance(section, dict):
            try:
                poll_interval = float(section.get("poll_interval_seconds", 30.0))
            except (TypeError, ValueError):
                pass

        self.log.debug("Sensor polling loop started (interval=%.1f sec)", poll_interval)

        next_read_at: Dict[str, float] = {}
        latest_by_name: Dict[str, Dict[str, Any]] = {}

        while not self._stop_event.is_set():
            now = time.monotonic()
            next_due_in = poll_interval
            try:
                updated = False
                for sensor in self.sensors:
                    name = sensor.name
                    interval = self._sensor_poll_interval(sensor, poll_interval)
                    due_at = next_read_at.get(name, 0.0)
                    if now >= due_at:
                        latest_by_name[name] = self._read_sensor(sensor)
                        next_read_at[name] = now + interval
                        updated = True
                    next_due_in = min(next_due_in, max(0.0, next_read_at[name] - now))

                if updated:
                    readings = [
                        latest_by_name[s.name] for s in self.sensors if s.name in latest_by_name
                    ]
                    with self._readings_lock:
                        self._latest_readings = readings
            except Exception as exc:
                self.log.warning("Sensor poll cycle failed: %s", exc)

            # Wait for next poll or stop signal
            self._stop_event.wait(max(0.1, next_due_in))

        self.log.debug("Sensor polling loop stopped")

    def get_summary(self) -> Dict[str, Any]:
        section = self.config.get("sensors", {})
        poll_interval = 30.0
        if isinstance(section, dict):
            try:
                poll_interval = float(section.get("poll_interval_seconds", 30.0))
            except (TypeError, ValueError):
                pass

        # Get cached readings (or empty list if not running)
        with self._readings_lock:
            readings = list(self._latest_readings) if self._latest_readings else []

        return {
            "enabled": bool(isinstance(section, dict) and section.get("enabled", False)),
            "poll_interval_seconds": poll_interval,
            "configured": len(self._get_sensor_definitions()),
            "loaded": len(self.sensors),
            "running": self._running,
            "readings": readings,
        }
