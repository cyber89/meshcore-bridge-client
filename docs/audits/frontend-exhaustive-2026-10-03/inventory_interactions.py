"""Read-only lexical inventory. Signals require semantic review before removal."""
from __future__ import annotations

import collections
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STATIC = ROOT / "src/web/static"
html = (STATIC / "index.html").read_text(encoding="utf-8")
ids = re.findall(r'\bid="([^"]+)"', html)
id_set = set(ids)
app = (STATIC / "js/app.js").read_text(encoding="utf-8")
context = app.split("this.context = {", 1)[1].split("// Instanciación", 1)[0]
sources = sorted((STATIC / "js").rglob("*.js"))
missing_ids: dict[str, list[str]] = {}
unused_imports: dict[str, list[str]] = {}
undefined_context: dict[str, list[str]] = {}
syntax: dict[str, int] = {}
for source in sources:
    name = source.relative_to(STATIC).as_posix()
    text = source.read_text(encoding="utf-8")
    missing = sorted(set(re.findall(r'getElementById\(["\']([^"\']+)["\']\)', text)) - id_set)
    if missing:
        missing_ids[name] = missing
    for imports in re.findall(r"import\s*{([^}]+)}", text):
        for entry in imports.split(","):
            symbol = entry.strip().split(" as ")[-1]
            if len(re.findall(r"\b" + re.escape(symbol) + r"\b", text)) == 1:
                unused_imports.setdefault(name, []).append(symbol)
    for method in re.findall(r"this\.ctx\??\.([A-Za-z_]\w*)\??\.?(?:\(|\?\.)", text):
        if not re.search(r"\b" + re.escape(method) + r"\s*[:(]", context):
            undefined_context.setdefault(method, []).append(name)
    syntax[name] = subprocess.run(["node", "--check", str(source)], capture_output=True, check=False).returncode
print(json.dumps({
    "description": "Lexical inventory; optional/dynamic DOM IDs are not proven errors.",
    "files": len(sources), "html_ids": len(ids),
    "duplicate_ids": [name for name, count in collections.Counter(ids).items() if count > 1],
    "lookup_ids_absent_from_static_html": missing_ids,
    "unused_named_imports": unused_imports,
    "unprovided_context_calls": undefined_context,
    "node_syntax_exit_codes": syntax,
}, ensure_ascii=False, indent=2))
