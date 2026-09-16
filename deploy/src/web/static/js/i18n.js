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

      // Header metrics tooltips
      'header.active_nodes':       'Nodos Activos en Malla',
      'header.rx_packets':         'Paquetes Recibidos',
      'header.tx_packets':         'Paquetes Emitidos',
      'header.airtime':            'Presupuesto de Airtime LoRa y Duty Cycle (1h)',
      'header.error_rate':         'Tasa de Error',
      'header.tx_queue':           'Cola TX / Buffer',

      // Chat section
      'chat.channels':             'Canales',
      'chat.direct_messages':      'Mensajes Directos',
      'chat.no_conversations':     'Sin conversaciones activas',
      'chat.channel_prefix':       'Canal',
      'chat.ch_0_default':         'Public / Broadcast',
      'chat.add_channel_title':    'Crear / Unirse a canal',
      'chat.import_channel_title': 'Importar canal o contacto',
      'chat.send':                 'Enviar',
      'chat.clear':                'Limpiar',
      'chat.input_placeholder':    'Escribe un mensaje para transmitir por RF...',
      'chat.open':                 'Canales',

      // Nodes section
      'nodes.title':               'Directorio de Nodos en la Malla',
      'nodes.subtitle':            'Todos los nodos descubiertos en la red LoRa MeshCore con su telemetría y estado en vivo.',
      'nodes.search_placeholder':  'Buscar nodo por nombre, alias, rol o clave pública...',
      'nodes.ping_btn':            'Ping',
      'nodes.ping_title':          'Ping directo de 0 saltos',
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
      'analytics.reset':           'Restablecer Métricas',
      'analytics.reset_title':     'Restablecer contadores y estadísticas acumuladas',
      'analytics.confirm_reset':   '¿Deseas restablecer todos los contadores de paquetes y métricas acumuladas de la red?',

      // Chat
      'chat.sound_on':             '🔔 Alertas sonoras de chat activadas',
      'chat.sound_off':            '🔕 Alertas sonoras de chat desactivadas',
      'chat.ch_0_title':           'Canal 0 (Public / Broadcast)',
      'chat.ch_n_title':           'Canal #{n}',
      'chat.ch_0_sub':             'Difusión comunitaria abierta por radio LoRa',
      'chat.ch_n_sub':             'Canal privado cifrado #{n}',
      'chat.ch_n_open_sub':        'Canal abierto sin cifrar #{n}',
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
      'nodes.hops':                'saltos',
      'nodes.key_label':           'Clave:',
      'nodes.tooltip_rssi':        'RSSI recibido',
      'nodes.tooltip_snr':         'Relación señal/ruido (SNR)',
      'nodes.tooltip_hops':        'Saltos en la red',
      'nodes.title_manage':        'Administrar Repetidor Remoto',
      'nodes.title_dm':            'Enviar Mensaje Directo',
      'nodes.title_settings':      'Configurar Nodo Local',
      'nodes.title_trace':         'Trazar ruta de red',
      'nodes.title_qr':            'Compartir QR',
      'contacts.title_chat':       'Abrir chat con este contacto',
      'contacts.title_trace':      'Trazar ruta traceroute',
      'contacts.title_qr':         'Compartir QR del contacto',
      'contacts.title_del':        'Eliminar de contactos',

      // Repeater
      'rep.auth_err':              'Contraseña incorrecta o cambiada en el repetidor',
      'rep.verifying':             '⏳ Verificando credenciales con el repetidor por RF...',
      'rep.restricted_access':     'Acceso de Administración Restringido',
      'rep.restricted_desc':       'Para consultar la telemetría, modificar parámetros RF y despachar comandos remotos a este repetidor, es obligatorio validar la contraseña de administración.',
      'rep.pin_label':             'Contraseña de Administración (PIN):',
      'rep.pin_placeholder':       'PIN / Contraseña del repetidor...',
      'rep.unlock_btn':            'Desbloquear & Autenticar Repetidor',

      // Modals
      'modal.channel_title':       'Configurar Canal LoRa',
      'modal.contact_title':       'Agregar Nuevo Contacto',
      'modal.save_channel':        'Guardar y Sincronizar al Nodo',
      'modal.save_contact':        'Guardar Contacto',
      'qr.title':                  'Compartir por Código QR',
      'qr.scan_hint':              'Escanea con la app MeshCore o cámara',
      'qr.uri_label':              'Enlace URI MeshCore:',
      'qr.copy_btn':               'Copiar',
      'qr.json_label':             'Esquema JSON:',
      'qr.download_json':          'Descargar JSON',
      'qr.done':                   'Listo',

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
      'time.online_local':         'En línea (Local)',
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
      'toast.metrics_reset':       'Métricas y contadores restablecidos correctamente',
      'toast.ping_sending':        '🎯 Enviando Ping (0 saltos) a {name}...',
      'toast.ping_ok':             '🎯 Pong recibido de {name}: {rtt}{snr}',
      'toast.ping_err':            '⚠️ Sin respuesta de Ping desde {name}',

      // Common
      'common.you':                'Tú',
      'common.anonymous':          'Anónimo',
      'common.local_station':      'Estación Local (Tú)',
      'common.online':             'En línea',
      'common.offline':            'Inactivo',
      'common.no_gps':             'Sin GPS',
      'common.repeater':           'Repetidor',
      'common.node':               'Nodo',

      // Settings actions
      'settings.action_clear_stats': 'Limpiar Stats',
      'settings.action_clear_stats_title': 'Restablece contadores de paquetes, duplicados y tiempos de aire',

      // Additional Chat keys
      'chat.add_channel_title':    'Crear / Unirse a canal',
      'chat.import_channel_title': 'Importar canal o contacto',
      'chat.share_location_title': 'Compartir mi ubicación GPS actual en el chat',
      'chat.qr':                   'QR',

      // Additional Map keys
      'map.fit_bounds':            'Ajustar mapa a todos los nodos con GPS',
      'map.center_local':          'Centrar en mi nodo local',

      // Additional Logs & Sniffer keys
      'logs.subtab_logs':          'Logs del Sistema',
      'logs.subtab_sniffer':       'Monitor de Paquetes RF (LoRa Sniffer)',
      'logs.debug_mode':           'Modo DEBUG',
      'logs.download_log':         'Descargar .log',
      'logs.pause_scroll':         'Pausar Scroll',
      'logs.resume_scroll':        'Reanudar Scroll',
      'logs.level_label':          'Nivel:',
      'logs.search_placeholder':   'Buscar en logs (módulo, error, texto)...',
      'sniffer.title':             'Monitor de Paquetes RF (LoRa Sniffer)',
      'sniffer.subtitle':          'Captura y análisis en vivo de tramas binarias LoRa MeshCore sobre el aire.',
      'sniffer.pause_btn':         'Pausar Captura',
      'sniffer.resume_btn':        'Reanudar Captura',
      'sniffer.clear_btn':         'Limpiar Paquetes',
      'sniffer.export_pcap':       'Exportar PCAP',
      'sniffer.export_json':       'Exportar JSON',
      'sniffer.export_csv':        'Exportar CSV',
      'sniffer.search_placeholder':'Buscar por pubkey, texto o hex...',

      // Additional Settings keys
      'settings.subtab_telem':     'Telemetría & Estado',
      'settings.subtab_radio':     'Parámetros RF & Radio',
      'settings.subtab_identity':  'Identidad & Posición GPS',
      'settings.subtab_terminal':  'Terminal',
      'settings.subtab_maps':      'Mapas Offline',
      'settings.subtab_security':  'Seguridad & API',
      'settings.refresh':          'Actualizar Parámetros',
      'settings.hw_actions_title': 'Acciones Rápidas de Hardware',
      'settings.hw_actions_sub':   'Comandos de ejecución y control directo sobre el microcontrolador y transceptor LoRa',
      'settings.action_advert_hop':'Advert Hop 0',
      'settings.action_advert_flood':'Advert Flood',
      'settings.action_stats':     'Stats Hardware',
      'settings.action_sync_rtc':  'Sincronizar RTC',
      'settings.action_clear_stats':'Limpiar Stats',
      'settings.action_reconnect_serial':'Reconectar Serial',
      'settings.action_reboot':    'Reiniciar Nodo',

      // Language toggle
      'lang.current':      'ES',
      'lang.switch':       '🌐 EN',
      'lang.title':        'Switch to English',

      // App orchestration & status
      'app.web_online':             'Web: Conectado',
      'app.web_connecting':         'Web: Conectando…',
      'app.web_offline':            'Web: Desconectado',
      'app.radio_online':           'Radio: Conectada ({port})',
      'app.radio_online_fallback':  'Radio: Conectada',
      'app.radio_offline':          'Radio: Desconectada',
      'app.dark_theme_title':       'Cambiar a tema claro',
      'app.light_theme_title':      'Cambiar a tema oscuro',

      // Time & Presence
      'time.online_local':          'En línea (Local)',
      'time.offline_no_signal':     'Desconectado (Sin señal)',
      'time.active_now':            'Activo (ahora mismo)',
      'time.active_mins':           'Activo (hace {n}m)',
      'time.active_hours':          'Activo (hace {n}h)',
      'time.idle_hours':            'Inactivo (hace {n}h)',
      'time.offline_days':          'Desconectado (hace {n}d)',
      'time.last_signal_tooltip':   'Última señal recibida: {time}',
      'time.no_signal':             'Sin señal registrada',
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

      // Header metrics tooltips
      'header.active_nodes':       'Active Nodes in Mesh',
      'header.rx_packets':         'Received Packets',
      'header.tx_packets':         'Transmitted Packets',
      'header.airtime':            'LoRa Airtime Budget & Duty Cycle (1h)',
      'header.error_rate':         'Error Rate',
      'header.tx_queue':           'TX Queue / Buffer',

      // Chat section
      'chat.channels':             'Channels',
      'chat.direct_messages':      'Direct Messages',
      'chat.no_conversations':     'No active conversations',
      'chat.channel_prefix':       'Channel',
      'chat.ch_0_default':         'Public / Broadcast',
      'chat.add_channel_title':    'Create / Join Channel',
      'chat.import_channel_title': 'Import Channel or Contact',
      'chat.send':                 'Send',
      'chat.clear':                'Clear',
      'chat.input_placeholder':    'Type a message to transmit via RF...',
      'chat.open':                 'Channels',

      // Nodes section
      'nodes.title':               'Mesh Node Directory',
      'nodes.subtitle':            'All nodes discovered in the MeshCore LoRa network with live telemetry and status.',
      'nodes.search_placeholder':  'Search node by name, alias, role or public key...',
      'nodes.ping_btn':            'Ping',
      'nodes.ping_title':          'Direct 0-hop Ping',
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
      'analytics.reset':           'Reset Metrics',
      'analytics.reset_title':     'Reset counters and accumulated statistics',
      'analytics.confirm_reset':   'Do you want to reset all packet counters and accumulated network metrics?',

      // Chat
      'chat.sound_on':             '🔔 Chat sound alerts enabled',
      'chat.sound_off':            '🔕 Chat sound alerts disabled',
      'chat.ch_0_title':           'Channel 0 (Public / Broadcast)',
      'chat.ch_n_title':           'Channel #{n}',
      'chat.ch_0_sub':             'Open community broadcast over LoRa radio',
      'chat.ch_n_sub':             'Encrypted private channel #{n}',
      'chat.ch_n_open_sub':        'Unencrypted open channel #{n}',
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
      'nodes.hops':                'hops',
      'nodes.key_label':           'Key:',
      'nodes.tooltip_rssi':        'Received RSSI',
      'nodes.tooltip_snr':         'Signal-to-noise ratio (SNR)',
      'nodes.tooltip_hops':        'Hops in network',
      'nodes.title_manage':        'Manage Remote Repeater',
      'nodes.title_dm':            'Send Direct Message',
      'nodes.title_settings':      'Configure Local Node',
      'nodes.title_trace':         'Trace network route',
      'nodes.title_qr':            'Share QR',
      'contacts.title_chat':       'Open chat with this contact',
      'contacts.title_trace':      'Trace network route',
      'contacts.title_qr':         'Share contact QR',
      'contacts.title_del':        'Delete from contacts',

      // Repeater
      'rep.auth_err':              'Incorrect password or changed on the repeater',
      'rep.verifying':             '⏳ Verifying credentials with repeater via RF...',
      'rep.restricted_access':     'Restricted Administration Access',
      'rep.restricted_desc':       'To view telemetry, modify RF parameters, and dispatch remote commands to this repeater, admin password validation is required.',
      'rep.pin_label':             'Administration Password (PIN):',
      'rep.pin_placeholder':       'Repeater PIN / Password...',
      'rep.unlock_btn':            'Unlock & Authenticate Repeater',

      // Modals
      'modal.channel_title':       'Configure LoRa Channel',
      'modal.contact_title':       'Add New Contact',
      'modal.save_channel':        'Save and Sync to Node',
      'modal.save_contact':        'Save Contact',
      'qr.title':                  'Share via QR Code',
      'qr.scan_hint':              'Scan with MeshCore app or camera',
      'qr.uri_label':              'MeshCore URI Link:',
      'qr.copy_btn':               'Copy',
      'qr.json_label':             'JSON Schema:',
      'qr.download_json':          'Download JSON',
      'qr.done':                   'Done',

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
      'time.online_local':         'Online (Local)',
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
      'toast.metrics_reset':       'Metrics and counters reset successfully',
      'toast.ping_sending':        '🎯 Sending Ping (0 hops) to {name}...',
      'toast.ping_ok':             '🎯 Pong received from {name}: {rtt}{snr}',
      'toast.ping_err':            '⚠️ No Ping response from {name}',

      // Common
      'common.you':                'You',
      'common.anonymous':          'Anonymous',
      'common.local_station':      'Local Station (You)',
      'common.online':             'Online',
      'common.offline':            'Offline',
      'common.no_gps':             'No GPS',
      'common.repeater':           'Repeater',
      'common.node':               'Node',

      // Settings actions
      'settings.action_clear_stats': 'Clear Stats',
      'settings.action_clear_stats_title': 'Reset packet counters, duplicates and airtimes',

      // Additional Chat keys
      'chat.add_channel_title':    'Create / Join channel',
      'chat.import_channel_title': 'Import channel or contact',
      'chat.share_location_title': 'Share my current GPS location in chat',
      'chat.qr':                   'QR',

      // Additional Map keys
      'map.fit_bounds':            'Fit map to all nodes with GPS',
      'map.center_local':          'Center on my local node',

      // Additional Logs & Sniffer keys
      'logs.subtab_logs':          'System Logs',
      'logs.subtab_sniffer':       'RF Packet Monitor (LoRa Sniffer)',
      'logs.debug_mode':           'DEBUG Mode',
      'logs.download_log':         'Download .log',
      'logs.pause_scroll':         'Pause Scroll',
      'logs.resume_scroll':        'Resume Scroll',
      'logs.level_label':          'Level:',
      'logs.search_placeholder':   'Search in logs (module, error, text)...',
      'sniffer.title':             'RF Packet Monitor (LoRa Sniffer)',
      'sniffer.subtitle':          'Live capture and analysis of on-air LoRa MeshCore binary frames.',
      'sniffer.pause_btn':         'Pause Capture',
      'sniffer.resume_btn':        'Resume Capture',
      'sniffer.clear_btn':         'Clear Packets',
      'sniffer.export_pcap':       'Export PCAP',
      'sniffer.export_json':       'Export JSON',
      'sniffer.export_csv':        'Export CSV',
      'sniffer.search_placeholder':'Search by pubkey, text or hex...',

      // Additional Settings keys
      'settings.subtab_telem':     'Telemetry & Status',
      'settings.subtab_radio':     'RF & Radio Parameters',
      'settings.subtab_identity':  'Identity & GPS Position',
      'settings.subtab_terminal':  'Terminal',
      'settings.subtab_maps':      'Offline Maps',
      'settings.subtab_security':  'Security & API',
      'settings.refresh':          'Refresh Parameters',
      'settings.hw_actions_title': 'Quick Hardware Actions',
      'settings.hw_actions_sub':   'Execution commands and direct control over microcontroller and LoRa transceiver',
      'settings.action_advert_hop':'Advert Hop 0',
      'settings.action_advert_flood':'Advert Flood',
      'settings.action_stats':     'Hardware Stats',
      'settings.action_sync_rtc':  'Sync RTC',
      'settings.action_clear_stats':'Clear Stats',
      'settings.action_reconnect_serial':'Reconnect Serial',
      'settings.action_reboot':    'Reboot Node',

      // Language toggle
      'lang.current':      'EN',
      'lang.switch':       '🌐 ES',
      'lang.title':        'Cambiar a Español',

      // App orchestration & status
      'app.web_online':             'Web: Connected',
      'app.web_connecting':         'Web: Connecting…',
      'app.web_offline':            'Web: Disconnected',
      'app.radio_online':           'Radio: Connected ({port})',
      'app.radio_online_fallback':  'Radio: Connected',
      'app.radio_offline':          'Radio: Disconnected',
      'app.dark_theme_title':       'Switch to light theme',
      'app.light_theme_title':      'Switch to dark theme',

      // Time & Presence
      'time.online_local':          'Online (Local)',
      'time.offline_no_signal':     'Disconnected (No signal)',
      'time.active_now':            'Active (just now)',
      'time.active_mins':           'Active ({n}m ago)',
      'time.active_hours':          'Active ({n}h ago)',
      'time.idle_hours':            'Idle ({n}h ago)',
      'time.offline_days':          'Disconnected ({n}d ago)',
      'time.last_signal_tooltip':   'Last signal received: {time}',
      'time.no_signal':             'No signal recorded',
    },
  };

  // ── Selector → i18n key map (static DOM elements) ──────────────────────────
  // Each entry: { s: CSS selector, k: key, a?: attribute, last?: bool }
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

    // Global search hint & Header metrics
    { s: '.search-hint',                 k: 'search.global_placeholder' },
    { s: '#globalSearchInput',           k: 'search.global_placeholder', a: 'placeholder' },
    { s: '.header-metrics .metric-chip:nth-child(1)', k: 'header.active_nodes', a: 'title' },
    { s: '.header-metrics .metric-chip:nth-child(2)', k: 'header.rx_packets', a: 'title' },
    { s: '.header-metrics .metric-chip:nth-child(3)', k: 'header.tx_packets', a: 'title' },
    { s: '#headerAirtimeChip',           k: 'header.airtime', a: 'title' },
    { s: '.header-metrics .metric-chip:nth-child(5)', k: 'header.error_rate', a: 'title' },
    { s: '.header-metrics .metric-chip:nth-child(6)', k: 'header.tx_queue', a: 'title' },

    // Chat
    { s: '#sidebarChannelList .chat-channels-header:first-of-type .panel-title', k: 'chat.channels' },
    { s: '#sidebarChannelList .chat-channels-header:nth-of-type(2) .panel-title', k: 'chat.direct_messages' },
    { s: '#btnAddChannel',               k: 'chat.add_channel_title', a: 'title' },
    { s: '#btnImportData',               k: 'chat.import_channel_title', a: 'title' },
    { s: '#chatInputText',               k: 'chat.input_placeholder', a: 'placeholder' },
    { s: '#clearChatBtn',                k: 'chat.clear', last: true },
    { s: '#btnShareLocation',            k: 'chat.share_location_title', a: 'title' },
    { s: '#btnSendMsg span:first-child', k: 'chat.send' },

    // Nodes section
    { s: '#tab-nodes .pane-header h2',   k: 'nodes.title', last: true },
    { s: '#tab-nodes .pane-header .header-subtitle', k: 'nodes.subtitle' },
    { s: '#nodesSearchInput',            k: 'nodes.search_placeholder', a: 'placeholder' },
    { s: '.filter-pill[data-filter="all"]', k: 'nodes.filter_all', last: true },
    { s: '.filter-pill[data-filter="REPEATER"]', k: 'nodes.filter_repeaters', last: true },
    { s: '.filter-pill[data-filter="SENSOR"]', k: 'nodes.filter_sensors', last: true },
    { s: '.filter-pill[data-filter="ROOM"]', k: 'nodes.filter_rooms', last: true },
    { s: '.filter-pill[data-filter="CLIENT"]', k: 'nodes.filter_clients', last: true },

    // Contacts section
    { s: '#tab-contacts .pane-header h2', k: 'contacts.title', last: true },
    { s: '#tab-contacts .pane-header .header-subtitle', k: 'contacts.subtitle' },
    { s: '#contactsSearchInput',         k: 'contacts.search_placeholder', a: 'placeholder' },
    { s: '#btnRefreshContacts',          k: 'contacts.refresh', last: true },
    { s: '#btnOpenAddContact',           k: 'contacts.add', last: true },
    { s: '.contact-filter-pill[data-filter="all"]', k: 'contacts.filter_all', last: true },
    { s: '.contact-filter-pill[data-filter="favorites"]', k: 'contacts.filter_favorites', last: true },
    { s: '.contact-filter-pill[data-filter="online"]', k: 'contacts.filter_online', last: true },
    { s: '.contact-filter-pill[data-filter="gps"]', k: 'contacts.filter_gps', last: true },

    // Map layers
    { s: '.map-layer-btn[data-layer="dark"]',         k: 'map.dark',      last: true },
    { s: '.map-layer-btn[data-layer="osm"]',          k: 'map.streets',   last: true },
    { s: '.map-layer-btn[data-layer="satellite"]',    k: 'map.satellite', last: true },
    { s: '.map-layer-btn[data-layer="local"]',        k: 'map.local',     last: true },
    { s: '#btnToggleHeatmap',            k: 'map.heatmap', last: true },
    { s: '#btnFitBounds',                k: 'map.fit_bounds', a: 'title' },
    { s: '#btnCenterLocal',              k: 'map.center_local', a: 'title' },

    // Analytics section
    { s: '#tab-analytics .pane-header h2', k: 'analytics.title', last: true },
    { s: '#tab-analytics .pane-header .header-subtitle', k: 'analytics.subtitle' },
    { s: '#btnRefreshAnalytics',         k: 'analytics.refresh', last: true },
    { s: '#btnResetMetricsText',         k: 'analytics.reset', last: true },
    { s: '#btnResetMetrics',             k: 'analytics.reset_title', a: 'title' },
    { s: '#cardKpiPackets .kpi-label',   k: 'analytics.kpi_packets' },
    { s: '#cardKpiNodes .kpi-label',     k: 'analytics.kpi_nodes' },
    { s: '#cardKpiErrorRate .kpi-label', k: 'analytics.kpi_error_rate' },
    { s: '#cardKpiQueue .kpi-label',     k: 'analytics.kpi_queue' },
    { s: '#cardTopActive .card-header h3', k: 'analytics.top_active', last: true },
    { s: '#cardTopActive .card-header .card-sub', k: 'analytics.top_active_sub' },
    { s: '#cardSignal .card-header h3',  k: 'analytics.signal', last: true },
    { s: '#cardSignal .card-header .card-sub', k: 'analytics.signal_sub' },
    { s: '#cardRepeaters .card-header h3', k: 'analytics.repeaters', last: true },
    { s: '#cardRepeaters .card-header .card-sub', k: 'analytics.repeaters_sub' },
    { s: '#cardBridge .card-header h3',  k: 'analytics.bridge', last: true },
    { s: '#cardBridge .card-header .card-sub', k: 'analytics.bridge_sub' },

    // Logs section
    { s: '#btnSubtabLogs',               k: 'logs.subtab_logs', last: true },
    { s: '#btnSubtabSniffer',            k: 'logs.subtab_sniffer', last: true },
    { s: '#subpanelSystemLogs .pane-header h2', k: 'logs.title', last: true },
    { s: '#subpanelSystemLogs .pane-header .header-subtitle', k: 'logs.subtitle' },
    { s: '#btnToggleDebugMode',          k: 'logs.debug_mode', last: true },
    { s: '#btnDownloadRawLogs',          k: 'logs.download_log', last: true },
    { s: '#btnClearLogs',                k: 'logs.clear', last: true },
    { s: '#btnPauseLogsScroll',          k: 'logs.pause_scroll' },
    { s: 'label[for="logLevelFilter"]',  k: 'logs.level_label' },
    { s: '#logSearchInput',              k: 'logs.search_placeholder', a: 'placeholder' },

    // Sniffer
    { s: '#subpanelRfPackets .pane-header h2', k: 'sniffer.title', last: true },
    { s: '#subpanelRfPackets .pane-header .header-subtitle', k: 'sniffer.subtitle' },
    { s: '#btnToggleSnifferPause',       k: 'sniffer.pause_btn', last: true },
    { s: '#btnClearSnifferPackets',      k: 'sniffer.clear_btn', last: true },
    { s: '#btnExportPcap',               k: 'sniffer.export_pcap', last: true },
    { s: '#btnExportJson',               k: 'sniffer.export_json', last: true },
    { s: '#btnExportCsv',                k: 'sniffer.export_csv', last: true },
    { s: '#snifferSearchInput',          k: 'sniffer.search_placeholder', a: 'placeholder' },

    // Settings
    { s: '#tab-settings .pane-header h2', k: 'settings.title', last: true },
    { s: '#tab-settings .pane-header .header-subtitle', k: 'settings.subtitle' },
    { s: '#btnRefreshLocalConfig',       k: 'settings.refresh', last: true },
    { s: '.local-subtab-btn[data-subtab="local-telemetry"]', k: 'settings.subtab_telem', last: true },
    { s: '.local-subtab-btn[data-subtab="local-radio"]', k: 'settings.subtab_radio', last: true },
    { s: '.local-subtab-btn[data-subtab="local-owner-pos"]', k: 'settings.subtab_identity', last: true },
    { s: '.local-subtab-btn[data-subtab="local-console"]', k: 'settings.subtab_terminal', last: true },
    { s: '.local-subtab-btn[data-subtab="local-storage-maps"]', k: 'settings.subtab_maps', last: true },
    { s: '.local-subtab-btn[data-subtab="local-security"]', k: 'settings.subtab_security', last: true },
    { s: '.hardware-actions-section .micro-title', k: 'settings.hw_actions_title', last: true },
    { s: '.hardware-actions-section .micro-subtitle', k: 'settings.hw_actions_sub' },
    { s: '#btnActionAdvertHop .btn-compact-label', k: 'settings.action_advert_hop' },
    { s: '#btnActionAdvertFlood .btn-compact-label', k: 'settings.action_advert_flood' },
    { s: '#btnRefreshLocalTelem .btn-compact-label', k: 'settings.action_stats' },
    { s: '#btnSyncLocalClock .btn-compact-label', k: 'settings.action_sync_rtc' },
    { s: '#btnActionClearLocalStats .btn-compact-label', k: 'settings.action_clear_stats' },
    { s: '#btnActionClearLocalStats',    k: 'settings.action_clear_stats_title', a: 'title' },
    { s: '#btnActionReconnectSerial .btn-compact-label', k: 'settings.action_reconnect_serial' },
    { s: '#btnActionRebootLocal .btn-compact-label', k: 'settings.action_reboot' },

    // Modals
    { s: '#createChannelTitle',          k: 'modal.channel_title', last: true },
    { s: '#btnCancelCreateChannel',      k: 'modal.cancel' },
    { s: '#btnSaveChannel',              k: 'modal.save_channel', last: true },
    { s: '#createContactTitle',          k: 'modal.contact_title', last: true },
    { s: '#btnCancelCreateContact',      k: 'modal.cancel' },
    { s: '#btnSaveContact',              k: 'modal.save_contact', last: true },
    { s: '#qrShareTitle',                k: 'qr.title', last: true },
    { s: '#qrShareDesc',                 k: 'qr.scan_hint', last: true },
    { s: 'label[for="qrShareUri"]',      k: 'qr.uri_label' },
    { s: '#btnCopyQrUri',                k: 'qr.copy_btn', last: true },
    { s: 'label[for="qrShareJson"]',     k: 'qr.json_label' },
    { s: '#btnDownloadQrJson',           k: 'qr.download_json', last: true },
    { s: '#btnCloseQrModalAction',       k: 'qr.done' },
    { s: '#repeaterAuthGate h4',         k: 'rep.restricted_access' },
    { s: '#repeaterAuthGate p',          k: 'rep.restricted_desc' },
    { s: 'label[for="repeaterGatePassword"]', k: 'rep.pin_label' },
    { s: '#repeaterGatePassword',        k: 'rep.pin_placeholder', a: 'placeholder' },
    { s: '#btnRepeaterGateSubmit',       k: 'rep.unlock_btn', last: true },
    { s: '#btnRepeaterGateCancel',       k: 'modal.cancel' },

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
   * Set text of an element while preserving child icons/elements.
   */
  function _setElementText(el, text) {
    if (!el) return;
    if (el.children.length === 0) {
      el.textContent = text;
      return;
    }
    const textChild = el.querySelector('.btn-text, .nav-label, .subtab-text, .btn-compact-label, .kpi-label, .card-label, .val-label');
    if (textChild) {
      textChild.textContent = text;
      return;
    }
    const textNodes = Array.from(el.childNodes).filter(
      n => n.nodeType === Node.TEXT_NODE && n.textContent.trim().length > 0
    );
    if (textNodes.length > 0) {
      textNodes[textNodes.length - 1].textContent = '\u00A0' + text;
    } else {
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
        _setElementText(el, text);
      } else {
        el.textContent = text;
      }
    });
  }

  /** Apply all static DOM translations */
  function apply() {
    document.documentElement.lang = _lang;
    
    // 1. Static DOM_MAP rules
    DOM_MAP.forEach(_applyEntry);

    // 2. Declarative data-i18n attributes
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const k = el.getAttribute('data-i18n');
      _setElementText(el, t(k));
    });

    // 3. Declarative data-i18n-placeholder
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      const k = el.getAttribute('data-i18n-placeholder');
      el.setAttribute('placeholder', t(k));
    });

    // 4. Declarative data-i18n-title
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
      const k = el.getAttribute('data-i18n-title');
      el.setAttribute('title', t(k));
    });

    // 5. Declarative data-i18n-aria-label
    document.querySelectorAll('[data-i18n-aria-label]').forEach(el => {
      const k = el.getAttribute('data-i18n-aria-label');
      el.setAttribute('aria-label', t(k));
    });

    // Update lang button text + title
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
    // Dispatch event so app.js and other modules can react
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
