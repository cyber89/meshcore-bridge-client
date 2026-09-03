/**
 * i18n.js — MeshCore Bridge Internationalization
 * ─────────────────────────────────────────────
 * Selector-based approach: no data-i18n attributes needed in HTML.
 * Exposes window.I18n = { t, apply, toggle, lang }
 *
 * Supported languages: 'es' (default), 'en'
 * Persistence: localStorage key 'mc_lang'
 * Auto-detection: navigator.language prefix
 */
(function () {
  'use strict';

  // ── Translation Dictionaries ────────────────────────────────────────────────
  const DICT = {
    es: {
      // Navigation
      'nav.chat':       'Mensajería',
      'nav.contacts':   'Contactos',
      'nav.nodes':      'Nodos',
      'nav.map':        'Mapa',
      'nav.analytics':  'Métricas',
      'nav.logs':       'Logs Sistema',
      'nav.settings':   'Ajustes',
      'nav.collapse':   'Colapsar',
      'nav.expand':     'Expandir',

      // Status bar
      'status.radio_connected':    'Radio: Conectada',
      'status.radio_disconnected': 'Radio: Desconectada',
      'status.radio_connecting':   'Radio: Conectando…',
      'status.ws_connected':       'Web: Conectado',
      'status.ws_disconnected':    'Web: Desconectado',
      'status.ws_connecting':      'Web: Conectando…',

      // Global search
      'search.global_placeholder': 'Buscar nodo, comando o canal...',

      // Chat section
      'chat.channels':             'Canales',
      'chat.direct_messages':      'Mensajes Directos',
      'chat.no_conversations':     'Sin conversaciones activas',
      'chat.send':                 'Enviar',
      'chat.clear':                'Limpiar',
      'chat.input_placeholder':    'Escribe un mensaje para transmitir por RF...',
      'chat.open':                 'Canales',

      // Nodes section
      'nodes.title':               'Directorio de Nodos en la Malla',
      'nodes.subtitle':            'Todos los nodos descubiertos en la red LoRa MeshCore con su telemetría y estado en vivo.',
      'nodes.search_placeholder':  'Buscar nodo por nombre, alias, rol o clave pública...',
      'nodes.filter_all':          'Todos',
      'nodes.filter_repeaters':    'Repetidores',
      'nodes.filter_sensors':      'Sensores',
      'nodes.filter_rooms':        'Salas',
      'nodes.filter_clients':      'Clientes',
      'nodes.discovering':         'Descubriendo nodos en la malla LoRa...',

      // Contacts section
      'contacts.title':            'Libreta de Contactos',
      'contacts.subtitle':         'Directorio de contactos, nodos amigos y gestión de claves públicas de la red.',
      'contacts.refresh':          'Actualizar',
      'contacts.add':              'Agregar Contacto',
      'contacts.search_placeholder': 'Buscar contacto por nombre, alias o clave pública...',
      'contacts.filter_all':       'Todos',
      'contacts.filter_favorites': 'Favoritos',
      'contacts.filter_online':    'En Línea',
      'contacts.filter_gps':       'Con Posición',
      'contacts.loading':          'Buscando contactos en el dispositivo...',
      'contacts.accept_all':       'Aceptar Todos',

      // Map section
      'map.dark':       'Oscuro',
      'map.streets':    'Calles',
      'map.satellite':  'Satelital',
      'map.local':      'Local',
      'map.radar':      'Radar',
      'map.heatmap':    'Heatmap RF',
      'map.nodes_title':'Nodos en Malla',

      // Analytics section
      'analytics.title':           'Métricas & Analítica de la Red Malla',
      'analytics.subtitle':        'Monitoreo de tráfico RF, calidad de enlace SNR/RSSI, estadísticas de repetidores y salud del puente.',
      'analytics.refresh':         'Actualizar Métricas',
      'analytics.kpi_packets':     'Paquetes Totales Malla',
      'analytics.kpi_nodes':       'Nodos Activos Registrados',
      'analytics.kpi_error_rate':  'Tasa de Error Global',
      'analytics.kpi_queue':       'Cola de Transmisión TX',
      'analytics.top_active':      'Top Nodos Más Activos',
      'analytics.top_active_sub':  'Nodos con mayor volumen de paquetes transmitidos y recibidos',
      'analytics.signal':          'Calidad de Señal RF (SNR)',
      'analytics.signal_sub':      'Ranking de mejor y peor relación señal/ruido en la malla',
      'analytics.repeaters':       'Top Routers & Repetidores',
      'analytics.repeaters_sub':   'Nodos de infraestructura y clientes enrutados',
      'analytics.bridge':          'Salud del Puente & Rendimiento',

      // Logs section
      'logs.title':                'Consola de Logs del Sistema',
      'logs.subtitle':             'Registro de eventos del puente MeshCore: conexiones, errores, tráfico serial y actividad MQTT.',
      'logs.clear':                'Limpiar Logs',
      'logs.export':               'Exportar',
      'logs.pause':                'Pausar',
      'logs.resume':               'Reanudar',

      // Settings section
      'settings.title':            'Ajustes & Configuración',
      'settings.subtitle':         'Parámetros del puente serial, MQTT, radio LoRa y preferencias de la interfaz web.',
      'settings.save':             'Guardar Configuración',
      'settings.reset':            'Restablecer',

      // Node card (dynamic)
      'node.battery':      'Batería',
      'node.rssi':         'RSSI',
      'node.snr':          'SNR',
      'node.hops':         'Hops',
      'node.last_seen':    'Último contacto',
      'node.send_dm':      'DM',
      'node.admin':        'Administrar',
      'node.ping':         'Ping',
      'node.traceroute':   'Traceroute',
      'node.role_client':  'Cliente',
      'node.role_repeater':'Repetidor',
      'node.role_sensor':  'Sensor',
      'node.role_room':    'Sala',
      'node.role_local':   'Local',
      'node.role_unknown': 'Desconocido',
      'node.unknown':      'Desconocido',
      'node.never':        'Nunca',
      'node.voltage':      'Voltaje',
      'node.lat':          'Lat',
      'node.lon':          'Lon',
      'node.no_gps':       'Sin GPS',

      // Modal / Common
      'modal.close':       'Cerrar',
      'modal.confirm':     'Confirmar',
      'modal.cancel':      'Cancelar',
      'modal.save':        'Guardar',
      'modal.send':        'Enviar',
      'modal.copy':        'Copiar',
      'modal.delete':      'Eliminar',
      'modal.edit':        'Editar',
      'modal.loading':     'Cargando...',
      'modal.error':       'Error',
      'modal.success':     'Éxito',
      'modal.yes':         'Sí',
      'modal.no':          'No',

      // Language toggle
      'lang.current':      'ES',
      'lang.switch':       '🌐 EN',
      'lang.title':        'Switch to English',
    },

    en: {
      // Navigation
      'nav.chat':       'Messaging',
      'nav.contacts':   'Contacts',
      'nav.nodes':      'Nodes',
      'nav.map':        'Map',
      'nav.analytics':  'Metrics',
      'nav.logs':       'System Logs',
      'nav.settings':   'Settings',
      'nav.collapse':   'Collapse',
      'nav.expand':     'Expand',

      // Status bar
      'status.radio_connected':    'Radio: Connected',
      'status.radio_disconnected': 'Radio: Disconnected',
      'status.radio_connecting':   'Radio: Connecting…',
      'status.ws_connected':       'Web: Connected',
      'status.ws_disconnected':    'Web: Disconnected',
      'status.ws_connecting':      'Web: Connecting…',

      // Global search
      'search.global_placeholder': 'Search node, command or channel...',

      // Chat section
      'chat.channels':             'Channels',
      'chat.direct_messages':      'Direct Messages',
      'chat.no_conversations':     'No active conversations',
      'chat.send':                 'Send',
      'chat.clear':                'Clear',
      'chat.input_placeholder':    'Type a message to transmit via RF...',
      'chat.open':                 'Channels',

      // Nodes section
      'nodes.title':               'Mesh Node Directory',
      'nodes.subtitle':            'All nodes discovered in the MeshCore LoRa network with live telemetry and status.',
      'nodes.search_placeholder':  'Search node by name, alias, role or public key...',
      'nodes.filter_all':          'All',
      'nodes.filter_repeaters':    'Repeaters',
      'nodes.filter_sensors':      'Sensors',
      'nodes.filter_rooms':        'Rooms',
      'nodes.filter_clients':      'Clients',
      'nodes.discovering':         'Discovering nodes in the LoRa mesh...',

      // Contacts section
      'contacts.title':            'Contact Book',
      'contacts.subtitle':         'Directory of contacts, friend nodes and public key management.',
      'contacts.refresh':          'Refresh',
      'contacts.add':              'Add Contact',
      'contacts.search_placeholder': 'Search contact by name, alias or public key...',
      'contacts.filter_all':       'All',
      'contacts.filter_favorites': 'Favorites',
      'contacts.filter_online':    'Online',
      'contacts.filter_gps':       'With Position',
      'contacts.loading':          'Loading contacts from device...',
      'contacts.accept_all':       'Accept All',

      // Map section
      'map.dark':       'Dark',
      'map.streets':    'Streets',
      'map.satellite':  'Satellite',
      'map.local':      'Local',
      'map.radar':      'Radar',
      'map.heatmap':    'RF Heatmap',
      'map.nodes_title':'Nodes in Mesh',

      // Analytics section
      'analytics.title':           'Mesh Network Metrics & Analytics',
      'analytics.subtitle':        'RF traffic monitoring, SNR/RSSI link quality, repeater statistics and bridge health.',
      'analytics.refresh':         'Refresh Metrics',
      'analytics.kpi_packets':     'Total Mesh Packets',
      'analytics.kpi_nodes':       'Active Registered Nodes',
      'analytics.kpi_error_rate':  'Global Error Rate',
      'analytics.kpi_queue':       'TX Transmission Queue',
      'analytics.top_active':      'Top Most Active Nodes',
      'analytics.top_active_sub':  'Nodes with highest packet volume sent and received',
      'analytics.signal':          'RF Signal Quality (SNR)',
      'analytics.signal_sub':      'Best and worst signal-to-noise ratio ranking in the mesh',
      'analytics.repeaters':       'Top Routers & Repeaters',
      'analytics.repeaters_sub':   'Infrastructure nodes and routed clients',
      'analytics.bridge':          'Bridge Health & Performance',

      // Logs section
      'logs.title':                'System Log Console',
      'logs.subtitle':             'MeshCore bridge event log: connections, errors, serial traffic and MQTT activity.',
      'logs.clear':                'Clear Logs',
      'logs.export':               'Export',
      'logs.pause':                'Pause',
      'logs.resume':               'Resume',

      // Settings section
      'settings.title':            'Settings & Configuration',
      'settings.subtitle':         'Serial bridge, MQTT, LoRa radio parameters and web interface preferences.',
      'settings.save':             'Save Configuration',
      'settings.reset':            'Reset',

      // Node card (dynamic)
      'node.battery':      'Battery',
      'node.rssi':         'RSSI',
      'node.snr':          'SNR',
      'node.hops':         'Hops',
      'node.last_seen':    'Last seen',
      'node.send_dm':      'DM',
      'node.admin':        'Manage',
      'node.ping':         'Ping',
      'node.traceroute':   'Traceroute',
      'node.role_client':  'Client',
      'node.role_repeater':'Repeater',
      'node.role_sensor':  'Sensor',
      'node.role_room':    'Room',
      'node.role_local':   'Local',
      'node.role_unknown': 'Unknown',
      'node.unknown':      'Unknown',
      'node.never':        'Never',
      'node.voltage':      'Voltage',
      'node.lat':          'Lat',
      'node.lon':          'Lon',
      'node.no_gps':       'No GPS',

      // Modal / Common
      'modal.close':       'Close',
      'modal.confirm':     'Confirm',
      'modal.cancel':      'Cancel',
      'modal.save':        'Save',
      'modal.send':        'Send',
      'modal.copy':        'Copy',
      'modal.delete':      'Delete',
      'modal.edit':        'Edit',
      'modal.loading':     'Loading...',
      'modal.error':       'Error',
      'modal.success':     'Success',
      'modal.yes':         'Yes',
      'modal.no':          'No',

      // Language toggle
      'lang.current':      'EN',
      'lang.switch':       '🌐 ES',
      'lang.title':        'Cambiar a Español',
    },
  };

  // ── Selector → i18n key map (static DOM elements) ──────────────────────────
  // Each entry: { s: CSS selector, k: key, a?: attribute, last?: bool }
  // last:true → update only the last text node (for icon+text buttons)
  const DOM_MAP = [
    // Nav labels
    { s: '#navTabChat .nav-label',       k: 'nav.chat' },
    { s: '#navTabContacts .nav-label',   k: 'nav.contacts' },
    { s: '#navTabNodes .nav-label',      k: 'nav.nodes' },
    { s: '#navTabMap .nav-label',        k: 'nav.map' },
    { s: '#navTabAnalytics .nav-label',  k: 'nav.analytics' },
    { s: '#navTabLogs .nav-label',       k: 'nav.logs' },
    { s: '#navTabSettings .nav-label',   k: 'nav.settings' },
    { s: '.sidebar-toggle-label',        k: 'nav.collapse' },

    // Global search hint
    { s: '.search-hint',                 k: 'search.global_placeholder' },

    // Chat
    { s: '#chatInputText',               k: 'chat.input_placeholder', a: 'placeholder' },
    { s: '#clearChatBtn',                k: 'chat.clear', last: true },
    { s: '#btnSendMsg span:first-child', k: 'chat.send' },

    // Nodes section
    { s: '#nodesSearchInput',            k: 'nodes.search_placeholder', a: 'placeholder' },

    // Contacts section
    { s: '#contactsSearchInput',         k: 'contacts.search_placeholder', a: 'placeholder' },

    // Map layers (last text node — icon + text)
    { s: '.map-layer-btn[data-layer="dark"]',         k: 'map.dark',      last: true },
    { s: '.map-layer-btn[data-layer="osm"]',          k: 'map.streets',   last: true },
    { s: '.map-layer-btn[data-layer="satellite"]',    k: 'map.satellite', last: true },
    { s: '.map-layer-btn[data-layer="local"]',        k: 'map.local',     last: true },
    { s: '.map-layer-btn[data-layer="tactical_radar"]',k: 'map.radar',    last: true },
    { s: '#btnToggleHeatmap',            k: 'map.heatmap', last: true },

    // Lang toggle button
    { s: '#langToggleBtn',               k: 'lang.switch' },
    { s: '#langToggleBtn',               k: 'lang.title', a: 'title' },
  ];

  // ── Language resolution ─────────────────────────────────────────────────────
  const LS_KEY = 'mc_lang';
  let _lang = localStorage.getItem(LS_KEY) ||
    (navigator.language && navigator.language.toLowerCase().startsWith('es') ? 'es' : 'en');
  if (!DICT[_lang]) _lang = 'es';

  // ── Core helpers ────────────────────────────────────────────────────────────
  /** Get translated string. Falls back to Spanish, then to the key itself. */
  function t(key) {
    return (DICT[_lang] && DICT[_lang][key]) || (DICT.es && DICT.es[key]) || key;
  }

  /**
   * Set the last text node of an element, preserving child elements (icons).
   * Falls back to textContent if no text node is found.
   */
  function _setLastTextNode(el, text) {
    const children = Array.from(el.childNodes);
    const textNodes = children.filter(
      n => n.nodeType === Node.TEXT_NODE && n.textContent.trim().length > 0
    );
    if (textNodes.length > 0) {
      textNodes[textNodes.length - 1].textContent = '\u00A0' + text;
    } else {
      // No text node found — create one after existing children
      el.appendChild(document.createTextNode('\u00A0' + text));
    }
  }

  /** Apply a single DOM_MAP entry */
  function _applyEntry(entry) {
    document.querySelectorAll(entry.s).forEach(el => {
      const text = t(entry.k);
      if (entry.a) {
        el.setAttribute(entry.a, text);
      } else if (entry.last) {
        _setLastTextNode(el, text);
      } else {
        el.textContent = text;
      }
    });
  }

  /** Apply all static DOM translations */
  function apply() {
    document.documentElement.lang = _lang;
    DOM_MAP.forEach(_applyEntry);
    // Update lang button text + title separately
    const btn = document.getElementById('langToggleBtn');
    if (btn) {
      btn.textContent = t('lang.switch');
      btn.title = t('lang.title');
    }
  }

  /** Toggle between 'es' and 'en', persist, and re-apply */
  function toggle() {
    _lang = _lang === 'es' ? 'en' : 'es';
    localStorage.setItem(LS_KEY, _lang);
    apply();
    // Dispatch event so app.js can react (re-render dynamic content if needed)
    window.dispatchEvent(new CustomEvent('mc:langchange', { detail: { lang: _lang } }));
  }

  // ── Public API ──────────────────────────────────────────────────────────────
  window.I18n = Object.freeze({ t, apply, toggle, get lang() { return _lang; } });

  // Auto-apply as soon as DOM is interactive
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', apply);
  } else {
    apply();
  }
})();
