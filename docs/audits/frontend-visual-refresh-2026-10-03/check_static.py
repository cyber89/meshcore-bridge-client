"""Revisión estática de CSS/tokens; no importa la app ni abre un navegador."""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
css_dir = ROOT / "src/web/static/css"
css = (css_dir / "tokens.css").read_text(encoding="utf-8")


def declarations(selector):
    block = re.search(re.escape(selector) + r"\s*\{([^}]+)\}", css).group(1)
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block))


def luminance(color):
    color = color.strip().lstrip("#")
    rgb = [int(color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    rgb = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in rgb]
    return sum(x * weight for x, weight in zip(rgb, (0.2126, 0.7152, 0.0722), strict=True))


def contrast(first, second):
    a, b = sorted((luminance(first), luminance(second)))
    return (b + 0.05) / (a + 0.05)


dark = declarations(":root")
light = {**dark, **declarations("body.light-theme")}
backgrounds = ["--bg-canvas", "--bg-surface", "--bg-surface-elevated", "--bg-surface-hover"]
foregrounds = ["--text-bright", "--text-main", "--text-muted", "--text-dim",
               "--accent-primary", "--accent-secondary", "--accent-success",
               "--accent-warning", "--accent-danger", "--accent-purple"]
rows = []
for theme, tokens in (("dark", dark), ("light", light)):
    for fg in foregrounds:
        for bg in backgrounds:
            ratio = contrast(tokens[fg], tokens[bg])
            rows.append({"theme": theme, "foreground": fg, "background": bg,
                         "ratio": round(ratio, 3), "passes_4_5": ratio >= 4.5})

rows.extend({"theme": "light", "foreground": "#ffffff", "background": token,
             "ratio": round(contrast("#ffffff", light[token]), 3),
             "passes_4_5": contrast("#ffffff", light[token]) >= 4.5}
            for token in ("--accent-primary", "--accent-primary-hover"))
balance = {}
for name in ("tokens.css", "components.css", "admin.css", "chat.css"):
    source = (css_dir / name).read_text(encoding="utf-8")
    stripped = re.sub(r"/\*.*?\*/|\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*'", "", source, flags=re.S)
    depth = 0
    minimum = 0
    for char in stripped:
        depth += (char == "{") - (char == "}")
        minimum = min(minimum, depth)
    balance[name] = {"balanced_braces": depth == 0 and minimum == 0}

result = {"base": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
          "scope": "Tokens hex declarados y equilibrio léxico de llaves; CSS de trabajo sobre la base. No rendering, CSSOM, interoperabilidad ni certificación WCAG completa.",
          "contrast_pairs": rows, "css": balance,
          "passes": all(row["passes_4_5"] for row in rows) and all(row["balanced_braces"] for row in balance.values())}
(HERE / "static-results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"pairs": len(rows), "failures": [r for r in rows if not r["passes_4_5"]],
                  "css": balance, "passes": result["passes"]}, ensure_ascii=False))
raise SystemExit(0 if result["passes"] else 1)
