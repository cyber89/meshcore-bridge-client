# Inventario DOM completo de configuración

HEAD `9f561932d648470e8c8bd23fc789a66bdb378d0e`. Extraído de Chromium con HTML actual; valores y restricciones en JSON. La presencia de control y serialización no acredita soporte firmware ni readback. Contrastar cada clave con matriz backend/protocolo.

| Control | Sección/API | Clave/efecto serializado | Tipo/restricciones nativas |
|---|---|---|---|
| localFreq | GET /api/config; POST /api/config/radio | frequency | number, required, step=0.025 |
| localRegion | GET /api/config; POST /api/config/radio | (preset local; no se serializa región) | select-one |
| localTxPower | GET /api/config; POST /api/config/radio | tx_power | range, min=2, max=22, step=1 |
| localHopLimit | GET /api/config; POST /api/config/radio | hop_limit | number, required, min=1, max=7 |
| localSf | GET /api/config; POST /api/config/radio | spreading_factor | select-one |
| localBw | GET /api/config; POST /api/config/radio | bandwidth | select-one |
| localCr | GET /api/config; POST /api/config/radio | coding_rate | select-one |
| localRepeatMode | GET /api/config; POST /api/config/radio | repeat | checkbox |
| localAdvertEnable | GET /api/config; POST /api/config/radio | advert_interval=0 si OFF | checkbox |
| localAdvertInterval | GET /api/config; POST /api/config/radio | advert_interval + beacon_interval | number, min=30, max=86400 |
| localTelemetryEnable | GET /api/config; POST /api/config/radio | telemetry_interval=0 + telemetry_mode_base=0 si OFF | checkbox |
| localTelemetryInterval | GET /api/config; POST /api/config/radio | telemetry_interval | number, min=10, max=3600 |
| localDevicePin | GET /api/config; POST /api/config/radio | pin (vacío → 0) | number, min=0, max=999999 |
| localPathHashMode | GET /api/config; POST /api/config/radio | path_hash_mode | select-one |
| localRxDelay | GET /api/config; POST /api/config/radio | rx_delay | number, min=0, max=100000 |
| localAirtimeFactor | GET /api/config; POST /api/config/radio | airtime_factor | number, min=0, max=1000 |
| localTelemBase | GET /api/config; POST /api/config/radio | telemetry_mode_base | select-one |
| localTelemLoc | GET /api/config; POST /api/config/radio | telemetry_mode_loc | select-one |
| localTelemEnv | GET /api/config; POST /api/config/radio | telemetry_mode_env | select-one |
| localAdvLocPolicy | GET /api/config; POST /api/config/radio | adv_loc_policy | checkbox |
| localMultiAcks | GET /api/config; POST /api/config/radio | multi_acks | checkbox |
| localManualAddContacts | GET /api/config; POST /api/config/radio | manual_add_contacts | checkbox |
| inputCustomVarKey | GET/POST /api/config/custom_vars | key | text, required |
| inputCustomVarVal | GET/POST /api/config/custom_vars | value | text, required |
| localNodeName | GET /api/config; POST /api/config/identity | name | text, required |
| localNodePubkey | GET /api/config; POST /api/config/identity | public_key (sólo lectura) | text, readonly |
| localOwnerInfo | GET /api/config; POST /api/config/identity | owner_info | text |
| localGpsLat | GET /api/config; POST /api/config/identity | latitude (requiere lon) | number, min=-90, max=90, step=0.000001 |
| localGpsLon | GET /api/config; POST /api/config/identity | longitude (requiere lat) | number, min=-180, max=180, step=0.000001 |
| localGpsAlt | GET /api/config; POST /api/config/identity | altitude_m (sólo con lat/lon) | number, step=1 |
| localPosFixed | GET /api/config; POST /api/config/identity | fixed_position | checkbox |
| localTerminalInput | POST /api/admin | command/action local | text |
| chkChatSoundAlerts | localStorage | sonido host | checkbox |
| inputLocalTileUrl | localStorage / mapa | URL tiles host | text |
| (input sin id) | Autocompletado invisible | username; no parámetro nodo | text |
| inputBridgeApiKey | localStorage / headers HTTP | API key bridge, no parámetro nodo | password |
| inputFloodScope | GET/POST /api/config/flood_scope | scope | text |
| chkAutoAddChat | GET/POST /api/config/autoadd | flags bit 1 | checkbox |
| chkAutoAddOverwrite | GET/POST /api/config/autoadd | flags bit 0 | checkbox |
| numAutoAddMaxHops | GET/POST /api/config/autoadd | max_hops | number, min=0, max=7 |
| (input sin id) | Autocompletado invisible | username; no parámetro nodo | text |
| repeaterGatePassword | POST /api/repeater/remote/login | password RF | password, required |
| adminModalNodePk | presentación sólo lectura | identidad destino | hidden |
| repQuickCmdInput | POST /api/repeater/remote/action | action CLI RF | text |
| radioFreq | POST /api/repeater/remote/config | freq | number, step=0.025 |
| radioRegion | POST /api/repeater/remote/config | region | select-one |
| radioPower | POST /api/repeater/remote/config | tx_power | range, min=2, max=22, step=1 |
| radioHopLimit | POST /api/repeater/remote/config | hop_limit | number, min=1, max=7 |
| radioSf | POST /api/repeater/remote/config | sf | select-one |
| radioBw | POST /api/repeater/remote/config | bw | select-one |
| radioCr | POST /api/repeater/remote/config | cr | select-one |
| radioRepeatMode | POST /api/repeater/remote/config | repeat | checkbox |
| radioBeaconInterval | POST /api/repeater/remote/config | beacon_interval | number, min=30, max=86400 |
| repOwnerName | POST /api/repeater/remote/config | owner_name | text |
| repOwnerInfo | POST /api/repeater/remote/config | owner_info | text |
| repPosLat | POST /api/repeater/remote/config | lat | number, step=0.00001 |
| repPosLon | POST /api/repeater/remote/config | lon | number, step=0.00001 |
| repPosAlt | POST /api/repeater/remote/config | alt | number, step=0.1 |
| repPosFixed | POST /api/repeater/remote/config | fixed + fixed_position | checkbox |
| (input sin id) | Autocompletado invisible | username; no parámetro nodo | text |
| secNewAdminPwd | POST /api/repeater/remote/config | new_password (sólo escritura) | password |
| secNewGuestPwd | POST /api/repeater/remote/config | guest_password (sólo escritura) | password |
| secAclMode | POST /api/repeater/remote/config | acl_mode (sólo dirty) | select-one |
| secIdentityKey | POST /api/repeater/remote/config | identity_key (sólo escritura) | text |
| repeaterTerminalInput | POST /api/repeater/remote/action | action CLI RF | text |

