# Lectura y navegación del chat — 2026-10-18

Implementación de la investigación realizada con tres agentes: distribución del
espacio, legibilidad y verificación. Se conserva Vanilla CSS/JS, el renderizado
literal de texto y los contratos de mensajería y almacenamiento.

## Cambios

- Texto del chat a 1rem (16px con raíz estándar), interlineado 1,55 y burbujas hasta
  `min(96%,72ch)`. El mensaje breve conserva ancho natural; no se fuerza ancho total.
- Padding de historial de 12px en escritorio y 8px en móvil, interior de burbuja
  de 10×12px, separación de paneles de 12px y primer separador de fecha compacto.
- Pie de hora y ACK adaptable, con indicador que no se encoge. Se conservan
  saltos explícitos, mensajes escapados y tarjetas de contacto/canal/GPS.
- Drawer y JS usan el mismo umbral de 991,98px para inicialización y selección
  de canal o DM. La preferencia global de navegación compacta sigue siendo manual.
- Los mensajes recibidos o publicados externamente conservan la posición del
  lector cuando está arriba, incluso si el mensaje externo figura como saliente.
  Si ya estaba al final, se sigue el final. Los envíos explícitos del compositor
  también se muestran al final.
- Un botón con cantidad permite llegar a mensajes nuevos sin cubrir el historial
  ni el compositor. Se puede activar por teclado; después el foco pasa al log.
  El indicador se limpia al volver abajo, cambiar conversación, limpiar caché o
  denegar acceso. Repaint del mismo feed conserva el contador y su idioma.
  Un `ResizeObserver` del feed limpia también el aviso si al redimensionar todo el
  contenido queda visible; no se usan intervalos ni observers por mensaje.
- Las pruebas visuales detectaron contraste insuficiente en colores previos del
  tema claro (radio conectada, verde de métricas y etiquetas sensor/repetidor/sala).
  Se oscurecen los cuatro acentos de texto correspondientes y el verde Bootstrap;
  radio conectada reutiliza el acento semántico. No se cambia la lógica de estados.

## Evidencia

Las regresiones reproducen antes del parche el salto desde scrollTop120 a más de
6100 al añadir un mensaje y el drawer persistente al seleccionar un DM a950px.
Después del primer parche pasan las nueve regresiones iniciales. Se amplían con
móvil/escritorio, envío propio, refresh y cambio de tamaño. La prueba adicional
de resize reproduce antes de su corrección un aviso visible sin overflow. Los resultados finales
se registran en `tests/artifacts/chat-reading-fix/`.

Las capturas estáticas con los informes del usuario verifican texto16px e
interlineado24,8px: seis líneas a390px y cinco a1024/1920px en ambos temas, sin
desbordamiento horizontal. Son capturas del componente, sin scripts de aplicación;
la verificación funcional usa las fixtures de estación virtual mantenidas.

## Resultado final

| Comprobación | Resultado |
|---|---|
| Chat, canales/DM, fragmentación, ACK, almacenamiento y aislamiento (`final-functional.xml`) | 50 pases |
| Reflow, temas, idiomas y controles (`final-visual.xml`) | 23 pases iniciales; 2 fallos de contraste detectados y corregidos |
| Revalidación de los dos fallos y tokens (`final-contrast.xml`) | 3 pases |
| Regresiones finales de lectura y navegación (`final-reading.xml`) | 12 pases, incluido resize |
| Casos distintos, tomando el último resultado de cada caso | 76 aprobados; sin errores o skips |
| Ruff y mypy estricto del módulo de regresiones nuevo | Sin incidencias |
| Auditoría ES/EN | 1651 claves por idioma; sin hallazgos estáticos |
| Resolución de imports ESM | 19 módulos; sin advertencias |
| Build/check y hashes de fuente/minificado/gzip | 31 assets coherentes |

Los reportes se solapan: no se suman sus ejecuciones para inflar el número de
casos distintos. Los bloques amplios se revalidan con casos específicos cuando
hay correcciones posteriores. No se afirma ejecución de toda la suite Python.

Las combinaciones de texto que fallaron en claro tenían ratios entre 2,94 y 4,40:1.
Los nuevos colores calculan, sobre esos fondos, entre 4,59 y 5,52:1; las pruebas de
navegador vuelven a aprobar los dos escenarios. No se relajan sus expectativas.

Se normalizaron únicamente finales CRLF a LF de tres fuentes ya idénticas al
índice Git, conforme a `.gitattributes`, para que el manifiesto coincida también
con los bytes publicados. No se cambió su contenido ni sus artefactos servidos.

## Alcance

No se añaden emisiones RF, reintentos, consultas periódicas, notificaciones MQTT
ni cambios de radio. El indicador es una acción local de navegación. No cambia
el rate limiter, el historial SQLite, los ACK ni los límites de transmisión.

Las pruebas usan temporales, radio virtual, loopback asignado por el SO y cierre
de browser/servidor/tareas en fixtures. No se usa hardware o broker operativo.
No se ejecuta la suite completa de backend ni se mide cobertura global por este
cambio. El contraste y reflow ensayados no acreditan accesibilidad completa.
