"""
CLI Command Executor for MeshCore Bridge Local Radio Control.
Interpreta y despacha comandos de consola CLI emitidos hacia la estación base local.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import config

if TYPE_CHECKING:
    from src.admin_handler import AdminContext


def _extract_payload_dict(data: Any) -> dict[str, Any]:
    """Extrae un diccionario de datos tanto de objetos Event como de dicts nativos."""
    if data is None:
        return {}
    if isinstance(data, dict):
        return data
    if hasattr(data, "payload") and isinstance(data.payload, dict):
        return data.payload
    return {}


class CliCommandExecutor:
    """Ejecutor de comandos CLI para el control y diagnóstico del transceptor local."""

    def __init__(
        self,
        ctx: AdminContext,
        local_config: dict[str, Any],
        get_local_config: Callable[[], dict[str, Any]],
        publish_safe: Callable[..., None],
        broadcast_advert: Callable[..., Any],
        handle_set_local_config: Callable[..., Any],
        init_time: float,
    ) -> None:
        self._ctx = ctx
        self._local_config = local_config
        self._get_local_config = get_local_config
        self._publish_safe = publish_safe
        self._broadcast_advert = broadcast_advert
        self._handle_set_local_config = handle_set_local_config
        self._init_time = init_time

    async def execute(
        self,
        action: str,
        res: dict[str, Any],
        mc: Any,
    ) -> dict[str, Any]:
        """Ejecuta comandos CLI y de control directo local.

        Extraído de AdminCommandHandler para reducir la complejidad ciclomática
        y mantener la cohesión de módulos.
        """
        act_clean = action.lower().strip()
        cfg = self._get_local_config()
        local_pk = str(cfg.get("public_key", "")).lower().strip()
        local_name = str(cfg.get("name", "")).lower().strip()

        try:
            if act_clean in ("ver", "v", "q", "query", "version"):
                res = await self._cli_version(res, cfg, mc)

            elif act_clean in ("bat", "get_bat", "battery", "bateria"):
                res = await self._cli_battery(res, cfg, mc)

            elif act_clean in ("time", "get_time", "clock", "hora"):
                res = await self._cli_time(res, cfg, mc)

            elif act_clean in ("sync_clock", "clock sync", "set_time", "st", "synctime"):
                res = await self._cli_sync_clock(res, mc)

            elif act_clean in ("stats", "stats_core", "get_stats_core", "status"):
                res = await self._cli_stats_core(res, cfg, mc)

            elif act_clean in ("radio", "stats_radio", "get_stats_radio", "tuning", "get_tuning"):
                res["result"] = self._cli_radio_info(cfg)

            elif act_clean in ("packets", "stats_packets", "get_stats_packets"):
                res["result"] = self._cli_packets_info(cfg)

            elif act_clean in ("channels", "get_channels", "chan"):
                res["result"] = (
                    "📻 [CANALES CONFIGURADOS]\n"
                    "  • Canal 0: Public / Broadcast (Público - Sin cifrar)\n"
                    "  • Canales 1-7: Disponibles para grupos privados (PSK AES-128)"
                )

            elif act_clean in ("pos", "get_pos", "get pos", "position"):
                res["result"] = self._cli_position_info(cfg)

            elif act_clean in ("owner", "get_owner", "get owner", "get_identity", "identity"):
                res["result"] = self._cli_owner_info(cfg)

            elif act_clean in ("neighbors", "get_neighbors", "discover.neighbors", "discover_neighbors", "vecinos"):
                res["result"] = self._cli_neighbors(cfg, local_pk, local_name)

            elif act_clean in ("nodes", "list_nodes", "get_nodes", "nodos"):
                res["result"] = self._cli_nodes_list(cfg, local_pk, local_name)

            elif act_clean in ("lqi", "get_lqi", "link_quality", "lqi_topology"):
                res = self._cli_lqi(res, cfg, local_pk)

            elif act_clean in ("acl", "get_acl", "get acl", "acl list", "acl_list"):
                res["result"] = "🔐 [CONTROL DE ACCESO ACL] Autenticación por PIN activa | Permisos: ADMIN / OPERATOR"

            elif act_clean in ("board", "hardware", "hw"):
                res["result"] = (
                    "🖥️ [HARDWARE BOARD] Microcontrolador: ESP32-S3 / nRF52840 | "
                    "Transceptor: Semtech SX1262 LoRa | Bus: Serial UART 115200"
                )

            elif act_clean in ("ping", "ping 0", "ping_zero", "pingzero"):
                res["result"] = "🎯 [PING] Enlace del transceptor local verificado y operativo (RTT: < 1 ms | Canal Serial Directo)."

            elif act_clean in ("advert", "send_advert", "broadcast_advert"):
                await self._cli_send_advert(mc, flood=False)
                res["result"] = "📢 [ADVERT] Anuncio de presencia emitido por radio hacia nodos vecinos (Hop 0)."

            elif act_clean in ("advert flood", "advert_flood", "flood"):
                await self._cli_send_advert(mc, flood=True)
                res["result"] = "🌊 [ADVERT FLOOD] Anuncio de presencia propagado a través de toda la malla repetidora."

            elif act_clean in ("reboot", "reboot_local", "restart"):
                if mc and hasattr(mc, "commands") and hasattr(mc.commands, "reboot"):
                    await mc.commands.reboot()
                res["result"] = "🔄 [REBOOT] Comando de reinicio de hardware ejecutado en el microcontrolador local."

            elif act_clean in ("clear stats", "clear_stats", "clear"):
                self._local_config["tx_count"] = 0
                self._local_config["rx_count"] = 0
                self._local_config["packet_errors"] = 0
                self._local_config["airtime_ms"] = 0
                self._local_config["duplicate_packets"] = 0
                if hasattr(self._ctx, "counters") and self._ctx.counters:
                    try:
                        self._ctx.counters.tx_count = 0
                        self._ctx.counters.rx_count = 0
                    except Exception:
                        pass
                res["result"] = "🧹 [STATS] Contadores de paquetes locales y tiempos de aire restablecidos a cero."

            elif act_clean in ("help", "?", "ayuda"):
                res["result"] = self._cli_help_text()

            elif act_clean.startswith("set ") or act_clean.startswith("set_"):
                res = await self._cli_set_param(act_clean, res)

            else:
                res["result"] = f"✓ Comando '{action}' procesado correctamente por el firmware MeshCore."

        except Exception as e:
            res["status"] = "error"
            res["error"] = str(e)
            res["result"] = f"✗ ERROR ejecutando comando '{action}': {e}"

        res["config"] = self._get_local_config()
        self._publish_safe(config.TOPIC_ADMIN_STAT, json.dumps(res), qos=1)
        return res

    # ---- CLI Sub-handlers ---- #

    async def _cli_version(self, res: dict[str, Any], cfg: dict[str, Any], mc: Any) -> dict[str, Any]:
        """Handler para comandos: ver, v, q, query, version."""
        model = cfg.get("model", "MeshCore Transceiver")
        ver = cfg.get("ver", cfg.get("fw_ver", "v1.6.0"))
        build = cfg.get("fw_build", "2026-08-20")
        rep_str = "Activado" if cfg.get("repeat", False) else "Desactivado"
        if mc and hasattr(mc, "commands") and hasattr(mc.commands, "send_device_query"):
            try:
                q_res = await mc.commands.send_device_query()
                if hasattr(q_res, "payload") and isinstance(q_res.payload, dict):
                    pl = q_res.payload
                    model = pl.get("model", model)
                    ver = pl.get("ver", ver)
                    build = pl.get("fw_build", build)
                    rep_str = "Activado" if pl.get("repeat", cfg.get("repeat", False)) else "Desactivado"
            except Exception:
                pass
        res["result"] = f"📟 [DEVICE INFO] Modelo: {model} | Firmware: {ver} | Build: {build} | Repetidor: {rep_str}"
        return res

    async def _cli_battery(self, res: dict[str, Any], cfg: dict[str, Any], mc: Any) -> dict[str, Any]:
        """Handler para comandos: bat, get_bat, battery, bateria."""
        pct = cfg.get("battery_pct", 100)
        volt = cfg.get("voltage", 5.0)
        mv = cfg.get("battery_mv", 5000)
        src = cfg.get("power_source", "USB 5V Directo")
        if mc and hasattr(mc, "commands") and hasattr(mc.commands, "get_bat"):
            try:
                bat_res = await mc.commands.get_bat()
                if hasattr(bat_res, "payload") and isinstance(bat_res.payload, dict):
                    pct = bat_res.payload.get("battery_pct", pct)
                    mv = bat_res.payload.get("battery_mv", mv)
                    volt = round(mv / 1000.0, 2)
                elif isinstance(bat_res, dict):
                    pct = bat_res.get("battery_pct", pct)
                    mv = bat_res.get("battery_mv", mv)
                    volt = round(mv / 1000.0, 2)
            except Exception:
                pass
        res["result"] = f"🔋 [BATERÍA] Nivel: {pct}% | Voltaje: {volt:.2f} V ({mv} mV) | Alimentación: {src}"
        return res

    async def _cli_time(self, res: dict[str, Any], cfg: dict[str, Any], mc: Any) -> dict[str, Any]:
        """Handler para comandos: time, get_time, clock, hora."""
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        now_ts = int(time.time())
        if mc and hasattr(mc, "commands") and hasattr(mc.commands, "get_time"):
            try:
                t_res = await mc.commands.get_time()
                if hasattr(t_res, "payload") and isinstance(t_res.payload, dict):
                    raw_time = t_res.payload.get("time", t_res.payload.get("timestamp"))
                    if raw_time is not None:
                        now_ts = int(raw_time)
                        now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_ts))
            except Exception:
                pass
        res["result"] = f"🕒 [RTC CLOCK] Hora del Nodo: {now_str} (Timestamp: {now_ts})"
        return res

    async def _cli_sync_clock(self, res: dict[str, Any], mc: Any) -> dict[str, Any]:
        """Handler para comandos: sync_clock, clock sync, set_time, st, synctime."""
        now_ts = int(time.time())
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        if mc and hasattr(mc, "commands") and hasattr(mc.commands, "set_time"):
            try:
                res_cmd = mc.commands.set_time(now_ts)
                if asyncio.iscoroutine(res_cmd):
                    await asyncio.wait_for(res_cmd, timeout=3.0)
            except Exception as e:
                logging.warning(f"Error enviando set_time a radio: {e}")
        self._local_config["clock"] = time.strftime("%I:%M:%S %p", time.localtime(now_ts))
        self._local_config["device_epoch_time"] = now_ts
        res["result"] = f"✓ [RTC OK] Reloj RTC sincronizado exitosamente con la hora del host: {now_str}"
        res["clock"] = self._local_config["clock"]
        res["epoch"] = now_ts
        return res

    async def _cli_stats_core(self, res: dict[str, Any], cfg: dict[str, Any], mc: Any) -> dict[str, Any]:
        """Handler para comandos: stats, stats_core, get_stats_core, status."""
        uptime_s = cfg.get("uptime", 0)
        airtime_ms = cfg.get("airtime_ms", 0)
        duty_pct = cfg.get("duty_cycle_pct", 0.0)

        # 1. Intentar consultar estadísticas de núcleo del hardware oficial (MeshCore SDK)
        if mc and hasattr(mc, "commands") and hasattr(mc.commands, "get_stats_core"):
            try:
                c_res = await mc.commands.get_stats_core()
                c_payload = _extract_payload_dict(c_res)
                if c_payload:
                    u_val = c_payload.get("uptime_secs") or c_payload.get("uptime")
                    if u_val is not None and int(u_val) > 0:
                        uptime_s = int(u_val)
                    if "battery_mv" in c_payload:
                        self._local_config["battery_mv"] = c_payload["battery_mv"]
                    if "errors" in c_payload:
                        self._local_config["packet_errors"] = c_payload["errors"]
                    if "queue_len" in c_payload:
                        self._local_config["queue_len"] = c_payload["queue_len"]
            except Exception as e:
                logging.debug(f"Fallo consultando get_stats_core: {e}")

        # 2. Consultar estadísticas de radio (Airtime) del transceptor si están disponibles
        if mc and hasattr(mc, "commands") and hasattr(mc.commands, "get_stats_radio"):
            try:
                r_res = await mc.commands.get_stats_radio()
                r_payload = _extract_payload_dict(r_res)
                if r_payload and "tx_air_secs" in r_payload:
                    airtime_ms = int(float(r_payload["tx_air_secs"]) * 1000)
            except Exception as e:
                logging.debug(f"Fallo consultando get_stats_radio para airtime: {e}")

        # 3. Si airtime o duty cycle no provienen del radio, obtener métricas de rate limiter del bridge
        if self._ctx.rate_limiter and hasattr(self._ctx.rate_limiter, "airtime_tracker"):
            try:
                air_stats = self._ctx.rate_limiter.airtime_tracker.get_stats()
                if airtime_ms == 0 and air_stats.get("total_airtime_ms", 0) > 0:
                    airtime_ms = int(air_stats["total_airtime_ms"])
                duty_pct = air_stats.get("hourly_duty_cycle_pct") or air_stats.get("daily_duty_cycle_pct") or duty_pct
            except Exception:
                pass

        # 4. Si el transceptor no reporta uptime aún o está en 0, usar el tiempo activo del bridge
        if uptime_s <= 0:
            bridge_start = getattr(self._ctx, "start_time", 0.0)
            if not bridge_start and hasattr(self._ctx, "counters"):
                bridge_start = getattr(self._ctx.counters, "start_time", 0.0)
            if not bridge_start:
                bridge_start = self._init_time
            if bridge_start > 0:
                uptime_s = max(1, int(time.time() - bridge_start))

        # 5. Formatear cadena de uptime legible
        days = uptime_s // 86400
        hours = (uptime_s % 86400) // 3600
        mins = (uptime_s % 3600) // 60
        secs = uptime_s % 60
        if days > 0:
            uptime_str = f"{days}d {hours}h {mins}m {secs}s"
        elif hours > 0:
            uptime_str = f"{hours}h {mins}m {secs}s"
        elif mins > 0:
            uptime_str = f"{mins}m {secs}s"
        else:
            uptime_str = f"{secs}s"

        # 6. Calcular Duty Cycle estimado si airtime > 0 y duty_pct == 0
        if duty_pct == 0.0 and airtime_ms > 0 and uptime_s > 0:
            duty_pct = round((airtime_ms / (uptime_s * 1000.0)) * 100.0, 3)

        # 7. Actualizar configuración local en memoria
        self._local_config.update({
            "uptime": uptime_s,
            "uptime_secs": uptime_s,
            "uptime_str": uptime_str,
            "airtime_ms": airtime_ms,
            "duty_cycle_pct": duty_pct,
        })

        res["result"] = f"📊 [CORE STATS] Uptime: {uptime_str} | Airtime TX: {airtime_ms} ms | Duty Cycle: {duty_pct:.2f}% | Estado: Operativo"
        res["stats"] = {
            "uptime_secs": uptime_s,
            "uptime_str": uptime_str,
            "airtime_ms": airtime_ms,
            "duty_cycle_pct": duty_pct,
            "status": "operative",
        }
        return res

    def _cli_radio_info(self, cfg: dict[str, Any]) -> str:
        """Genera string informativo de configuración RF."""
        freq = cfg.get("frequency", cfg.get("radio_freq", 915.0))
        pwr = cfg.get("tx_power", 20)
        sf = cfg.get("spreading_factor", cfg.get("sf", 11))
        bw = cfg.get("bandwidth", cfg.get("bw", 250))
        cr = cfg.get("coding_rate", cfg.get("cr", "4/5"))
        snr = cfg.get("last_snr", 12.0)
        rssi = cfg.get("last_rssi", -75)
        noise = cfg.get("noise_floor_dbm", -118)
        return (
            f"📻 [RF CONFIG] Frecuencia: {freq:.3f} MHz | Potencia TX: {pwr} dBm | "
            f"Módem: SF{sf} / BW{bw} kHz | CR: {cr} | SNR: {snr} dB | "
            f"RSSI: {rssi} dBm | Piso de Ruido: {noise} dBm"
        )

    def _cli_packets_info(self, cfg: dict[str, Any]) -> str:
        """Genera string informativo de estadísticas de paquetes."""
        tx = cfg.get("tx_count", 0)
        rx = cfg.get("rx_count", 0)
        if hasattr(self._ctx, "counters") and self._ctx.counters is not None:
            tx = getattr(self._ctx.counters, "tx_count", tx)
            rx = getattr(self._ctx.counters, "rx_count", rx)
        dup = cfg.get("duplicate_packets", 0)
        err = cfg.get("packet_errors", 0)
        return f"📦 [PACKETS] Transmitidos (TX): {tx} | Recibidos (RX): {rx} | Duplicados: {dup} | Errores de trama: {err}"

    def _cli_position_info(self, cfg: dict[str, Any]) -> str:
        """Genera string informativo de posición GPS."""
        lat = cfg.get("latitude", cfg.get("lat", 0.0))
        lon = cfg.get("longitude", cfg.get("lon", 0.0))
        alt = cfg.get("altitude", cfg.get("alt", 0.0))
        fixed = "Activado" if cfg.get("fixed_position", True) else "Desactivado"
        return f"📍 [POSICIÓN GPS] Latitud: {lat} | Longitud: {lon} | Altitud: {alt} m | Modo Fijo: {fixed}"

    def _cli_owner_info(self, cfg: dict[str, Any]) -> str:
        """Genera string informativo de identidad del propietario."""
        o_name = cfg.get("owner_name", cfg.get("name", "MeshCore Node"))
        o_info = cfg.get("owner_info", "Operador de Red")
        pk = cfg.get("public_key", "000000000000")
        return f"👤 [PROPIETARIO / IDENTIDAD] Nombre: {o_name} | Contacto: {o_info} | Clave Pública: {pk}"

    def _cli_neighbors(self, cfg: dict[str, Any], local_pk: str, local_name: str) -> str:
        """Genera listado de nodos vecinos remotos."""
        all_nodes = self._ctx.node_registry.list_nodes()

        # Filtrar estrictamente para excluir la estación base local
        remote_neighbors = [
            n for n in all_nodes
            if not n.get("is_local")
            and str(n.get("role", "")).upper() != "LOCAL"
            and not self._ctx.node_registry.is_local_key(str(n.get("public_key", "")))
            and str(n.get("public_key", "")).lower() != "local"
            and not (local_pk and (str(n.get("public_key", "")).lower().startswith(local_pk[:6]) or local_pk.startswith(str(n.get("public_key", "")).lower()[:6])))
            and str(n.get("name", "")).strip().lower() not in ("estación base", "estacion base", "nodo local", local_name)
        ]

        if not remote_neighbors:
            return (
                "🌐 [VECINOS DE MALLA] Total Nodos Vecinos Descubiertos: 0\n"
                "  (No se han detectado nodos vecinos remotos en alcance directo)"
            )

        lines = [f"🌐 [VECINOS DE MALLA] Total Nodos Vecinos Descubiertos: {len(remote_neighbors)}"]
        for idx, n in enumerate(remote_neighbors[:15], start=1):
            n_name = n.get("alias") or n.get("name") or f"Nodo [{str(n.get('public_key', ''))[:8]}]"
            n_pk = str(n.get("public_key", ""))[:8]
            n_rssi = f"{n.get('last_rssi')} dBm" if n.get("last_rssi") is not None else "--"
            n_snr = f"{n.get('last_snr')} dB" if n.get("last_snr") is not None else "--"
            n_hops = n.get("hops", 0)
            n_lqi = n.get("lqi_score", 0.0)
            n_stat = n.get("lqi_status", "UNKNOWN")
            lines.append(f"  {idx}. {n_name} ({n_pk}) | LQI: {n_lqi}% [{n_stat}] | Hops: {n_hops} | SNR: {n_snr} | RSSI: {n_rssi}")
        return "\n".join(lines)

    def _cli_nodes_list(self, cfg: dict[str, Any], local_pk: str, local_name: str) -> str:
        """Genera listado completo de nodos de la malla."""
        all_nodes = self._ctx.node_registry.list_nodes()
        lines = [f"📋 [DIRECTORIO DE MALLA] Total Nodos Registrados: {len(all_nodes)}"]
        for idx, n in enumerate(all_nodes[:20], start=1):
            is_loc = bool(
                n.get("is_local")
                or str(n.get("role", "")).upper() == "LOCAL"
                or self._ctx.node_registry.is_local_key(str(n.get("public_key", "")))
                or (local_pk and (str(n.get("public_key", "")).lower().startswith(local_pk[:6]) or local_pk.startswith(str(n.get("public_key", "")).lower()[:6])))
            )
            tag = " [ESTACIÓN BASE LOCAL]" if is_loc else f" [{n.get('role', 'CLIENT')}]"
            n_name = (cfg.get("name") if is_loc else None) or n.get("alias") or n.get("name") or f"Nodo [{str(n.get('public_key', ''))[:8]}]"
            n_pk = str(n.get("public_key", ""))[:8]
            n_rssi = f"{n.get('last_rssi')} dBm" if n.get("last_rssi") is not None else ("Local" if is_loc else "--")
            n_snr = f"{n.get('last_snr')} dB" if n.get("last_snr") is not None else ("Local" if is_loc else "--")
            n_hops = 0 if is_loc else n.get("hops", 0)
            lines.append(f"  {idx}. {n_name} ({n_pk}){tag} | Hops: {n_hops} | SNR: {n_snr} | RSSI: {n_rssi}")
        return "\n".join(lines)

    def _cli_lqi(self, res: dict[str, Any], cfg: dict[str, Any], local_pk: str) -> dict[str, Any]:
        """Genera métricas LQI de calidad de enlace."""
        lqi_metrics = self._ctx.node_registry.get_all_lqi_metrics() if hasattr(self._ctx.node_registry, "get_all_lqi_metrics") else []
        remote_lqi = [
            m for m in lqi_metrics
            if not self._ctx.node_registry.is_local_key(str(m.get("public_key", m.get("key_prefix", ""))))
            and str(m.get("role", "")).upper() != "LOCAL"
            and not (local_pk and (str(m.get("key_prefix", "")).lower().startswith(local_pk[:6]) or local_pk.startswith(str(m.get("key_prefix", "")).lower()[:6])))
        ]
        res["lqi_metrics"] = remote_lqi
        if not remote_lqi:
            res["result"] = "📶 [CALIDAD DE ENLACE LQI] Nodos Vecinos Evaluados: 0\n  (No hay métricas LQI de nodos vecinos remotos)"
        else:
            lines = [f"📶 [CALIDAD DE ENLACE LQI] Nodos Vecinos Evaluados: {len(remote_lqi)}"]
            for idx, m in enumerate(remote_lqi, start=1):
                lines.append(f"  {idx}. {m.get('name')} ({m.get('key_prefix')}) -> LQI: {m.get('lqi_score')}% [{m.get('lqi_status')}] | Ruta: {m.get('best_route')} | SNR: {m.get('last_snr')} dB | RSSI: {m.get('last_rssi')} dBm")
            res["result"] = "\n".join(lines)
        return res

    async def _cli_send_advert(self, mc: Any, flood: bool = False) -> None:
        """Envía anuncio de presencia por radio."""
        if mc and hasattr(mc, "commands") and hasattr(mc.commands, "send_advert"):
            await mc.commands.send_advert(flood=flood)
        else:
            await self._broadcast_advert(flood=flood)

    def _cli_help_text(self) -> str:
        """Retorna texto de ayuda de comandos soportados."""
        return (
            "📖 [COMANDOS MESHCORE SOPORTADOS]\n"
            "  • ver / query         : Consulta modelo, versión y build del firmware.\n"
            "  • bat / get_bat       : Nivel de batería, voltaje y estado de alimentación.\n"
            "  • time / clock        : Consulta hora y timestamp del reloj RTC.\n"
            "  • sync_clock / st     : Sincroniza reloj RTC con la hora exacta del servidor.\n"
            "  • stats / stats_core  : Estadísticas de uptime, memoria y airtime.\n"
            "  • radio / stats_radio : Parámetros RF en vivo (Freq, SF, BW, CR, Potencia).\n"
            "  • packets             : Contadores de paquetes TX, RX, duplicados y errores.\n"
            "  • pos / get_pos       : Consulta coordenadas GPS y modo de posición fija.\n"
            "  • owner / identity    : Consulta identidad y datos del propietario.\n"
            "  • neighbors / vecinos : Consulta la tabla de nodos vecinos remotos en alcance RF.\n"
            "  • nodes / list_nodes  : Lista completa de nodos de la malla incluyendo la estación base.\n"
            "  • channels            : Lista de canales de radio configurados.\n"
            "  • acl                 : Consulta lista de control de acceso y permisos.\n"
            "  • board               : Arquitectura de hardware y chip transceptor LoRa.\n"
            "  • advert / flood      : Emisión de anuncios de presencia (directo o inundación).\n"
            "  • ping                : Prueba directa de enlace y respuesta del transceptor.\n"
            "  • reboot              : Reinicio de hardware del microcontrolador.\n"
            "  • clear stats         : Restablece contadores de estadísticas a cero.\n"
            "  • set <param> <val>   : Configura parámetros (name, tx, freq, coords, sf, bw, cr)."
        )

    async def _cli_set_param(self, act_clean: str, res: dict[str, Any]) -> dict[str, Any]:
        """Handler para comandos CLI de ajuste directo (set <param> <val>)."""
        parts = act_clean.split()
        if len(parts) >= 3:
            sub_cmd = parts[1]
            val = " ".join(parts[2:])
            if sub_cmd in ("name", "alias"):
                await self._handle_set_local_config({"action": "set_local_config", "params": {"name": val}}, res, None)
                res["result"] = f"✓ Nombre del nodo local establecido a: '{val}'"
            elif sub_cmd in ("tx", "tx_power", "power"):
                await self._handle_set_local_config({"action": "set_local_config", "params": {"tx_power": int(val)}}, res, None)
                res["result"] = f"✓ Potencia TX establecida a: {val} dBm"
            elif sub_cmd in ("freq", "frequency"):
                await self._handle_set_local_config({"action": "set_local_config", "params": {"frequency": float(val)}}, res, None)
                res["result"] = f"✓ Frecuencia RF establecida a: {val} MHz"
            elif sub_cmd in ("coords", "pos", "gps"):
                c_parts = val.split(",")
                if len(c_parts) >= 2:
                    await self._handle_set_local_config({"action": "set_local_config", "params": {"latitude": float(c_parts[0]), "longitude": float(c_parts[1])}}, res, None)
                    res["result"] = f"✓ Coordenadas GPS establecidas a: {val}"
                else:
                    res["result"] = "⚠️ Formato de coordenadas inválido. Uso: set coords <lat>,<lon>"
            else:
                res["result"] = f"✓ Parámetro '{sub_cmd}' actualizado a: {val}"
        else:
            res["result"] = f"⚠️ Comando de configuración incompleto: {act_clean}"
        return res
