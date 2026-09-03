/**
 * Funciones de utilidad y constantes canónicas para MeshCore Station.
 */

// Límites de capacidad en RAM para ring-buffers
export const MAX_RAW_PACKETS = 200;
export const MAX_SYSTEM_LOGS = 300;
export const MAX_FEED_MESSAGES = 100;

// Mapeo canónico de frecuencias por región de radio
export const REGION_FREQUENCIES = Object.freeze({
  "US915": "915.000",
  "EU868": "868.000",
  "AU915": "915.000",
  "AS923": "923.000",
  "IN865": "865.000",
  "RU864": "864.000",
});

// Eventos de telemetría y control excluidos del feed de chat (O(1) Set lookup)
export const NON_CHAT_EVENT_TYPES = new Set([
  "repeater_response", "repeater_telemetry", "advert", "node_advert",
  "node_discovered", "contact_discovered", "contact_updated", "contacts_updated",
  "channels_updated", "message_delivered", "trace_data", "system_log",
  "metrics_update", "rf_log", "telemetry", "stats_radio", "stats_core", "ack", "trace"
]);

// Prefijos de comandos/errores CLI de firmware para filtrar ruido de consola
export const KNOWN_CLI_SYSTEM_PREFIXES = [
  "unknown command",
  "error: unknown command",
  "error unknown command",
  "invalid command",
  "cmd ",
  "login ",
  "auth ",
  "stats-",
  "stats_",
  "logging off",
  "log erased",
  "welcome admin",
  "access denied",
  "bad pin",
  "wrong password",
  "incorrect password",
  "permission denied",
  "not logged in",
];

/**
 * Función de sanitización XSS estricta para escape en el DOM.
 * @param {string} str Cadena a sanitizar
 * @returns {string} Cadena sanitizada
 */
export function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/**
 * Utilidad de debouncing para optimizar inputs de búsqueda en tiempo real.
 */
export function debounce(fn, waitMs = 150) {
  let timer = null;
  return function(...args) {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      fn.apply(this, args);
    }, waitMs);
  };
}

/**
 * Retorna las cabeceras HTTP necesarias incluyendo X-Api-Key si está configurada.
 */
export function getAuthHeaders(customHeaders = {}) {
  const headers = { "Content-Type": "application/json", ...customHeaders };
  const apiKey = (localStorage.getItem("meshcore_bridge_api_key") || "").trim();
  if (apiKey) {
    headers["X-Api-Key"] = apiKey;
  }
  return headers;
}

/**
 * Extrae el nombre de remitente y el texto limpio de un mensaje si viene con formato 'Nombre: Texto'.
 */
export function extractSenderAndText(text, currentSenderName = null) {
  if (!text || typeof text !== "string") {
    return { senderName: currentSenderName || "Anónimo", cleanText: text || "" };
  }
  const trimmed = text.trim();

  // 1. Si coincide con el nombre de remitente actual al inicio
  if (currentSenderName && typeof currentSenderName === "string") {
    const sName = currentSenderName.trim();
    if (sName && sName.toLowerCase() !== "unknown" && sName.toLowerCase() !== "anónimo" && sName.toLowerCase() !== "anonimo") {
      const escaped = sName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const namePrefixRegex = new RegExp(`^(?:\\[${escaped}\\]|<${escaped}>|${escaped})\\s*:\\s*([\\s\\S]*)$`, "i");
      const nameMatch = trimmed.match(namePrefixRegex);
      if (nameMatch) {
        const actual = nameMatch[1].trim();
        if (!actual.startsWith("//")) {
          return {
            senderName: currentSenderName,
            cleanText: actual || trimmed
          };
        }
      }
    }
  }

  // 2. Patrón general 'Nombre: Mensaje' o '[Nombre]: Mensaje'
  const match = trimmed.match(/^(?:\[([a-zA-Z0-9_\-\.]{2,32})\]|<([a-zA-Z0-9_\-\.]{2,32})>|([a-zA-Z0-9_\-\.]{2,32})):\s*([\s\S]*)$/);
  if (match) {
    const candidateName = (match[1] || match[2] || match[3] || "").trim();
    const actualText = (match[4] || "").trim();
    const lowerCandidate = candidateName.toLowerCase();
    if (!actualText.startsWith("//") && !["http", "https", "ftp", "ws", "wss", "json", "data", "cmd", "r", "ack", "req", "res", "echo", "status", "meshcore", "loc"].includes(lowerCandidate)) {
      const isUnknown = !currentSenderName ||
        currentSenderName.toLowerCase() === "unknown" ||
        currentSenderName.toLowerCase() === "anónimo" ||
        currentSenderName.toLowerCase() === "anonimo" ||
        currentSenderName.startsWith("Node_unknow") ||
        currentSenderName.length >= 12;
      return {
        senderName: isUnknown ? candidateName : currentSenderName,
        cleanText: actualText || trimmed
      };
    }
  }
  return {
    senderName: currentSenderName && currentSenderName.toLowerCase() !== "unknown" ? currentSenderName : "Anónimo",
    cleanText: trimmed
  };
}

