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

/**
 * Clave oficial canónica de canal público por defecto en la pila MeshCore.
 * SSoT: reference/meshcore/docs/companion_protocol.md, faq.md, qr_codes.md
 */
export const MESHCORE_PUBLIC_CHANNEL_SECRET = "8b3387e9c5cdea6ac9e5edbaa115cd72";

/**
 * Mapea el rol de dispositivo a su tipo numérico oficial de MeshCore.
 * SSoT: FirmwareAdvertType (CHAT=1, REPEATER=2, ROOM=3, SENSOR=4).
 * @param {string} role
 * @returns {number}
 */
export function getNumericContactType(role) {
  const r = String(role || "CLIENT").trim().toUpperCase();
  if (r === "REPEATER" || r === "ROUTER") return 2;
  if (r === "ROOM") return 3;
  if (r === "SENSOR") return 4;
  return 1; // CHAT / CLIENT
}

/**
 * Mapea el tipo numérico oficial de MeshCore al rol canónico.
 * @param {number|string} typeNum
 * @returns {string}
 */
export function getRoleFromNumericType(typeNum) {
  const n = parseInt(typeNum, 10);
  if (n === 2) return "REPEATER";
  if (n === 3) return "ROOM";
  if (n === 4) return "SENSOR";
  return "CLIENT";
}

/**
 * Genera un enlace URI canónico oficial para compartir un contacto según la especificación MeshCore.
 * Formato: meshcore://contact/add?name=<name>&public_key=<public_key>&type=<type>
 * @param {string} name
 * @param {string} publicKey
 * @param {string} role
 * @returns {string}
 */
export function buildMeshCoreContactUri(name, publicKey, role = "CLIENT") {
  const cleanName = String(name || "Contact").trim();
  const cleanPk = String(publicKey || "").trim().toLowerCase();
  const typeNum = getNumericContactType(role);
  return `meshcore://contact/add?name=${encodeURIComponent(cleanName)}&public_key=${encodeURIComponent(cleanPk)}&type=${typeNum}`;
}

/**
 * Genera un enlace URI canónico oficial para compartir un canal según la especificación MeshCore.
 * Formato: meshcore://channel/add?name=<name>&secret=<secret>[&index=<index>]
 * @param {string} name
 * @param {string} secret
 * @param {number|null} index
 * @returns {string}
 */
export function buildMeshCoreChannelUri(name, secret = "", index = null) {
  const cleanName = String(name || "Public").trim();
  const rawSec = String(secret || "").trim();
  const cleanSec = (rawSec && rawSec !== "••••••••") ? rawSec.toLowerCase() : MESHCORE_PUBLIC_CHANNEL_SECRET;
  let uri = `meshcore://channel/add?name=${encodeURIComponent(cleanName)}&secret=${encodeURIComponent(cleanSec)}`;
  if (index !== null && index !== undefined && !isNaN(Number(index))) {
    uri += `&index=${Number(index)}`;
  }
  return uri;
}

/**
 * Genera el formato canónico oficial de contacto compartido en un mensaje de chat MeshCore:
 * Formato: <public_key:type:name>
 * Ejemplo: <8d5accef196f5986567b3c7e915fc8e5fc3fe689cadca190d02523aef24b46bc:1:Cu1.mobilUnit>
 * @param {string} name
 * @param {string} publicKey
 * @param {string} role
 * @returns {string}
 */
export function formatMeshCoreContactMessage(name, publicKey, role = "CLIENT") {
  const cleanName = String(name || "Contact").replace(/[<>]/g, "").trim();
  const cleanPk = String(publicKey || "").trim().toLowerCase();
  const typeNum = getNumericContactType(role);
  return `<${cleanPk}:${typeNum}:${cleanName}>`;
}

/**
 * Parsea un enlace URI de MeshCore o un formato de mensaje <pubkey:type:name>.
 * @param {string} rawUri
 * @returns {object|null}
 */
