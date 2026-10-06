# Recepción, telemetría y contratos compartidos — segundo lote

Fecha: 2026-10-05. Base: `776eed7`. Responsable: agente principal.
Skills: async-concurrency-engineering, python-patterns-typing,
meshcore-source-inspector, security-code-auditor y bridge-test-runner.
Referencias sólo lectura; ningún transceptor, broker o dato operativo utilizado.

## Evidencia y método

test_remaining_core_audit.py reprodujo **24 fallos y cinco controles** antes
del parche. Sus 29 casos aprobaron después; se añadieron nueve controles de
sesión RF, límites observados, lookup y persistencia, TTL MQTT y paridad SDK.
La comprobación ampliada con dominio/reloj/persistencia dio **119 passed**,
3,34 s. Una ejecución anterior dio 118 aprobadas y un fallo de fixture:
intentaba mutar un modelo congelado. Se corrigió la construcción, conservando
todas las aserciones. Se añadieron regresiones por comportamiento observable.

RUNTIME-02: una ráfaga de 1000 ACK con consumidor lento retenía 1000 tareas.
La reproducción nueva dio cuatro fallos. El parche limita trabajos y tareas;
cinco regresiones finales incluyen el sink SystemHandler real bloqueado y
cancelación/rearranque. Comprobación conjunta RX/salud: **8 passed**, 0,70 s.
Integración intermedia: 99 aprobadas/1 fallo por MagicMock usado como sink async;
la fixture ahora refleja el método asíncrono real, sin reducir la expectativa.

La revisión final detectó otra salida desacoplada en Bridge._schedule_background:
1000 notificaciones de log retenían 1000 tareas aunque el router estuviera
acotado. La regresión adicional reprodujo ese fallo; después **48 casos** de
RX/TCP/core/políticas y **25 casos** de lifecycle/RX aprobaron. Son seis regresiones
RX nuevas. Overflow usa skip_broadcast para que su propio log no llene la cola.

La primera suite integrada de este lote dio 1363 aprobadas, tres fallos y una
omisión. Dos fallos reproducen la selección de un loop explícito inactivo:
Bridge elegía el loop actual, pero el pool RX seguía creando workers en el
inactivo. La admisión ahora selecciona también el loop en ejecución cuando el
configurado no está activo; las aserciones existentes se conservan. El tercer
fallo pertenece al borrado de logs y se registra en el anexo web.

Además, una regresión aislada mostró feedback local si el sink WebSocket falla:
el log de fallo del worker volvía a ese mismo sink (cuatro intentos en la
inyección finita, en lugar de uno). Ese log conserva su registro local y usa
skip_broadcast. La regresión falla antes y aprueba después; son siete casos RX
nuevos. El grupo final RX/core/lifecycle/TCP aprobó **50 casos en 1,77 s**.

PI-S05: **7 fallos/1 control antes**, ausencia de configuración TLS;
**11 passed**, 4,60 s después, incluyendo Paho real sobre TLS de loopback.
CA confiable y hostname correcto conectan; CA desconocida/hostname distinto
producen SSLCertVerificationError sin downgrade. El primer receptor de prueba
ignoraba los varios bytes de longitud MQTT: se corrigió ese fixture y se
conservó el resultado anterior de 10 aprobadas/1 fallo. cryptography es una
dependencia opcional de QA para generar certificados temporales, nunca runtime.

XML locales, fuera del commit: tests/artifacts/remaining-core-{before,after,verified}.xml,
remaining-rx-{before,after,health}.xml, remaining-runtime-integrated.xml y
remaining-tls-{before,after,verified,final}.xml. El seguimiento principal conserva
la verificación integrada y cobertura; estos pases focalizados no la sustituyen.

## RUNTIME-02 — admisión y ownership

El usuario aprobó **256 trabajos RX pendientes**, **200 ACK pendientes** y
vigencia ACK de **3600 s**. La concurrencia existente es 20 por defecto,
configurable mediante MAX_RX_CONCURRENCY. Una deque acotada retiene factorías
de corutinas; un pool crea como máximo esa concurrencia de workers. Despacho,
broadcasts y sincronización local de rutas comparten admisión. Las estrategias
admin/System esperan sus sinks en el worker, sin tareas secundarias desacopladas.
Las factorías de log/notificación/TCP que el bridge inicia en su loop también
entran al pool. Los callbacks desde otro hilo se publican al loop propietario;
la reserva MQTT previa al post se trata en PI-S06. No se certifica un límite
universal del ready queue de asyncio ni una entrega pública sin saturación.
El máximo cuenta trabajos, no 256 paquetes más sinks sin límite.

Sólo snapshots de igual identidad se agrupan: advert por emisor, actualización
de contacto y lectura de ruta local. Chat, ACK y respuestas solicitadas conservan
identidad. Un trabajo crítico puede desplazar una observación pendiente.
Si todos los pendientes son críticos, el nuevo trabajo público se rechaza con
RX-OVERFLOW y err_count; nunca se anuncia procesado. La entrega SDK directa
a sus waiters es independiente; esto no promete entrega pública ilimitada ni
la de un observador cuyo único ingreso sea este router. La operación afectada
mantiene su timeout/error, sin confirmar datos ausentes.

