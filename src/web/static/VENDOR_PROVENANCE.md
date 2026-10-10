# Bibliotecas del frontend

Revisión: 2026-10-10. Estos recursos se ejecutan en el navegador; su versión no
depende de la versión del intérprete Python del bridge.

| Biblioteca | Versión previa | Versión actual | Distribución |
| --- | --- | --- | --- |
| Bootstrap CSS y bundle JS | 5.3.3 | 5.3.8 | Archivos locales oficiales; el bundle incluye Popper. |
| Bootswatch Temas Zephyr y Slate | - | 5.3.8 | Archivos locales compilados de Bootswatch (Zephyr para claro, Slate para oscuro). |
| Bootstrap Icons CSS y fuentes WOFF/WOFF2 | 1.11.3 | 1.13.2 | Archivos locales del mismo paquete/version. |
| Leaflet | 1.9.4 | 1.9.4 | CDN unpkg con los hashes SRI existentes; última estable consultada. |

Fuentes primarias: [Bootstrap](https://getbootstrap.com/docs/5.3/getting-started/download/),
[release de Icons](https://github.com/twbs/icons/releases/tag/v1.13.2),
[registro npm Bootstrap](https://registry.npmjs.org/bootstrap/5.3.8),
[registro npm Icons](https://registry.npmjs.org/bootstrap-icons/1.13.2) y
[registro npm Leaflet](https://registry.npmjs.org/leaflet/latest).
La rama Leaflet 2.0 alpha no se seleccionó como versión estable.

Los tarballs npm se descargaron a staging y se verificaron contra `dist.integrity`
SHA512 del registro oficial antes de copiar. No se extrajo el archivo completo:
se rechazaron miembros con rutas absolutas, traversal o enlaces y se copiaron
únicamente los siete archivos mapeados, dentro de `src/web/static`. Se mantuvieron
las rutas existentes de CSS, JS y fuentes. Las licencias MIT originales están en
`licenses/bootstrap.txt` y `licenses/bootstrap-icons.txt`.

`vendor-manifest.json` registra URL/version del paquete, integridad npm, SHA256 del
tarball y SHA256/tamaño de cada archivo. Los archivos copiados se volvieron a
hashear; `.gitattributes` mantiene LF para CSS, bundle y licencias al hacer checkout
en cualquier plataforma. Esta comprobación de integridad y procedencia no acredita compatibilidad
visual; la verificación de navegador se registra en el informe QA del proyecto.

La SPA utiliza fuentes de sistema y ya no solicita Inter/Fira Code desde el HTML.
El build genera `css/bootstrap-zephyr.local.min.css` eliminando únicamente el
`@import` de Google Fonts del tema Zephyr; conserva el archivo oficial, su licencia
y los hashes de `vendor-manifest.json`. `asset-manifest.json` registra los hashes
de origen, variante servida y gzip. El servidor selecciona esta variante cuando
coinciden los hashes; sin build válido sirve el original oficial (que conserva su
import de fuentes). Los mapas remotos usan teselas OpenStreetMap y Esri; son servicios,
no bibliotecas versionadas. El generador QR local declara implementación propia y
no un paquete npm con versión. Los assets de skills de terceros y snapshots de
`reference/` quedan fuera de esta actualización.

La comprobación del 2026-10-10 detectó que el SHA256 registrado para
`licenses/bootswatch.txt` duplicaba el de la licencia Bootstrap. Se corrigió el
hash observado del archivo local en el manifest, conservando sus bytes. Esta
corrección acredita integridad del checkout; no se volvió a descargar ni a
validar el origen declarado de esa licencia.