export function parseMeshCoreUri(rawUri) {
  if (!rawUri || typeof rawUri !== "string") return null;
  const str = rawUri.trim();

  // Caso 0: Formato de mensaje MeshCore <pubkey:type:name>
  const tagMatch = str.match(/^<([0-9a-fA-F]{64}):([0-9]+):([^>]+)>$/);
  if (tagMatch) {
    const pk = tagMatch[1].toLowerCase();
    const typeNum = parseInt(tagMatch[2], 10);
    const name = tagMatch[3].trim();
    const role = getRoleFromNumericType(typeNum);
    return {
      type: "contact",
      kind: "contact",
      name,
      public_key: pk,
      pubkey: pk,
      role,
      contact_type: typeNum,
    };
  }

  if (!str.startsWith("meshcore://")) return null;

  // Caso A: Canal (Canónico meshcore://channel/add o legado meshcore://channel?...)
  if (str.includes("channel")) {
    let qs = "";
    const qIdx = str.indexOf("?");
    if (qIdx !== -1) qs = str.slice(qIdx + 1);
    const params = new URLSearchParams(qs);
    const name = params.get("name") || "Canal Importado";
    const secret = params.get("secret") || params.get("psk") || "";
    const idxStr = params.get("index");
    const index = idxStr !== null ? parseInt(idxStr, 10) : null;
    return {
      type: "channel",
      kind: "channel",
      name,
      secret,
      psk: secret,
      index,
    };
  }

  // Caso B: Contacto / Nodo (Canónico meshcore://contact/add o legado meshcore://contact? / meshcore://node?)
  if (str.includes("contact") || str.includes("node")) {
    let qs = "";
    const qIdx = str.indexOf("?");
    if (qIdx !== -1) qs = str.slice(qIdx + 1);
    const params = new URLSearchParams(qs);
    const name = params.get("name") || params.get("alias") || "Contacto Importado";
    const publicKey = (params.get("public_key") || params.get("pubkey") || params.get("key") || "").trim().toLowerCase();
    const typeParam = params.get("type");
    const role = typeParam ? getRoleFromNumericType(typeParam) : (params.get("role") || "CLIENT");
    return {
      type: "contact",
      kind: "contact",
      name,
      public_key: publicKey,
      pubkey: publicKey,
      role,
      contact_type: getNumericContactType(role),
    };
  }

  // Caso C: Tarjeta binaria hexadecimal (meshcore://<hex>)
  const hexPart = str.replace("meshcore://", "").replace(/^\/+/, "");
  if (/^[0-9a-fA-F]{64,}$/.test(hexPart)) {
    return {
      type: "binary_card",
      kind: "binary_card",
      hex: hexPart,
    };
  }

  return null;
}

/**
 * Límite estándar de caracteres/bytes de texto en carga útil de trama LoRa para MeshCore.
 */
export const MAX_LORA_TEXT_BYTES = 160;

/**
 * Calcula la longitud exacta en bytes de una cadena codificada en UTF-8.
 * Permite computar con precisión caracteres multi-byte como emojis (3-4 bytes) y tildes (2 bytes).
 * @param {string} str Cadena de texto
 * @returns {number} Número exacto de bytes en UTF-8
 */
export function getUtf8ByteLength(str) {
  if (!str) return 0;
  if (typeof TextEncoder !== "undefined") {
    return new TextEncoder().encode(str).length;
  }
  let len = 0;
  for (let i = 0; i < str.length; i++) {
    const code = str.charCodeAt(i);
    if (code <= 0x7f) len += 1;
    else if (code <= 0x7ff) len += 2;
    else if (code >= 0xd800 && code <= 0xdbff) {
      len += 4;
      i++;
    } else len += 3;
  }
  return len;
}

/**
 * Calcula el tiempo estimado de transmisión en el aire (Airtime) en milisegundos
 * para una trama de LoRa según la fórmula estándar de Semtech.
 * @param {number} payloadBytes Carga útil en bytes
 * @param {number} sf Spreading Factor (7..12)
 * @param {number} bwKhz Ancho de banda en kHz (125, 250, 500)
 * @param {number} cr Coding Rate denominador (5 para 4/5, 8 para 4/8)
 * @param {number} preamble Símbolos de preámbulo (habitualmente 8)
 * @returns {number} Tiempo en el aire en milisegundos
 */
export function estimateLoraAirtimeMs(payloadBytes, sf = 11, bwKhz = 250, cr = 5, preamble = 8) {
  const bwHz = (Number(bwKhz) || 250) * 1000.0;
  const spreadFactor = Number(sf) || 11;
  const codingRate = Number(cr) || 5;
  const tSymMs = (Math.pow(2, spreadFactor) / bwHz) * 1000.0;
  const tPreambleMs = (preamble + 4.25) * tSymMs;

  const ih = 0;
  const de = (spreadFactor >= 11 && bwHz <= 125000) ? 1 : 0;
  const crcVal = 1;

  const term1 = 8 * payloadBytes - 4 * spreadFactor + 28 + 16 * crcVal - 20 * ih;
  const term2 = 4 * (spreadFactor - 2 * de);
  const payloadSymbolsNum = Math.ceil(term1 / Math.max(1, term2)) * codingRate;
  const symbolCount = 8 + Math.max(0, payloadSymbolsNum);
  const tPayloadMs = symbolCount * tSymMs;

  return Math.max(1, Math.round(tPreambleMs + tPayloadMs));
}

/**
 * Formatea una marca de tiempo para mensajes de chat (Hora, Ayer + Hora, o Fecha + Hora).
 * @param {string|number|Date} timestamp Marca de tiempo ISO, epoch ms o Date
 * @returns {string} Texto formateado
 */