rx_overflow_count/rx_coalesced_count describen la política. Estado expone
error_count y el reporte periódico de salud añade total_processing_errors,
sin otro timer. Los workers terminan al vaciar la cola; cancelación elimina
factorías sin dejar corutinas sin await. El callback RX pertenece al loop;
la reserva MQTT entre hilos se corrige/documenta por separado.

## RUNTIME-07 — FIFO

TxItem compara prioridad y contador. created_at es metadato sin comparación.
Primer elemento timestamp 100, segundo 90, misma prioridad: antes salía el
segundo; ahora primero/segundo. Sin límites, airtime ni reintentos nuevos.

## PI-07 — unidades y flags

solar_mv siempre se divide entre 1000, incluso 0/100; solar_v/solar_voltage
conservan voltios, incluso 120. Sólo el alias histórico solar sin unidad conserva
su heurística previa. battery_mv/voltage_v preservan milivoltios: 3875 → 3,875 V.
fixed_position admite bool, int 0/1 y tokens booleanos conocidos. Fracciones,
NaN, contenedores y tokens ambiguos no inventan estado. No se migra historial
sin procedencia ni se afirma que un porcentaje estimado sea lectura física.

## PI-08 — CayenneLPP

Se reconocen generic sensor, current, frequency, altitude, load, concentration,
power, distance, energy, direction, time, colour y switch. Cada registro conserva
tamaño exacto; current 117 deja decodificar la temperatura siguiente. Binario
y JSON SDK comparten nombres/unidades, incluyendo listas escalares y códigos
numéricos conocidos. Layout: channel/type, enteros big endian, sin padding ni
CRC interno (la envoltura pertenece al SDK). CURRENT: 2 bytes signed/1000 A;
COLOUR: tres bytes red/green/blue. LOAD 122 (3 bytes signed/1000) es extensión
Python, no tipo declarado por CayenneLPP C++ 1.6.1. Voltage/current usan signo.
Desconocidos/truncados siguen deteniendo el decoder; no se inventa la frontera.

Fuentes: [SDK encoder](../../../reference/meshcore_py/src/meshcore/lpp_json_encoder.py),
[dependencia firmware](../../../reference/meshcore/platformio.ini),
[CayenneLPP 1.6.1](https://raw.githubusercontent.com/ElectronicCats/CayenneLPP/1.6.1/src/CayenneLPP.cpp)
y tabla cayennelpp instalada para QA. Sin cambios en referencias/dependencias.

## Backend de WEB-09/10/11

NodeContactInfo.to_dict no deriva límites desde el nombre de placa.
max_tx_power sólo conserva lo recibido; min/default son None sin evidencia.
tx_power_limits_source indica observed/unknown. La UI distingue medidas/rangos.
PacketBuffer conserva asc por defecto y añade desc antes de paginar; total se
calcula después de filtrar. La SPA pide la cola reciente y pinta cronológicamente.
CapturedPacket incluye session_id UUID por instancia; clear conserva contador
y sesión. Reinicios con packet_id repetido no confunden capturas. Merge HTTP/WS
por identidad/generación: [anexo web](web-remaining.md).

## PI-S05 — TLS MQTT

MQTTConfig añade tls_enabled y rutas CA/certificado/clave. MQTT_TLS permite
activarlo desde entorno; token ambiguo se rechaza. Certificado/clave cliente
deben ir juntos; archivos TLS con TLS desactivado se rechazan. El contexto
conserva CERT_REQUIRED/verificación de hostname. Sin CA explícita se usa
confianza del sistema; el par cliente permite mTLS. Se configura antes de
conectar, sin fallback plaintext ante fallo. No hereda SSLKEYLOGFILE.
Defaults locales y broker/puerto existentes se conservan; el operador configura
su listener/material de confianza y reinicia. No se activa TLS en una estación
operativa ni se acredita el certificado de ningún broker externo.

Fuentes: [Python SSL](https://docs.python.org/3/library/ssl.html#ssl.create_default_context)
y [Paho](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html#paho.mqtt.client.Client.tls_set_context).

## Deuda resuelta y límites

NodeRegistry._nodes_by_name se retiró: sólo se escribía. find_by_name conserva
registro canónico y ambigüedad, con controles rename/alias/borrado/JSON reload.
publish_safe mantiene ttl_seconds por compatibilidad pero una caducidad explícita
devuelve False/warning unsupported. MQTT 3 no promete una expiración inexistente;
la publicación habitual sigue igual. No se borran APIs públicas/callbacks/scratch
por ausencia de callers léxicos. No se certifica optimalidad de todos los métodos.

## Impacto en la malla

1. Airtime adicional: cero; cambios locales de RX/FIFO/parser/TLS. Batería se
   consulta bajo demanda por el executor, sin sondeo periódico nuevo.
2. Spam/feedback: sin retransmisión RF ni publicación automática nueva. Saturación
   se hace visible localmente, sin convertirla en un bucle de reintentos.
3. Guardado/timers: no arma scheduler ni cambia intervalos. ACK utiliza el
   mantenimiento existente y límites acordados. Persistencia cooldown tiene
   anexo propio; guardar no envía radio automáticamente.
