# 🗺️ Almacenamiento de Mapas Offline para MeshCore Bridge

Este directorio permite almacenar mapas cartográficos para operar **100% fuera de línea (sin conexión a Internet)**.

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
*El bridge detectará, indexará y servirá automáticamente todas las bases de datos `.mbtiles` sin necesidad de reiniciar el servidor.*

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
