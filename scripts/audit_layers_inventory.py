"""Read-only structural inventory for the layered audit; never imports production."""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def scoped_nodes(node: ast.AST) -> list[ast.AST]:
    """Avoid counting a nested function's branches in its enclosing function."""
    result = [node]
    for child in ast.iter_child_nodes(node):
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            result.extend(scoped_nodes(child))
    return result


def complexity(node: ast.AST) -> int:
    """Decision-count proxy; not Radon/McCabe certification or a runtime metric."""
    total = 1
    for child in scoped_nodes(node):
        if isinstance(child, (ast.If, ast.IfExp, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler)):
            total += 1
        elif isinstance(child, ast.BoolOp):
            total += len(child.values) - 1
        elif isinstance(child, ast.comprehension):
            total += 1 + len(child.ifs)
        elif isinstance(child, ast.Match):
            total += sum(not isinstance(case.pattern, ast.MatchAs) or case.pattern.pattern is not None or case.guard is not None for case in child.cases)
    return total


def inventory() -> dict[str, Any]:
    paths = sorted((ROOT / "src").rglob("*.py"))
    paths += [ROOT / name for name in ("config.py", "meshcore_bridge.py", "run_interactive_demo.py")]
    names: Counter[str] = Counter()
    strings: Counter[str] = Counter()
    modules: list[dict[str, Any]] = []
    functions: list[dict[str, Any]] = []
    classes: list[dict[str, Any]] = []
    parse_errors: list[dict[str, str]] = []

    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        source = path.read_text(encoding="utf-8-sig")
        try:
            tree = ast.parse(source, filename=relative, feature_version=(3, 10))
        except SyntaxError as error:
            parse_errors.append({"file": relative, "error": str(error)})
            continue
        imports = []
        for child in ast.walk(tree):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                names[child.id] += 1
            elif isinstance(child, ast.Attribute) and isinstance(child.ctx, ast.Load):
                names[child.attr] += 1
            elif isinstance(child, ast.Constant) and isinstance(child.value, str):
                strings.update(re.findall(r"\b[A-Za-z_]\w*\b", child.value))
            elif isinstance(child, ast.Import):
                imports.extend(alias.name for alias in child.names)
            elif isinstance(child, ast.ImportFrom):
                imports.append("." * child.level + (child.module or ""))
        modules.append({"file": relative, "lines": len(source.splitlines()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "imports": sorted(set(imports))})

        def visit(body: list[ast.AST], prefix: str, file_name: str) -> None:
            for child in body:
                if isinstance(child, ast.ClassDef):
                    qualified = prefix + child.name
                    methods = [item.name for item in child.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))]
                    classes.append({"file": file_name, "name": qualified, "line": child.lineno, "end_line": child.end_lineno, "span_lines": (child.end_lineno or child.lineno) - child.lineno + 1, "methods": methods, "bases": [ast.unparse(base) for base in child.bases]})
                    visit(list(child.body), qualified + ".", file_name)
                elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    qualified = prefix + child.name
                    decorators = [ast.unparse(item) for item in child.decorator_list]
                    args = child.args
                    positional = [item.arg for item in (*args.posonlyargs, *args.args) if item.arg not in ("self", "cls")]
                    nodes = scoped_nodes(child)
                    functions.append({"file": file_name, "name": qualified, "symbol": child.name, "line": child.lineno, "end_line": child.end_lineno, "span_lines": (child.end_lineno or child.lineno) - child.lineno + 1, "decision_proxy": complexity(child), "statement_count": sum(isinstance(item, ast.stmt) for item in nodes) - 1, "parameters": positional + [item.arg for item in args.kwonlyargs], "variadic": bool(args.vararg or args.kwarg), "async": isinstance(child, ast.AsyncFunctionDef), "decorators": decorators, "kind": "method_or_nested" if prefix else "function"})
                    visit(list(child.body), qualified + ".", file_name)
                else:
                    visit(list(ast.iter_child_nodes(child)), prefix, file_name)

        visit(list(tree.body), "", relative)

    for function in functions:
        function["production_name_loads"] = names[function["symbol"]]
        function["production_string_mentions"] = strings[function["symbol"]]
        function["no_observed_name_usage"] = not names[function["symbol"]] and not strings[function["symbol"]]
    assets = []
    for path in sorted((ROOT / "src/web/static").rglob("*")):
        if path.suffix in (".js", ".css", ".html"):
            assets.append({"file": path.relative_to(ROOT).as_posix(), "lines": len(path.read_text(encoding="utf-8-sig").splitlines()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return {"methodology": {"scope": "recursive src Python plus three root entry/config files; all static JS/CSS/HTML", "python_syntax_target": "3.10", "complexity": "AST decision-count proxy excluding nested scopes and with statements; not formal McCabe", "unused": "untyped name/string reference heuristic in production only; zero mentions is a candidate, never proof of unused code", "imports_executed": False, "limits": "No runtime timing/optimality claim; dynamic callbacks, reflection, public APIs and inheritance require manual inspection."}, "summary": {"python_files": len(modules), "classes": len(classes), "functions_methods_nested": len(functions), "static_assets": len(assets), "parse_errors": len(parse_errors)}, "modules": modules, "classes": classes, "functions": functions, "assets": assets, "parse_errors": parse_errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args()
    report = inventory()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.csv:
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("file", "qualified_name", "line", "span_lines", "decision_proxy", "statements", "parameters", "async", "production_name_loads", "no_observed_name_usage"))
        for item in report["functions"]:
            writer.writerow((item["file"], item["name"], item["line"], item["span_lines"], item["decision_proxy"], item["statement_count"], len(item["parameters"]), item["async"], item["production_name_loads"], item["no_observed_name_usage"]))
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", encoding="utf-8", newline="") as output:
            output.write(stream.getvalue())
    print(json.dumps(report["summary"]))
    return 1 if report["parse_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
