/**
 * PacketWorker - Web Worker para procesamiento, filtrado y analítica de tramas LoRa.
 * Ejecuta cómputos de filtrado y búsqueda en un hilo separado para mantener
 * el procesamiento fuera del event loop de la interfaz ante ráfagas de paquetes RF.
 * Estándar W3C nativo, sin dependencias externas.
 */

"use strict";

self.onmessage = function (e) {
  if (!e.data || typeof e.data !== "object") return;
  const { id, action, payload } = e.data;

  try {
    switch (action) {
      case "filter": {
        const { packets, filters } = payload || {};
        const result = filterPackets(packets || [], filters || {});
        self.postMessage({ id, action, success: true, result });
        break;
      }

      case "stats": {
        const { packets } = payload || {};
        const stats = computePacketStats(packets || []);
        self.postMessage({ id, action, success: true, result: stats });
        break;
      }

      case "ping": {
        self.postMessage({ id, action, success: true, result: "pong" });
        break;
      }

      default:
        self.postMessage({
          id,
          action,
          success: false,
          error: `Acción desconocida: ${action}`,
        });
    }
  } catch (err) {
    self.postMessage({
      id,
      action,
      success: false,
      error: err && err.message ? err.message : String(err),
    });
  }
};

/**
 * Filtra la colección de paquetes RF de acuerdo a los criterios proporcionados.
 */
function filterPackets(packets, filters) {
  const dirFilter = (filters.dirFilter || "").toLowerCase().trim();
  const typeFilter = (filters.typeFilter || "").toUpperCase().trim();
  const searchQuery = (filters.searchQuery || "").toLowerCase().trim();

  return packets.filter((pkt) => {
    if (!pkt || typeof pkt !== "object") return false;

    if (dirFilter) {
      const pktDir = (pkt.direction || "").toLowerCase();
      if (pktDir !== dirFilter) return false;
    }

    if (typeFilter) {
      const pktType = (pkt.packet_type || "").toUpperCase();
      if (!pktType.includes(typeFilter)) return false;
    }

    if (searchQuery) {
      const sSender = pkt.sender || "";
      const sSenderName = pkt.sender_name || "";
      const sTarget = pkt.target || "";
      const sText = pkt.text || "";
      const sType = pkt.packet_type || "";
      const fullSearchTarget = `${sSender} ${sSenderName} ${sTarget} ${sText} ${sType}`.toLowerCase();
      if (!fullSearchTarget.includes(searchQuery)) return false;
    }

    return true;
  });
}

/**
 * Computa estadísticas acumuladas sobre un lote de tramas RF.
 */
function computePacketStats(packets) {
  let rxCount = 0;
  let txCount = 0;
  let totalBytes = 0;
  let sumSnr = 0;
  let countSnr = 0;
  let sumRssi = 0;
  let countRssi = 0;
  const types = {};

  for (let i = 0; i < packets.length; i++) {
    const pkt = packets[i];
    if (!pkt) continue;

    const dir = (pkt.direction || "").toLowerCase();
    if (dir === "rx") rxCount++;
    else if (dir === "tx") txCount++;

    if (typeof pkt.size_bytes === "number") {
      totalBytes += pkt.size_bytes;
    }

    if (typeof pkt.snr === "number" && !isNaN(pkt.snr)) {
      sumSnr += pkt.snr;
      countSnr++;
    }

    if (typeof pkt.rssi === "number" && !isNaN(pkt.rssi)) {
      sumRssi += pkt.rssi;
      countRssi++;
    }

    const type = (pkt.packet_type || "UNKNOWN").toUpperCase();
    types[type] = (types[type] || 0) + 1;
  }

  return {
    totalPackets: packets.length,
    rxCount,
    txCount,
    totalBytes,
    avgSnr: countSnr > 0 ? +(sumSnr / countSnr).toFixed(2) : null,
    avgRssi: countRssi > 0 ? +(sumRssi / countRssi).toFixed(1) : null,
    byType: types,
  };
}
