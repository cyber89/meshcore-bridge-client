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


      // Analytics
      'analytics.no_traffic':      'No hay nodos con tráfico registrado todavía.',
      'analytics.no_signal':       'No hay mediciones de SNR/RSSI registradas en la malla.',
      'analytics.no_repeaters':    'No se detectaron repetidores o routers en la topología.',
      'analytics.nodes_count':     '{n} nodos',
      'analytics.hops_count':      '{n} saltos',
      'analytics.standard':        'Estándar',
      'analytics.in_ram_dup':      'En RAM ({n} duplicados filtrados)',
      'analytics.pkts_waiting':    '{n} paquetes en espera',
      'analytics.connected_ok':    'Conectado y Operativo',
      'analytics.disconnected':    'Desconectado',
      'analytics.online_broker':   'En Línea (Broker Bridge)',
      'analytics.usage_pct':       'Uso actual: {pct}% del ciclo horario',
      'analytics.repeater_count':  '{n} Repetidores en Malla',
      'analytics.errors_acc':      '{n} errores acumulados',
      'analytics.packets_count':   '{n} paquetes',

      // Chat
      'chat.sound_on':             '🔔 Alertas sonoras de chat activadas',
      'chat.sound_off':            '🔕 Alertas sonoras de chat desactivadas',
      'chat.ch_0_title':           'Canal 0 (Public / Broadcast)',
      'chat.ch_n_title':           'Canal #{n}',
      'chat.ch_0_sub':             'Difusión comunitaria abierta por radio LoRa',
      'chat.ch_n_sub':             'Canal privado cifrado #{n}',
      'chat.open_badge':           'Abierto',
      'chat.encrypted_badge':      'Cifrado',
      'chat.dm_sub':               'Mensaje directo punto a punto • {pk}',
      'chat.my_location':          '📍 Mi ubicación GPS: {lat}, {lon}',
      'chat.station_location':     '📍 Ubicación de estación: {lat}, {lon}',
      'chat.cleared':              'Conversación limpiada.',
      'chat.write_below':          'Escribe un mensaje abajo para transmitir por la malla LoRa.',
      'chat.no_messages':          'No hay mensajes en esta conversación aún.',
      'chat.gps_shared':           '📍 Punto GPS Compartido',
      'chat.view_map':             'Ver en Mapa',
      'chat.delivered':            '✓✓ Entregado',
      'chat.sent':                 '✓ Enviado',

      // Map
      'map.local_station_you':     'Estación Base Local (Tú)',
      'map.local_station':         'Estación Base Local',
      'map.no_gps_nodes':          'No hay nodos con posición GPS en la malla.',
      'map.trace_ready':           'Listo para trazar',
      'map.trace_hint':            'Haz clic en "Iniciar Traza" para enviar una sonda multi-salto y mapear los repetidores.',
      'map.trace_start_hint':      'Presiona "Iniciar Traza" para comenzar',
      'map.trace_transmitting':    'Transmitiendo sonda RF...',
      'map.trace_completed':       '✓ Completado ({hops} saltos, {rtt}ms)',
      'map.trace_failed':          '✗ Fallo de traza o sin respuesta',
      'map.trace_conn_err':        '✗ Error de conexión',
      'map.tracing':               '⏳ Trazando...',
      'map.start_trace':           '🚀 Iniciar Traza',
      'map.node_label':            'Nodo',
      'map.role_label':            'Rol:',
      'map.link_qual':             'Calidad Enlace:',
      'map.rssi_snr':              'RSSI / SNR:',
      'map.noise_floor':           'Piso Ruido:',
      'map.cov_radius':            'Radio Cobertura:',
      'map.key_label':             'Clave:',
      'map.pos_label':             'Posición:',
      'map.rssi_label':            'RSSI:',
      'map.snr_label':             'SNR:',
      'map.local_connected':       '📍 Transceptor Local Conectado',

      // Nodes
      'nodes.no_contacts':         'No hay contactos registrados en el dispositivo.',
      'nodes.no_nodes':            'No se han descubierto nodos en la malla LoRa.',
      'nodes.route_direct':        'Directo',
      'nodes.route_mesh':          'Malla',
      'nodes.chat_btn':            'Chat',
      'nodes.trace_btn':           'Ruta',
      'nodes.manage_btn':          'Administrar',
      'nodes.settings_btn':        'Ajustes',
      'nodes.owner_label':         'Dueño:',
      'nodes.remove_fav':          'Quitar de favoritos',
      'nodes.add_fav':             'Marcar como favorito',
      'nodes.del_confirm':         '¿Eliminar al contacto "{name}"?',
      'nodes.empty_filter':        'No se encontraron contactos para los filtros seleccionados.',
      'nodes.empty_fav':           '⭐ No tienes contactos marcados como favoritos. Haz clic en la estrella de cualquier tarjeta para añadirlo.',
      'nodes.empty_online':        '📡 No hay contactos en línea en este momento.',
      'nodes.empty_gps':           '📍 No hay contactos con posición GPS registrada.',
      'nodes.empty_search':        '🔍 No se encontraron contactos que coincidan con "{q}".',
      'nodes.battery_title':       'Batería: {val}',
      'nodes.route_label':         'Ruta:',
      'nodes.lqi_label':           'LQI:',

      // Repeater
      'rep.auth_err':              'Contraseña incorrecta o cambiada en el repetidor',
      'rep.verifying':             '⏳ Verificando credenciales con el repetidor por RF...',

      // Sniffer
      'sniffer.no_packets_filter': 'No hay paquetes que coincidan con los filtros actuales.',
      'sniffer.no_logs_filter':    'No hay logs que coincidan con los filtros actuales.',
      'sniffer.rx_incoming':       'RX (Entrante)',
      'sniffer.tx_outgoing':       'TX (Saliente)',
      'sniffer.no_decoded':        '(Sin payload decodificado)',
      'sniffer.copied':            '✓ ¡Copiado!',
      'sniffer.inspect_btn':       'Inspeccionar trama',

      // Time & Signals
      'time.online_host':          'En línea (Host)',
      'time.unknown':              'Desconocido',
      'time.just_now':             'Hace un momento',
      'time.mins_ago':             'Hace {n} min',
      'time.hours_ago':            'Hace {n} h',
      'time.days_ago':             'Hace {n} d',
      'signal.excellent':          'Excelente',
      'signal.good':               'Buena',
      'signal.acceptable':         'Aceptable',
      'signal.marginal':           'Marginal',
      'signal.weak':               'Débil',
      'signal.critical':           'Crítico',

      // Toasts
      'toast.dm_local_err':        '⚠️ No se puede abrir conversación DM con la estación local',
      'toast.repeater_chat_err':   '🚫 Los repetidores son nodos de infraestructura y no procesan chat.',
      'toast.contact_copied':      '📋 Enlace de contacto copiado al portapapeles',
      'toast.channel_copied':      '📋 Enlace de canal copiado al portapapeles',
      'toast.gps_loading':         '📍 Obteniendo coordenadas GPS...',
      'toast.gps_ready':           '📍 Coordenadas listas para enviar: {lat}, {lon}',
      'toast.gps_station':         '📍 Usando ubicación configurada de la estación base: {lat}, {lon}',
      'toast.map_adjusted':        '🗺️ Mapa ajustado a los nodos activos con GPS',
      'toast.map_centered_local':  '🎯 Centrado en nodo local ({lat}, {lon})',
      'toast.map_no_local_gps':    'No se encontraron coordenadas GPS para el nodo local.',
      'toast.heatmap_off':         '🔥 Mapa de calor RF desactivado',
      'toast.heatmap_on':          '🔥 Heatmap RF generado con {n} puntos de cobertura activa',
      'toast.heatmap_err':         'Error cargando Heatmap RF: {err}',
      'toast.trace_completed':     '🗺️ Ruta completada en {hops} saltos ({rtt} ms)',
      'toast.trace_err':           'Error en traza: {msg}',
      'toast.net_err':             'Error de red: {msg}',
      'toast.contact_deleted':     'Contacto eliminado',
      'toast.fav_added':           '⭐ "{name}" añadido a Favoritos',
      'toast.fav_removed':         '"{name}" quitado de Favoritos',
      'toast.rep_logout':          '🔒 Sesión de administración cerrada para este repetidor',
      'toast.rep_auth_ok':         '🔓 Repetidor autenticado con éxito',
      'toast.rep_cfg_ok':          '📻 Configuración RF transmitida al repetidor',
      'toast.rep_pos_ok':          '📍 Información y posición aplicadas al repetidor',
      'toast.rep_telem_req':       '📡 Consultando telemetría, batería y estado al repetidor por RF...',
      'toast.ch_saved':            '✅ Canal {index} ({name}) guardado y sincronizado',
      'toast.contact_added':       '✅ Contacto {name} agregado',
      'toast.uri_copied':          '📋 Enlace URI copiado al portapapeles',
      'toast.api_key_saved':       '🔑 API Key guardada en el navegador',
      'toast.api_key_del':         'ℹ️ API Key eliminada',
      'toast.radio_cfg_ok':        '📻 Parámetros de radio locales actualizados',
      'toast.identity_ok':         '📍 Identidad y ubicación guardadas',

      // Common
      'common.you':                'Tú',
      'common.anonymous':          'Anónimo',
      'common.local_station':      'Estación Local (Tú)',
      'common.no_gps':             'Sin GPS',
      'common.repeater':           'Repetidor',
      'common.node':               'Nodo',

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


      // Analytics
      'analytics.no_traffic':      'No nodes with registered traffic yet.',
      'analytics.no_signal':       'No SNR/RSSI measurements registered in the mesh.',
      'analytics.no_repeaters':    'No repeaters or routers detected in the topology.',
      'analytics.nodes_count':     '{n} nodes',
      'analytics.hops_count':      '{n} hops',
      'analytics.standard':        'Standard',
      'analytics.in_ram_dup':      'In RAM ({n} duplicates filtered)',
      'analytics.pkts_waiting':    '{n} packets waiting',
      'analytics.connected_ok':    'Connected and Operational',
      'analytics.disconnected':    'Disconnected',
      'analytics.online_broker':   'Online (Broker Bridge)',
      'analytics.usage_pct':       'Current usage: {pct}% of hourly cycle',
      'analytics.repeater_count':  '{n} Repeaters in Mesh',
      'analytics.errors_acc':      '{n} accumulated errors',
      'analytics.packets_count':   '{n} packets',

      // Chat
      'chat.sound_on':             '🔔 Chat sound alerts enabled',
      'chat.sound_off':            '🔕 Chat sound alerts disabled',
      'chat.ch_0_title':           'Channel 0 (Public / Broadcast)',
      'chat.ch_n_title':           'Channel #{n}',
      'chat.ch_0_sub':             'Open community broadcast over LoRa radio',
      'chat.ch_n_sub':             'Encrypted private channel #{n}',
      'chat.open_badge':           'Open',
      'chat.encrypted_badge':      'Encrypted',
      'chat.dm_sub':               'Point-to-point direct message • {pk}',
      'chat.my_location':          '📍 My GPS location: {lat}, {lon}',
      'chat.station_location':     '📍 Station location: {lat}, {lon}',
      'chat.cleared':              'Conversation cleared.',
      'chat.write_below':          'Type a message below to transmit over the LoRa mesh.',
      'chat.no_messages':          'No messages in this conversation yet.',
      'chat.gps_shared':           '📍 Shared GPS Point',
      'chat.view_map':             'View on Map',
      'chat.delivered':            '✓✓ Delivered',
      'chat.sent':                 '✓ Sent',

      // Map
      'map.local_station_you':     'Local Base Station (You)',
      'map.local_station':         'Local Base Station',
      'map.no_gps_nodes':          'No nodes with GPS position in the mesh.',
      'map.trace_ready':           'Ready to trace',
      'map.trace_hint':            'Click "Start Trace" to send a multi-hop probe and map repeaters.',
      'map.trace_start_hint':      'Press "Start Trace" to begin',
      'map.trace_transmitting':    'Transmitting RF probe...',
      'map.trace_completed':       '✓ Completed ({hops} hops, {rtt}ms)',
      'map.trace_failed':          '✗ Trace failed or no response',
      'map.trace_conn_err':        '✗ Connection error',
      'map.tracing':               '⏳ Tracing...',
      'map.start_trace':           '🚀 Start Trace',
      'map.node_label':            'Node',
      'map.role_label':            'Role:',
      'map.link_qual':             'Link Quality:',
      'map.rssi_snr':              'RSSI / SNR:',
      'map.noise_floor':           'Noise Floor:',
      'map.cov_radius':            'Coverage Radius:',
      'map.key_label':             'Key:',
      'map.pos_label':             'Position:',
      'map.rssi_label':            'RSSI:',
      'map.snr_label':             'SNR:',
      'map.local_connected':       '📍 Local Transceiver Connected',

      // Nodes
      'nodes.no_contacts':         'No contacts registered on the device.',
      'nodes.no_nodes':            'No nodes discovered in the LoRa mesh.',
      'nodes.route_direct':        'Direct',
      'nodes.route_mesh':          'Mesh',
      'nodes.chat_btn':            'Chat',
      'nodes.trace_btn':           'Trace',
      'nodes.manage_btn':          'Manage',
      'nodes.settings_btn':        'Settings',
      'nodes.owner_label':         'Owner:',
      'nodes.remove_fav':          'Remove from favorites',
      'nodes.add_fav':             'Mark as favorite',
      'nodes.del_confirm':         'Delete contact "{name}"?',
      'nodes.empty_filter':        'No contacts found for the selected filters.',
      'nodes.empty_fav':           '⭐ You have no contacts marked as favorites. Click the star on any card to add one.',
      'nodes.empty_online':        '📡 No contacts online right now.',
      'nodes.empty_gps':           '📍 No contacts with registered GPS position.',
      'nodes.empty_search':        '🔍 No contacts found matching "{q}".',
      'nodes.battery_title':       'Battery: {val}',
      'nodes.route_label':         'Route:',
      'nodes.lqi_label':           'LQI:',

      // Repeater
      'rep.auth_err':              'Incorrect password or changed on the repeater',
      'rep.verifying':             '⏳ Verifying credentials with repeater via RF...',

      // Sniffer
      'sniffer.no_packets_filter': 'No packets match current filters.',
      'sniffer.no_logs_filter':    'No logs match current filters.',
      'sniffer.rx_incoming':       'RX (Incoming)',
      'sniffer.tx_outgoing':       'TX (Outgoing)',
      'sniffer.no_decoded':        '(No decoded payload)',
      'sniffer.copied':            '✓ Copied!',
      'sniffer.inspect_btn':       'Inspect frame',

      // Time & Signals
      'time.online_host':          'Online (Host)',
      'time.unknown':              'Unknown',
      'time.just_now':             'Just now',
      'time.mins_ago':             '{n} mins ago',
      'time.hours_ago':            '{n} hrs ago',
      'time.days_ago':             '{n} days ago',
      'signal.excellent':          'Excellent',
      'signal.good':               'Good',
      'signal.acceptable':         'Acceptable',
      'signal.marginal':           'Marginal',
      'signal.weak':               'Weak',
      'signal.critical':           'Critical',

      // Toasts
      'toast.dm_local_err':        '⚠️ Cannot open DM conversation with the local station',
      'toast.repeater_chat_err':   '🚫 Repeaters are infrastructure nodes and do not process chat.',
      'toast.contact_copied':      '📋 Contact link copied to clipboard',
      'toast.channel_copied':      '📋 Channel link copied to clipboard',
      'toast.gps_loading':         '📍 Getting GPS coordinates...',
      'toast.gps_ready':           '📍 Coordinates ready to send: {lat}, {lon}',
      'toast.gps_station':         '📍 Using configured base station location: {lat}, {lon}',
      'toast.map_adjusted':        '🗺️ Map adjusted to active nodes with GPS',
      'toast.map_centered_local':  '🎯 Centered on local node ({lat}, {lon})',
      'toast.map_no_local_gps':    'No GPS coordinates found for the local node.',
      'toast.heatmap_off':         '🔥 RF Heatmap disabled',
      'toast.heatmap_on':          '🔥 RF Heatmap generated with {n} active coverage points',
      'toast.heatmap_err':         'Error loading RF Heatmap: {err}',
      'toast.trace_completed':     '🗺️ Route completed in {hops} hops ({rtt} ms)',
      'toast.trace_err':           'Trace error: {msg}',
      'toast.net_err':             'Network error: {msg}',
      'toast.contact_deleted':     'Contact deleted',
      'toast.fav_added':           '⭐ "{name}" added to Favorites',
      'toast.fav_removed':         '"{name}" removed from Favorites',
      'toast.rep_logout':          '🔒 Admin session closed for this repeater',
      'toast.rep_auth_ok':         '🔓 Repeater authenticated successfully',
      'toast.rep_cfg_ok':          '📻 RF configuration transmitted to repeater',
      'toast.rep_pos_ok':          '📍 Information and position applied to repeater',
      'toast.rep_telem_req':       '📡 Requesting telemetry, battery and status to repeater via RF...',
      'toast.ch_saved':            '✅ Channel {index} ({name}) saved and synced',
      'toast.contact_added':       '✅ Contact {name} added',
      'toast.uri_copied':          '📋 URI link copied to clipboard',
      'toast.api_key_saved':       '🔑 API Key saved in browser',
      'toast.api_key_del':         'ℹ️ API Key deleted',
      'toast.radio_cfg_ok':        '📻 Local radio parameters updated',
      'toast.identity_ok':         '📍 Identity and location saved',

      // Common
      'common.you':                'You',
      'common.anonymous':          'Anonymous',
      'common.local_station':      'Local Station (You)',
      'common.no_gps':             'No GPS',
      'common.repeater':           'Repeater',
      'common.node':               'Node',

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
