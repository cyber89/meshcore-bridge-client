"""
Unit and Integration tests for LinkQualityEngine and LQI-based routing.
Valida el cálculo de LQI instantáneo, suavizado EMA, decaimiento por inactividad,
clasificación cualitativa, selección óptima de ruta e integración con NodeRegistry.
"""

import unittest

from src.contact_manager import NodeContactUpdate, NodeRegistry
from src.lqi_engine import LinkQualityEngine, LQIStatus


class TestLinkQualityEngine(unittest.TestCase):
    def test_compute_instant_lqi_extremes(self) -> None:
        # Señal óptima máxima (+10 dB SNR, -40 dBm RSSI, 0 hops) -> 100.0%
        lqi_max = LinkQualityEngine.compute_instant_lqi(snr=10.0, rssi=-40, hops=0)
        self.assertEqual(lqi_max, 100.0)

        # Señal pésima mínima (-20 dB SNR, -125 dBm RSSI, 0 hops) -> 0.0%
        lqi_min = LinkQualityEngine.compute_instant_lqi(snr=-20.0, rssi=-125, hops=0)
        self.assertEqual(lqi_min, 0.0)

        # Valores intermedios típicos (SNR 0 dB, RSSI -85 dBm)
        lqi_mid = LinkQualityEngine.compute_instant_lqi(snr=0.0, rssi=-85, hops=0)
        self.assertTrue(40.0 <= lqi_mid <= 70.0)

    def test_hop_penalty(self) -> None:
        # Señal óptima con saltos
        lqi_0_hops = LinkQualityEngine.compute_instant_lqi(snr=10.0, rssi=-40, hops=0)
        lqi_1_hop = LinkQualityEngine.compute_instant_lqi(snr=10.0, rssi=-40, hops=1)
        lqi_2_hops = LinkQualityEngine.compute_instant_lqi(snr=10.0, rssi=-40, hops=2)

        self.assertEqual(lqi_0_hops, 100.0)
        self.assertEqual(lqi_1_hop, 85.0)   # 100 - 15
        self.assertEqual(lqi_2_hops, 70.0)  # 100 - 30

    def test_ema_smoothing(self) -> None:
        # Primer paquete adopta el valor instantáneo
        lqi_init = LinkQualityEngine.update_ema_lqi(prev_lqi=0.0, instant_lqi=80.0)
        self.assertEqual(lqi_init, 80.0)

        # Segundo paquete suavizado con alpha=0.3
        # new = 0.3 * 50 + 0.7 * 80 = 15 + 56 = 71.0
        lqi_smoothed = LinkQualityEngine.update_ema_lqi(prev_lqi=80.0, instant_lqi=50.0, alpha=0.3)
        self.assertEqual(lqi_smoothed, 71.0)

    def test_time_decay(self) -> None:
        now = 1000.0
        # Dentro del umbral de inactividad (3 minutos = 180s) -> Sin decaimiento
        lqi_fresh = LinkQualityEngine.apply_time_decay(lqi=80.0, last_seen_ts=now - 100.0, now_ts=now)
        self.assertEqual(lqi_fresh, 80.0)

        # 4 minutos de inactividad (1 minuto extra tras umbral de 3m) -> Decae 10%
        # 80 * (1 - 0.10) = 72.0
        lqi_decayed_1m = LinkQualityEngine.apply_time_decay(lqi=80.0, last_seen_ts=now - 240.0, now_ts=now)
        self.assertEqual(lqi_decayed_1m, 72.0)

        # 13 minutos de inactividad (10 minutos extra) -> Decae a 0.0%
        lqi_dead = LinkQualityEngine.apply_time_decay(lqi=80.0, last_seen_ts=now - 780.0, now_ts=now)
        self.assertEqual(lqi_dead, 0.0)

    def test_classify_lqi_status(self) -> None:
        self.assertEqual(LinkQualityEngine.classify_lqi_status(95.0), LQIStatus.EXCELLENT.value)
        self.assertEqual(LinkQualityEngine.classify_lqi_status(75.0), LQIStatus.GOOD.value)
        self.assertEqual(LinkQualityEngine.classify_lqi_status(50.0), LQIStatus.FAIR.value)
        self.assertEqual(LinkQualityEngine.classify_lqi_status(25.0), LQIStatus.POOR.value)
        self.assertEqual(LinkQualityEngine.classify_lqi_status(0.0), LQIStatus.UNREACHABLE.value)

    def test_route_selection_direct_vs_repeater(self) -> None:
        registry = NodeRegistry()
        target_pk = "11112222333344445555666677778888"
        repeater_pk = "22223333444455556666777788889999"

        # Registrar target con enlace degradado (LQI bajo: SNR -15 dB, RSSI -120 dBm)
        registry.add_or_update(
            target_pk,
            NodeContactUpdate(
                name="TargetNode",
                role="CLIENT",
                last_snr=-15.0,
                last_rssi=-120,
            ),
        )

        # Registrar un repetidor con excelente enlace (SNR +8 dB, RSSI -50 dBm)
        registry.add_or_update(
            repeater_pk,
            NodeContactUpdate(
                name="RepeaterNorth",
                role="REPEATER",
                last_snr=8.0,
                last_rssi=-50,
            ),
        )

        # Evaluar mejor ruta
        route_decision = LinkQualityEngine.select_best_route(target_pk, registry)
        self.assertEqual(route_decision["route_type"], "REPEATER")
        self.assertEqual(route_decision["via_repeater_pk"], repeater_pk)
        self.assertTrue(route_decision["lqi_score"] >= 60.0)

    def test_node_registry_lqi_integration(self) -> None:
        registry = NodeRegistry()
        node_pk = "aaaabbbbccccddddeeeeffff00001111"

        # Actualizar nodo con SNR y RSSI
        contact = registry.add_or_update(
            node_pk,
            NodeContactUpdate(
                name="SensorStation",
                role="CLIENT",
                last_snr=5.0,
                last_rssi=-60,
                hops=0,
            ),
        )

        self.assertTrue(contact.lqi_score > 70.0)
        self.assertEqual(contact.lqi_status, LQIStatus.EXCELLENT.value)

        # Consultar métricas de todos los nodos
        metrics = registry.get_all_lqi_metrics()
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0]["public_key"], node_pk)
        self.assertEqual(metrics[0]["name"], "SensorStation")
        self.assertTrue(metrics[0]["lqi_score"] > 70.0)


if __name__ == "__main__":
    unittest.main()
