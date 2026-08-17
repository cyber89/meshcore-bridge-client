---
name: lora-frame-validator
description: >-
  Herramienta de análisis, cálculo y verificación de tramas binarias de protocolo LoRa/MeshCore.
  Permite validar delimitación SOF/EOF, secuencias de escape (byte stuffing) y calcular
  múltiples algoritmos de CRC (CRC-CCITT, CRC-16-IBM, CRC-32, Fletcher-16, XOR). Usar para
  validar capturas de tramas UART/LoRa reales o depurar serializadores/deserializadores.
---

# LoRa & MeshCore Frame Validator Skill

Esta skill proporciona herramientas para que el **Protocol & Firmware Investigator**, el **Python Bridge Architect** y el **Protocol QA Agent** validen tramas binarias crudas, offsets de campos y coherencia de checksums.

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
