/**
 * ReactiveStore - Almacén de Estado Reactivo Ligero y Desacoplado.
 * Implementado sobre Proxy y EventTarget nativos del navegador (W3C Standard).
 * Cero dependencias externas; ultra-rápido para hardware embebido (SBCs / Raspberry Pi).
 */

export class ReactiveStore {
  /**
   * @param {Record<string, any>} initialState Estado inicial del almacén.
   */
  constructor(initialState = {}) {
    this._target = new EventTarget();
    this._rawState = { ...initialState };

    // Proxy reactivo que intercepta mutaciones y despacha eventos de cambio
    this.state = new Proxy(this._rawState, {
      set: (target, prop, value) => {
        const oldValue = target[prop];
        if (oldValue === value) return true;

        target[prop] = value;

        // Despachar evento específico para la propiedad mutada
        this._target.dispatchEvent(
          new CustomEvent(`change:${String(prop)}`, {
            detail: { prop, value, oldValue },
          })
        );

        // Despachar evento global de cambio de estado
        this._target.dispatchEvent(
          new CustomEvent("change", {
            detail: { prop, value, oldValue },
          })
        );

        return true;
      },
      get: (target, prop) => {
        return target[prop];
      },
    });
  }

  /**
   * Obtiene el valor actual de una propiedad del estado.
   * @param {string} prop Nombre de la propiedad.
   * @returns {any} Valor actual.
   */
  get(prop) {
    return this.state[prop];
  }

  /**
   * Actualiza el valor de una propiedad del estado.
   * @param {string} prop Nombre de la propiedad.
   * @param {any} value Nuevo valor.
   */
  set(prop, value) {
    this.state[prop] = value;
  }

  /**
   * Actualiza múltiples propiedades de forma atómica.
   * @param {Record<string, any>} patch Objeto con propiedades a actualizar.
   */
  setMany(patch) {
    if (!patch || typeof patch !== "object") return;
    for (const [k, v] of Object.entries(patch)) {
      this.state[k] = v;
    }
  }

  /**
   * Suscribe un listener a cambios en una propiedad específica del estado.
   * @param {string} prop Nombre de la propiedad a observar.
   * @param {(newValue: any, oldValue: any) => void} callback Función invocada al cambiar la propiedad.
   * @returns {() => void} Función para cancelar la suscripción.
   */
  subscribe(prop, callback) {
    const handler = (e) => {
      callback(e.detail.value, e.detail.oldValue);
    };
    const eventName = `change:${prop}`;
    this._target.addEventListener(eventName, handler);
    return () => this._target.removeEventListener(eventName, handler);
  }

  /**
   * Suscribe un listener a cualquier cambio en el estado global.
   * @param {(prop: string, newValue: any, oldValue: any) => void} callback Función invocada en cualquier mutación.
   * @returns {() => void} Función para cancelar la suscripción.
   */
  subscribeAll(callback) {
    const handler = (e) => {
      callback(e.detail.prop, e.detail.value, e.detail.oldValue);
    };
    this._target.addEventListener("change", handler);
    return () => this._target.removeEventListener("change", handler);
  }

  /**
   * Retorna una instantánea inmutable (shallow copy) del estado actual.
   * @returns {Record<string, any>} Copia del estado.
   */
  snapshot() {
    return { ...this._rawState };
  }
}

/**
 * Instancia singleton compartida por defecto con el esquema canónico de MeshCore Bridge.
 */
export const store = new ReactiveStore({
  wsConnected: false,
  radioConnected: false,
  radioPort: "",
  activeTab: "tab-chat",
  activeChannelIdx: 0,
  activeDmTarget: null,
  airtimeDutyCycle: 0,
  airtimeMs: 0,
  knownNodesCount: 0,
  theme: "dark",
  unreadCount: 0,
});
