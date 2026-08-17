#!/usr/bin/env python3
"""
MeshCore Source Inspector CLI & AST Extractor.
Analiza y extrae definiciones de C/C++ (structs, enums, defines, crc) y SDKs de Python
ubicados en /reference/ sin saturar la ventana de contexto.
"""

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Mapeo estándar de tamaños de tipos de C/C++ en arquitecturas embebidas de 32 bits (ESP32/ARM Cortex-M/RP2040)
C_TYPE_SIZES: Dict[str, int] = {
    "uint8_t": 1, "int8_t": 1, "char": 1, "unsigned char": 1, "signed char": 1, "bool": 1,
    "uint16_t": 2, "int16_t": 2, "short": 2, "unsigned short": 2,
    "uint32_t": 4, "int32_t": 4, "int": 4, "unsigned int": 4, "float": 4, "uint32": 4,
    "uint64_t": 8, "int64_t": 8, "double": 8,
}

@dataclass
class StructField:
    name: str
    c_type: str
    size_bytes: int
    offset_bytes: int
    is_array: bool = False
    array_len: int = 1

@dataclass
class StructDefinition:
    name: str
    file_path: str
    line_number: int
    is_packed: bool
    total_size_bytes: int
    fields: List[StructField] = field(default_factory=list)

@dataclass
class EnumValue:
    name: str
    value: Optional[str] = None

@dataclass
class EnumDefinition:
    name: str
    file_path: str
    line_number: int
    values: List[EnumValue] = field(default_factory=list)

@dataclass
class DefineConstant:
    name: str
    value: str
    file_path: str
    line_number: int

@dataclass
class InspectionResult:
    defines: List[DefineConstant] = field(default_factory=list)
    enums: List[EnumDefinition] = field(default_factory=list)
    structs: List[StructDefinition] = field(default_factory=list)
    crc_functions: List[Dict[str, Any]] = field(default_factory=list)
    python_classes: List[Dict[str, Any]] = field(default_factory=list)

