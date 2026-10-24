# 🗺️ Almacenamiento de Mapas Offline para MeshCore Bridge

Este directorio permite servir teselas cartográficas locales sin descargarlas de Internet. La interfaz actual carga Leaflet desde un CDN; disponer de teselas locales no garantiza un arranque completo de la SPA sin conexión.

---

## 📁 Estructuras de Mapas Soportadas

### Opción 1: Archivos SQLite MBTiles (`*.mbtiles`) - **Recomendado**
Simplemente copia tus bases de datos `.mbtiles` (raster PNG/JPEG) directamente dentro de esta carpeta (`data/maps/`):
```text
data/
└── maps/
    ├── guantanamo.mbtiles
    ├── cuba_osm.mbtiles
    └── mi_region.mbtiles
```
*El bridge indexa las bases de datos `.mbtiles` al iniciar el servicio de mapas. Tras añadir o sustituir archivos, solicita `POST /api/map/reload` con la autenticación y protección CSRF correspondientes, o reinicia el bridge; no hay un observador automático de archivos.*

---

### Opción 2: Mosaicos Sueltos XYZ (`tiles/{z}/{x}/{y}.png`)
Puedes descomprimir o exportar carpetas de teselas estándar XYZ:
```text
data/
└── maps/
    └── tiles/
        ├── 10/
        │   └── 305/
        │       └── 450.png
        └── 11/
            └── 610/
                └── 900.png
```

---

## 🌐 Endpoint del Servidor Local
El bridge expone automáticamente el endpoint local:
- **URL de Teselas**: `/api/map/tiles/{z}/{x}/{y}.png`
- **Estado de Mapas**: `/api/map/status`
