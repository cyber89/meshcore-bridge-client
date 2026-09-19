from __future__ import annotations

from typing import Any, Dict

from repeater.data_acquisition.hardware_stats import HardwareStatsCollector

from .base import SensorBase
from .registry import SensorRegistry


@SensorRegistry.register("hardware_stats")
class HardwareStatsSensor(SensorBase):
    sensor_type = "hardware_stats"

    def __init__(self, name: str, config: Dict[str, Any] | None = None, log=None):
        super().__init__(name=name, config=config, log=log)
        self.collector = HardwareStatsCollector()

    def _read(self) -> Dict[str, Any]:
        return self.collector.get_stats()