class CSourceInspector:
    def __init__(self, base_paths: List[Path]):
        self.base_paths = base_paths
        self.result = InspectionResult()

    def scan_all(self, filter_symbol: Optional[str] = None) -> InspectionResult:
        for base_path in self.base_paths:
            if not base_path.exists():
                continue
            if base_path.is_file():
                self._inspect_file(base_path)
            else:
                for root, _, files in os.walk(base_path):
                    for file in sorted(files):
                        file_path = Path(root) / file
                        if file_path.suffix in (".h", ".hpp", ".c", ".cpp", ".ino"):
                            self._inspect_c_file(file_path)
                        elif file_path.suffix == ".py":
                            self._inspect_py_file(file_path)

        if filter_symbol:
            pattern = re.compile(filter_symbol, re.IGNORECASE)
            self.result.defines = [d for d in self.result.defines if pattern.search(d.name) or pattern.search(d.value)]
            self.result.enums = [e for e in self.result.enums if pattern.search(e.name) or any(pattern.search(v.name) for v in e.values)]
            self.result.structs = [s for s in self.result.structs if pattern.search(s.name) or any(pattern.search(f.name) for f in s.fields)]
            self.result.python_classes = [c for c in self.result.python_classes if pattern.search(c["name"])]

        return self.result

    def _inspect_c_file(self, file_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return

        rel_path = str(file_path)
        lines = content.splitlines()

        # 1. Extraer #define relevantes para protocolo, framing, buffers, opcodes
        define_regex = re.compile(r"^\s*#define\s+([A-Za-z0-9_]+)\s+([^\/\n]+)", re.MULTILINE)
        for match in define_regex.finditer(content):
            name = match.group(1).strip()
            val = match.group(2).strip()
            # Filtrar guardas de inclusión tipo _HEADER_H
            if name.endswith("_H") or name.endswith("_H_") or name.startswith("__"):
                continue
            # Priorizar constantes de protocolo
            if any(k in name.upper() for k in ("SOF", "EOF", "ESC", "FRAME", "CRC", "OPCODE", "PKT", "CMD", "TYPE", "LEN", "MAX", "HEADER", "PORT", "BAUD", "LORA", "MESH", "PAYLOAD")):
                line_no = content[:match.start()].count("\n") + 1
                self.result.defines.append(DefineConstant(name=name, value=val, file_path=rel_path, line_number=line_no))

        # 2. Extraer Enums
        enum_regex = re.compile(r"enum(?:\s+class)?\s+([A-Za-z0-9_]+)?\s*(?::\s*[A-Za-z0-9_]+)?\s*\{([^}]+)\}\s*([A-Za-z0-9_]+)?;", re.MULTILINE | re.DOTALL)
        for match in enum_regex.finditer(content):
            enum_name = match.group(1) or match.group(3) or "AnonymousEnum"
            body = match.group(2)
            line_no = content[:match.start()].count("\n") + 1
            
            enum_def = EnumDefinition(name=enum_name, file_path=rel_path, line_number=line_no)
            for item in body.split(","):
                item = item.strip()
                if not item or item.startswith("//") or item.startswith("/*"):
                    continue
                # Limpiar comentarios en línea
                item = re.sub(r"/\*.*?\*/", "", item).strip()
                item = re.sub(r"//.*", "", item).strip()
                if not item:
                    continue
                if "=" in item:
                    k, v = item.split("=", 1)
                    enum_def.values.append(EnumValue(name=k.strip(), value=v.strip()))
                else:
                    enum_def.values.append(EnumValue(name=item.strip()))
            
            if enum_def.values:
                self.result.enums.append(enum_def)

        # 3. Extraer Structs
        struct_regex = re.compile(r"(?:typedef\s+)?struct(?:\s+__attribute__\s*\(\s*\(\s*packed\s*\)\s*\))?\s*([A-Za-z0-9_]+)?\s*\{([^}]+)\}\s*(?:__attribute__\s*\(\s*\(\s*packed\s*\)\s*\))?\s*([A-Za-z0-9_]+)?;", re.MULTILINE | re.DOTALL)
        for match in struct_regex.finditer(content):
            struct_name = match.group(1) or match.group(3) or "AnonymousStruct"
            body = match.group(2)
            line_no = content[:match.start()].count("\n") + 1
            full_match_text = match.group(0)
            is_packed = "packed" in full_match_text or "#pragma pack" in content[:match.start()]

            struct_def = StructDefinition(
                name=struct_name,
                file_path=rel_path,
                line_number=line_no,
                is_packed=is_packed,
                total_size_bytes=0,
            )

            current_offset = 0
            field_lines = body.split(";")
            for fline in field_lines:
                fline = fline.strip()
                fline = re.sub(r"/\*.*?\*/", "", fline).strip()
                fline = re.sub(r"//.*", "", fline).strip()
                if not fline:
                    continue

                # Parsear tipo y nombre (ej: uint8_t dest_id, char name[16], uint16_t seq)
                field_match = re.match(r"^([\w\s\*]+?)\s+([A-Za-z0-9_]+)(?:\[([A-Za-z0-9_\s\+\-\*]+)\])?$", fline)
                if field_match:
                    c_type = field_match.group(1).strip()
                    fname = field_match.group(2).strip()
                    array_len_str = field_match.group(3)

                    is_array = array_len_str is not None
                    array_len = 1
                    if is_array and array_len_str:
                        try:
                            array_len = int(eval(array_len_str, {}, {}))  # safe for simple arithmetic
                        except Exception:
                            array_len = 1

                    unit_size = C_TYPE_SIZES.get(c_type, 4)
                    field_size = unit_size * array_len
                    struct_def.fields.append(
                        StructField(
                            name=fname,
                            c_type=c_type,
                            size_bytes=field_size,
                            offset_bytes=current_offset,
                            is_array=is_array,
                            array_len=array_len,
                        )
                    )
                    current_offset += field_size

            struct_def.total_size_bytes = current_offset
            if struct_def.fields:
                self.result.structs.append(struct_def)

        # 4. Extraer funciones de CRC / Checksum
        crc_regex = re.compile(r"((?:uint\d+_t|unsigned\s+int|int|short)\s+(?:crc|checksum|calc_crc|crc16|crc32|crc8)[A-Za-z0-9_]*\s*\([^)]*\)\s*\{[^}]+\})", re.MULTILINE | re.DOTALL | re.IGNORECASE)
        for match in crc_regex.finditer(content):
            fn_code = match.group(1).strip()
            line_no = content[:match.start()].count("\n") + 1
            # Resumir función
            fn_first_line = fn_code.splitlines()[0]
            self.result.crc_functions.append({
                "signature": fn_first_line,
                "file_path": rel_path,
                "line_number": line_no,
                "code_snippet": fn_code[:300] + ("..." if len(fn_code) > 300 else ""),
            })

    def _inspect_py_file(self, file_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return

        rel_path = str(file_path)
        class_regex = re.compile(r"^class\s+([A-Za-z0-9_]+)(?:\(([^)]+)\))?:", re.MULTILINE)
        for match in class_regex.finditer(content):
            cls_name = match.group(1)
            bases = match.group(2) or ""
            line_no = content[:match.start()].count("\n") + 1
            if any(k in cls_name.lower() for k in ("packet", "frame", "event", "message", "command", "mesh", "node", "telemetry", "type", "client")):
                self.result.python_classes.append({
                    "name": cls_name,
                    "bases": bases.strip(),
                    "file_path": rel_path,
                    "line_number": line_no,
                })


def format_markdown(res: InspectionResult) -> str:
    out = ["# MeshCore AST & Protocol Inspection Summary\n"]
    
    out.append(f"## 1. Framing & Protocol `#define` Constants ({len(res.defines)} encontradas)\n")
    if res.defines:
        out.append("| Constante | Valor | Archivo | Línea |")
        out.append("| :--- | :--- | :--- | :--- |")
        for d in res.defines[:40]:
            p = Path(d.file_path).name
            out.append(f"| `{d.name}` | `{d.value}` | `{p}` | {d.line_number} |")
    else:
        out.append("_No se encontraron constantes relevantes con el filtro actual._\n")

    out.append(f"\n## 2. Enums de Protocolo & OpCodes ({len(res.enums)} encontrados)\n")
    for e in res.enums[:25]:
        p = Path(e.file_path).name
        out.append(f"### Enum `{e.name}` (`{p}:{e.line_number}`)")
        out.append("| Identificador | Valor Asignado |")
        out.append("| :--- | :--- |")
        for v in e.values:
            val_str = f"`{v.value}`" if v.value else "_(auto)_"
            out.append(f"| `{v.name}` | {val_str} |")
        out.append("")

    out.append(f"\n## 3. Memory Layouts & Structs ({len(res.structs)} encontrados)\n")
    for s in res.structs[:25]:
        p = Path(s.file_path).name
        packed_tag = " [__packed__]" if s.is_packed else ""
        out.append(f"### Struct `{s.name}`{packed_tag} — Total: {s.total_size_bytes} Bytes (`{p}:{s.line_number}`)")
        out.append("| Offset (B) | Campo | Tipo C/C++ | Tamaño (B) |")
        out.append("| :--- | :--- | :--- | :--- |")
        for f in s.fields:
            arr = f"[{f.array_len}]" if f.is_array else ""
            out.append(f"| `+{f.offset_bytes:02d}` | `{f.name}{arr}` | `{f.c_type}` | {f.size_bytes} |")
        out.append("")

    if res.crc_functions:
        out.append(f"\n## 4. Algoritmos de Checksum & CRC ({len(res.crc_functions)} encontrados)\n")
        for crc in res.crc_functions:
            p = Path(crc["file_path"]).name
            out.append(f"#### `{crc['signature']}` (`{p}:{crc['line_number']}`)")
            out.append("```c")
            out.append(crc["code_snippet"])
            out.append("```\n")

    if res.python_classes:
        out.append(f"\n## 5. Clases y Modelos en SDKs Python ({len(res.python_classes)} encontrados)\n")
        out.append("| Clase | Clase Base | Archivo | Línea |")
        out.append("| :--- | :--- | :--- | :--- |")
        for pc in res.python_classes[:30]:
            p = Path(pc["file_path"]).name
            out.append(f"| `{pc['name']}` | `{pc['bases']}` | `{p}` | {pc['line_number']} |")

    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="MeshCore Source AST & Protocol Inspector")
    parser.add_argument("--path", action="append", default=[], help="Rutas a inspeccionar (ej: reference/meshcore, reference/meshcore_py)")
    parser.add_argument("--symbol", type=str, default=None, help="Filtrar por nombre de símbolo, struct o enum")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Formato de salida")
    parser.add_argument("--out", type=str, default=None, help="Guardar reporte en archivo destino")

    args = parser.parse_args()

    default_paths = [
        Path("reference/meshcore/include"),
        Path("reference/meshcore/src"),
        Path("reference/meshcore/boards"),
        Path("reference/meshcore_py/src"),
        Path("reference/meshcore_cli/src"),
    ]

    target_paths = [Path(p) for p in args.path] if args.path else [p for p in default_paths if p.exists()]
    if not target_paths:
        target_paths = [Path("reference")]

    inspector = CSourceInspector(base_paths=target_paths)
    res = inspector.scan_all(filter_symbol=args.symbol)

    if args.format == "json":
        output_str = json.dumps({
            "defines": [asdict(d) for d in res.defines],
            "enums": [asdict(e) for e in res.enums],
            "structs": [asdict(s) for s in res.structs],
            "crc_functions": res.crc_functions,
            "python_classes": res.python_classes,
        }, indent=2)
    else:
        output_str = format_markdown(res)

    if args.out:
        Path(args.out).write_text(output_str, encoding="utf-8")
        print(f"[OK] Reporte generado exitosamente en: {args.out}")
    else:
        print(output_str)

if __name__ == "__main__":
    main()
