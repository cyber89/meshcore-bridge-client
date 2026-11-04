/**
 * EventBus - Bus de eventos asíncrono desacoplado para MeshCore Station SPA.
 * Basado en EventTarget nativo y CustomEvent del navegador.
 */

export class EventBus {
  constructor() {
    this._target = new EventTarget();
    this._handlers = new Map();
  }

  /**
   * Suscribe un listener a un tipo de evento.
   * @param {string} eventName Nombre del evento
   * @param {Function} handler Función callback (recibe detail como argumento)
   * @returns {Function} Función para cancelar la suscripción
   */
  on(eventName, handler) {
    if (!this._handlers.has(eventName)) {
      this._handlers.set(eventName, new Map());
    }
    const wrappedHandler = (e) => handler(e.detail);
    this._handlers.get(eventName).set(handler, wrappedHandler);
    this._target.addEventListener(eventName, wrappedHandler);
    return () => this.off(eventName, handler);
  }

  /**
   * Desuscribe un listener de un tipo de evento.
   * @param {string} eventName Nombre del evento
   * @param {Function} handler Función callback original
   */
  off(eventName, handler) {
    if (!this._handlers.has(eventName)) return;
    const eventMap = this._handlers.get(eventName);
    const wrappedHandler = eventMap.get(handler);
    if (wrappedHandler) {
      this._target.removeEventListener(eventName, wrappedHandler);
      eventMap.delete(handler);
    }
  }

  /**
   * Emite un evento con datos asociados.
   * @param {string} eventName Nombre del evento
   * @param {any} detail Carga útil del evento
   */
  emit(eventName, detail) {
    this._target.dispatchEvent(new CustomEvent(eventName, { detail }));
  }

  /**
   * Escucha un evento exactamente una vez.
   * API pública conservada para integraciones; la SPA actual usa on().
   * @param {string} eventName Nombre del evento
   * @param {Function} handler Función callback
   */
  once(eventName, handler) {
    const wrappedHandler = (e) => {
      this.off(eventName, handler);
      handler(e.detail);
    };
    if (!this._handlers.has(eventName)) {
      this._handlers.set(eventName, new Map());
    }
    this._handlers.get(eventName).set(handler, wrappedHandler);
    this._target.addEventListener(eventName, wrappedHandler, { once: true });
  }
}

// Instancia singleton compartida por defecto
export const eventBus = new EventBus();

// Nombres canónicos de eventos para autocompletado y desacoplamiento
export const EVENTS = Object.freeze({
  WS_STATUS_CHANGE: "meshcore:ws_status_change",
  RADIO_STATUS_CHANGE: "meshcore:radio_status_change",
  RX_PACKET: "meshcore:rx_packet",
  TX_STATUS: "meshcore:tx_status",
  NODE_DISCOVERED: "meshcore:node_discovered",
  NODE_UPDATED: "meshcore:node_updated",
  CHAT_MESSAGE_RECV: "meshcore:chat_message_recv",
  FEED_CHANGED: "meshcore:feed_changed",
  TAB_CHANGED: "meshcore:tab_changed",
  HEATMAP_UPDATED: "meshcore:heatmap_updated",
  SETTINGS_SAVED: "meshcore:settings_saved",
  SYSTEM_LOG_RECV: "meshcore:system_log_recv",
  SYSTEM_LOG: "meshcore:system_log",
  LOGS_CLEARED: "meshcore:logs_cleared",
  METRICS_UPDATE: "meshcore:metrics_update",
  RF_PACKET: "meshcore:rf_packet",
  DUTY_CYCLE_ALERT: "meshcore:duty_cycle_alert",
  AIRTIME_CUTOFF_CHANGE: "meshcore:airtime_cutoff_change",
  VISIBILITY_CHANGED: "meshcore:visibility_changed",
  CHANNELS_UPDATED: "meshcore:channels_updated",
  CONTACTS_UPDATED: "meshcore:contacts_updated",
  CONFIG_UPDATED: "meshcore:config_updated",
  MESSAGE_STATUS: "meshcore:message_status",
});
