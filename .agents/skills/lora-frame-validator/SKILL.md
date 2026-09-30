---
name: lora-frame-validator
description: >-
  Herramienta de análisis de checksums y del formato sintético legado usado por simuladores del bridge.
  NO representa el framing Companion oficial de MeshCore ni el layout on-air de Packet.h. Para capturas
  MeshCore reales, identificar primero la capa: Companion 0x3C/0x3E o paquete LoRa Packet.h.
---

# Legacy/Synthetic Frame & Checksum Validator Skill

Esta skill valida el formato sintético `0xAA/0x55/ESC/CRC` conservado para pruebas internas y puede calcular checksums sobre dumps arbitrarios. No debe utilizarse como evidencia de que MeshCore Companion o `Packet.h` usan ese framing.

## Scripts y Herramientas

El script principal de validación se encuentra en:
[validate_frame.py](./scripts/validate_frame.py)

## Modos de Uso

### 1. Validación de Trama Hexadecimal
```bash
python .agents/skills/lora-frame-validator/scripts/validate_frame.py --hex "AA0100080102030405060708C8B555" --sof AA --eof 55 --crc-type ccitt
```

### 2. Detección Automática de CRC
Calcula simultáneamente CRC-16 CCITT, CRC-16 IBM, CRC-32, Fletcher-16 y XOR para identificar qué algoritmo coincide con el checksum embebido:
```bash
python .agents/skills/lora-frame-validator/scripts/validate_frame.py --hex "AA02000000000000BEEF55"
```

### 3. Salida Estructurada en JSON
```bash
python .agents/skills/lora-frame-validator/scripts/validate_frame.py --hex "AA0102030455" --format json
```

### 4. Inspección de Archivos Binarios o Dumps de Tráfico
```bash
python .agents/skills/lora-frame-validator/scripts/validate_frame.py --file captures/serial_dump.bin
```
