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
    this._isBatching = false;
    this._batchChanges = [];

    // Proxy reactivo que intercepta mutaciones y despacha eventos de cambio
    this.state = new Proxy(this._rawState, {
      set: (target, prop, value) => {
        const oldValue = target[prop];
        if (oldValue === value) return true;

        target[prop] = value;

        if (this._isBatching) {
          this._batchChanges.push({ prop, value, oldValue });
          return true;
        }

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
   * Ejecuta una serie de mutaciones agrupadas de forma atómica.
   * Emite un único evento global 'change' al finalizar el bloque de ejecución.
   * @param {() => void} fn Función con las mutaciones a ejecutar.
   */
  batch(fn) {
    if (this._isBatching) {
      fn();
      return;
    }
    this._isBatching = true;
    this._batchChanges = [];
    try {
      fn();
    } finally {
      this._isBatching = false;
      const changes = [...this._batchChanges];
      this._batchChanges = [];
      if (changes.length > 0) {
        for (const change of changes) {
          this._target.dispatchEvent(
            new CustomEvent(`change:${String(change.prop)}`, {
              detail: change,
            })
          );
        }
        this._target.dispatchEvent(
          new CustomEvent("change", {
            detail: { batch: true, changes, snapshot: this.snapshot() },
          })
        );
      }
    }
  }

  /**
   * Actualiza múltiples propiedades de forma atómica.
   * @param {Record<string, any>} patch Objeto con propiedades a actualizar.
   */
  setMany(patch) {
    if (!patch || typeof patch !== "object") return;
    this.batch(() => {
      for (const [k, v] of Object.entries(patch)) {
        this.state[k] = v;
      }
    });
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
   * Retorna una instantánea inmutable (deep clone) del estado actual.
   * @returns {Record<string, any>} Copia profunda del estado.
   */
  snapshot() {
    try {
      return structuredClone(this._rawState);
    } catch (_) {
      return JSON.parse(JSON.stringify(this._rawState));
    }
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
  channels: [],
  stationConfig: {},
  stationStatus: {},
  servicesConfig: {},
});