export function formatRelativeTime(timestamp) {
  if (!timestamp) return "";
  const msgDate = new Date(timestamp);
  if (isNaN(msgDate.getTime())) return "";

  const now = new Date();
  const isToday = msgDate.toDateString() === now.toDateString();

  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const isYesterday = msgDate.toDateString() === yesterday.toDateString();

  const timeStr = msgDate.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  if (isToday) {
    return timeStr;
  } else if (isYesterday) {
    const ayerStr = (typeof window !== "undefined" && window.I18n ? window.I18n.t('chat.yesterday') : null) || "Ayer";
    return `${ayerStr} ${timeStr}`;
  } else {
    const dateStr = msgDate.toLocaleDateString([], { day: "2-digit", month: "2-digit", year: "numeric" });
    return `${dateStr} ${timeStr}`;
  }
}

/**
 * Genera la etiqueta del separador de fechas de chat (HOY, AYER o fecha completa).
 * @param {string|number|Date} timestamp Marca de tiempo ISO o ms
 * @returns {string} Etiqueta en mayúsculas
 */
export function getDateGroupLabel(timestamp) {
  if (!timestamp) return "";
  const msgDate = new Date(timestamp);
  if (isNaN(msgDate.getTime())) return "";

  const now = new Date();
  if (msgDate.toDateString() === now.toDateString()) {
    return (typeof window !== "undefined" && window.I18n ? window.I18n.t('chat.date_today') : null) || "HOY";
  }

  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (msgDate.toDateString() === yesterday.toDateString()) {
    return (typeof window !== "undefined" && window.I18n ? window.I18n.t('chat.date_yesterday') : null) || "AYER";
  }

  return msgDate.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" }).toUpperCase();
}

/**
 * Formatea el tiempo transcurrido desde la última señal de un nodo (activo, inactivo, desconectado).
 * @param {number} lastSeen Epoch en segundos o milisegundos
 * @param {boolean} isLocal Indica si corresponde a la estación base local
 * @returns {string} Cadena descriptiva legible
 */
export function formatLastSeen(lastSeen, isLocal = false) {
  if (isLocal) return (typeof window !== "undefined" && window.I18n ? window.I18n.t('time.online_local') : null) || "En línea (Local)";
  if (!lastSeen || lastSeen <= 0) return (typeof window !== "undefined" && window.I18n ? window.I18n.t('time.offline_no_signal') : null) || "Desconectado (Sin señal)";
  let effTs = Number(lastSeen);
  if (effTs > 1e11) effTs = Math.floor(effTs / 1000);
  let diff = Math.floor(Date.now() / 1000) - effTs;
  if (diff < 0) diff = 0;

  if (diff < 60) {
    return (typeof window !== "undefined" && window.I18n ? window.I18n.t('time.active_now') : null) || "Activo (ahora mismo)";
  }
  if (diff < 1800) {
    const mins = Math.max(1, Math.floor(diff / 60));
    const str = typeof window !== "undefined" && window.I18n ? window.I18n.t('time.active_mins') : null;
    return str ? str.replace('{n}', mins) : `Activo (hace ${mins}m)`;
  }
  if (diff < 7200) {
    const mins = Math.floor(diff / 60);
    if (mins < 60) {
      const str = typeof window !== "undefined" && window.I18n ? window.I18n.t('time.idle_mins') : null;
      return str ? str.replace('{n}', mins) : `Inactivo (hace ${mins}m)`;
    }
    const hours = Math.floor(diff / 3600);
    const str = typeof window !== "undefined" && window.I18n ? window.I18n.t('time.idle_hours') : null;
    return str ? str.replace('{n}', hours) : `Inactivo (hace ${hours}h)`;
  }
  if (diff < 86400) {
    const hours = Math.floor(diff / 3600);
    const str = typeof window !== "undefined" && window.I18n ? window.I18n.t('time.offline_hours') : null;
    return str ? str.replace('{n}', hours) : `Desconectado (hace ${hours}h)`;
  }
  const days = Math.max(1, Math.floor(diff / 86400));
  const str = typeof window !== "undefined" && window.I18n ? window.I18n.t('time.offline_days') : null;
  return str ? str.replace('{n}', days) : `Desconectado (hace ${days}d)`;
}

/**
 * Calcula la clase CSS de estado de presencia de un nodo (status-online, status-idle, status-offline).
 * @param {number} lastSeen Epoch en segundos o milisegundos
 * @param {boolean} isLocal Indica si es el nodo local
 * @returns {string} Clase CSS de estado
 */
export function getPresenceState(lastSeen, isLocal = false) {
  if (isLocal) return "status-online";
  if (!lastSeen || lastSeen <= 0) return "status-offline";
  let effTs = Number(lastSeen);
  if (effTs > 1e11) effTs = Math.floor(effTs / 1000);
  let diff = Math.floor(Date.now() / 1000) - effTs;
  if (diff < 0) diff = 0;

  if (diff < 1800) return "status-online";
  if (diff < 7200) return "status-idle";
  return "status-offline";
}