/**
 * Valida si un texto es un comando de sistema o error de consola CLI.
 */
export function isCommandOrSystemText(text, txtType = 0) {
  if (txtType === 1 || txtType === 2) return true;
  if (!text || typeof text !== "string") return true;

  const clean = text.trim();
  if (!clean) return true;

  let cleanLower = clean.toLowerCase();
  if (cleanLower.startsWith("->") || cleanLower.startsWith("- >") || cleanLower.startsWith(">")) {
    cleanLower = cleanLower.replace(/^[- >]+/, "").trim();
  }

  return KNOWN_CLI_SYSTEM_PREFIXES.some((prefix) => cleanLower.startsWith(prefix));
}

/**
 * Determina si una trama de evento recibida es un mensaje de chat común.
 */
export function isCommonChatMessage(payload) {
  if (!payload || typeof payload !== "object") return false;

  const evType = String(payload.event_type || payload.type || "");
  if (NON_CHAT_EVENT_TYPES.has(evType)) {
    return false;
  }

  const isChatType = (
    evType === "public" ||
    evType === "channel" ||
    evType === "direct" ||
    payload.type === "CHANNEL_MSG" ||
    payload.type === "DIRECT_MSG"
  );

  if (!isChatType) {
    return false;
  }

  const txtType = Number(payload.txt_type ?? payload.text_type ?? 0);
  if (txtType === 1) {
    return false;
  }

  const text = String(payload.text || payload.message || "").trim();
  if (!text) {
    return false;
  }

  return true;
}

/**
 * Calcula los límites mínimo, máximo y por defecto de potencia TX según el hardware del nodo.
 */
export function getHardwarePowerLimits(node) {
  if (!node) return { min: 2, max: 22, def: 20 };
  if (typeof node.max_tx_power === "number" && node.max_tx_power > 0) {
    const minP = typeof node.min_tx_power === "number" ? node.min_tx_power : (node.max_tx_power >= 30 ? 10 : (node.max_tx_power <= 14 ? 0 : 2));
    return { min: minP, max: node.max_tx_power, def: Math.min(20, node.max_tx_power) };
  }
  const hw = String(node.hardware_board || node.hw_model_name || node.hw_model || node.model || node.board || "").toUpperCase();
  if (hw.includes("30DBM") || hw.includes("E22") || hw.includes("PA") || hw.includes("PLUS") || hw.includes("HIGH_POWER")) {
    return { min: 10, max: 30, def: 27 };
  }
  if (hw.includes("V2") || hw.includes("V1") || hw.includes("SX1276") || hw.includes("SX1278") || hw.includes("M5STACK") || hw.includes("TLORA")) {
    return { min: 2, max: 20, def: 17 };
  }
  if (hw.includes("CC1352") || hw.includes("LOW_POWER")) {
    return { min: 0, max: 14, def: 10 };
  }
  return { min: 2, max: 22, def: 20 };
}