## Lectura y escritura por grupos

- Radio/identidad local: populateLocalConfig actualiza desde GET/self_info; saveRadio/saveIdentity construyen lote completo y consumen data.config. El estado dirty sólo protege la lectura; no filtra el lote de escritura. PIN no debe tener readback público: vacío implica conservar, nunca borrar por defecto.
- Radio/identidad remoto: populateRepeaterModalData se nutre de Map/eventos/lectura CLI; save escribe lote completo. Resultado no acredita aplicado (VUI01).
- Seguridad remota: passwords/identity_key son sólo escritura; no se exige leer secretos. ACL requiere catálogo oficial/capability: sus tres opciones no equivalen por sí solas a ACL setperm.
- AutoAdd, Scope, custom vars usan endpoints dedicados. No se hicieron escrituras de esos endpoints al hardware; AutoAdd sí tiene diagnóstico de borrador perdido.
- Mapas, API key y sonido pertenecen al host/navegador; no se deben acreditar como parámetros del nodo.
- Acciones: actualización local GET?refresh=true, sync-clock, advert directo/flood, reconnect, reboot, clear-stats; consultas remotas refresh_telemetry/get radio/owner/regions/acl/neighbours y sync_clock/advert/reboot/clear stats/terminal. La conexión/sesión/capacidad debe verificarse por operación.
- Públicas claves/firmware/placa/conexión/batería/voltaje/temperatura/reloj/uptime/noise/SNR/RSSI/airtime/duty/contadores/colas/ruta se presentan como estado de sólo lectura. Deben conservar desconocido/antigüedad y no sustituirse por valores de ejemplo.

El JSON registra opciones completas de todos los selectores y labels traducidos. Las 65 entradas incluyen tres username ocultos sin id.
