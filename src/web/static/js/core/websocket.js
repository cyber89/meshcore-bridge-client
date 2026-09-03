/**
 * MeshCoreWebSocketClient - Cliente WebSocket resiliente con reconexión exponencial y keepalive.
 * Emite eventos a través del EventBus desacoplado.
 */

import { EVENTS } from "./eventbus.js";

export class MeshCoreWebSocketClient {
  constructor(eventBus, path = "/ws") {
    this.eventBus = eventBus;
    this.path = path;
    this.ws = null;
    this.reconnectTimer = null;
    this.heartbeatInterval = null;
    this.reconnectDelay = 1000;
    this.maxReconnectDelay = 30000;
    this.status = "disconnected";
  }

  connect() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}${this.path}`;

    if (this.ws) {
      try {
        this.ws.onclose = null;
        this.ws.onerror = null;
        this.ws.close();
      } catch (_) {}
    }

    this._setStatus("connecting");

    try {
      this.ws = new WebSocket(wsUrl);
    } catch (err) {
      console.warn("Error creando WebSocket:", err);
      this._scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.reconnectDelay = 1000;
      this._setStatus("connected");
      this._startHeartbeat();
    };

    this.ws.onclose = () => {
      this._stopHeartbeat();
      this._scheduleReconnect();
    };

    this.ws.onerror = (e) => {
      console.warn("WS error:", e);
    };

    this.ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload && (payload.type === "pong" || payload.event_type === "pong")) return;
        this.eventBus.emit(EVENTS.RX_PACKET, payload);
      } catch (err) {
        console.error("Error parseando WebSocket payload:", err);
      }
    };
  }

  send(data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      const msg = typeof data === "string" ? data : JSON.stringify(data);
      this.ws.send(msg);
      return true;
    }
    return false;
  }

  close() {
    this._stopHeartbeat();
    clearTimeout(this.reconnectTimer);
    if (this.ws) {
      try {
        this.ws.onclose = null;
        this.ws.close();
      } catch (_) {}
      this.ws = null;
    }
    this._setStatus("disconnected");
  }

  _setStatus(newStatus) {
    this.status = newStatus;
    this.eventBus.emit(EVENTS.WS_STATUS_CHANGE, newStatus);
  }

  _scheduleReconnect() {
    this._setStatus("reconnecting");
    clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => this.connect(), this.reconnectDelay);
    this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
  }

  _startHeartbeat() {
    this._stopHeartbeat();
    this.heartbeatInterval = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        try {
          this.ws.send(JSON.stringify({ type: "ping", timestamp: Date.now() }));
        } catch (_) {}
      }
    }, 15000);
  }

  _stopHeartbeat() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }
}
