from __future__ import annotations

import importlib.util
import logging
import re

# Required for optional dependency installation in controlled, validated path.
import subprocess  # nosec B404
import sys
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional, Tuple

_PIP_PACKAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class SensorBase(ABC):
    """Base class for lightweight sensor plug-ins."""

    sensor_type = "sensor"

    def __init__(
        self,
        name: str,
        config: Optional[Dict[str, Any]] = None,
        log: Optional[logging.Logger] = None,
    ):
        self.name = name
        self.config = config or {}
        self.settings = self.config.get("settings", {}) if isinstance(self.config, dict) else {}
        self.enabled = (
            bool(self.config.get("enabled", True)) if isinstance(self.config, dict) else True
        )
        self.log = log or logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def _read(self) -> Dict[str, Any]:
        """Read the sensor and return a raw payload dictionary."""

    def read(self) -> Dict[str, Any]:
        timestamp = datetime.now(timezone.utc).isoformat()
        if not self.enabled:
            return self._result(ok=False, timestamp=timestamp, error="disabled")

        try:
            data = self._read()
        except Exception as exc:
            self.log.warning("Sensor read failed for %s: %s", self.name, exc)
            return self._result(ok=False, timestamp=timestamp, error=f"{type(exc).__name__}: {exc}")

        if data is None:
            data = {}
        if not isinstance(data, dict):
            data = {"value": data}

        return self._result(ok=True, timestamp=timestamp, data=data)

    def _result(
        self,
        *,
        ok: bool,
        timestamp: str,
        data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "name": self.name,
            "type": self.sensor_type,
            "ok": ok,
            "timestamp": timestamp,
            "data": data or {},
        }
        if error:
            result["error"] = error
        return result

    def _auto_install_enabled(self) -> bool:
        """Return true when package auto-install is enabled for this sensor."""
        raw = self.config.get("auto_install_packages") if isinstance(self.config, dict) else False
        return bool(raw)

    def ensure_python_modules(self, modules: Iterable[Tuple[str, str]]) -> bool:
        """Ensure Python modules are importable; optionally install via pip if missing.

        modules: iterable of (import_name, pip_package_name).
        """
        missing: list[Tuple[str, str]] = []
        for import_name, package_name in modules:
            if importlib.util.find_spec(import_name) is None:
                missing.append((import_name, package_name))

        if not missing:
            return True

        if not self._auto_install_enabled():
            names = ", ".join(pkg for _, pkg in missing)
            self.log.warning(
                "Missing sensor dependencies for %s: %s (set auto_install_packages=true to install automatically)",
                self.name,
                names,
            )
            return False

        for import_name, package_name in missing:
            if not _PIP_PACKAGE_RE.fullmatch(package_name):
                self.log.warning(
                    "Refusing to install dependency with unsupported package name for %s: %r",
                    self.name,
                    package_name,
                )
                return False
            self.log.info("Installing missing dependency for %s: %s", self.name, package_name)
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", package_name],
                capture_output=True,
                text=True,
                check=False,
            )  # nosec B603
            if result.returncode != 0:
                self.log.warning(
                    "Failed installing %s for %s: %s",
                    package_name,
                    self.name,
                    (result.stderr or result.stdout or "unknown error").strip(),
                )
                return False

            if importlib.util.find_spec(import_name) is None:
                self.log.warning(
                    "Dependency %s installed but module %s still unavailable for %s",
                    package_name,
                    import_name,
                    self.name,
                )
                return False

        return True
