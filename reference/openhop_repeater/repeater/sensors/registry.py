from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from .base import SensorBase


class SensorRegistry:
    _factories: Dict[str, Callable[..., SensorBase]] = {}

    @classmethod
    def register(cls, sensor_type: str, factory: Optional[Callable[..., SensorBase]] = None):
        """Register a sensor factory or class under a sensor type."""
        key = str(sensor_type).strip().lower()

        def _decorator(target):
            cls._factories[key] = target
            return target

        if factory is not None:
            cls._factories[key] = factory
            return factory
        return _decorator

    @classmethod
    def create(
        cls, sensor_type: str, name: str, config: Optional[Dict[str, Any]] = None, **kwargs
    ) -> SensorBase:
        key = str(sensor_type).strip().lower()
        factory = cls._factories.get(key)
        if factory is None:
            raise ValueError(f"Unknown sensor type: {sensor_type}")

        if isinstance(factory, type) and issubclass(factory, SensorBase):
            return factory(name=name, config=config, **kwargs)
        return factory(name=name, config=config, **kwargs)

    @classmethod
    def available_types(cls) -> list[str]:
        return sorted(cls._factories)
