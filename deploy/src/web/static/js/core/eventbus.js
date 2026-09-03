/**
 * EventBus - Bus de eventos asíncrono desacoplado para MeshCore Station SPA.
 * Basado en EventTarget nativo y CustomEvent del navegador.
 */

export class EventBus {
  constructor() {
    this._target = new EventTarget();
  }

  /**
   * Suscribe un listener a un tipo de evento.
   * @param {string} eventName Nombre del evento
   * @param {Function} handler Función callback (recibe detail como argumento)
   * @returns {Function} Función para cancelar la suscripción
   */
  on(eventName, handler) {
    const wrappedHandler = (e) => handler(e.detail);
    this._target.addEventListener(eventName, wrappedHandler);
    return () => this._target.removeEventListener(eventName, wrappedHandler);
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
   * @param {string} eventName Nombre del evento
   * @param {Function} handler Función callback
   */
  once(eventName, handler) {
    const wrappedHandler = (e) => handler(e.detail);
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
});
