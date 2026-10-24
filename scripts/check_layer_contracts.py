"""Statically enforce the forbidden import contracts declared in pyproject.toml.

This reads Python ASTs without importing the application or loading station state.
It follows project-local imports transitively; dynamic imports are outside its scope.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def import_graph(root: Path) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for path in (root / "src").rglob("*.py"):
        parts = list(path.relative_to(root).with_suffix("").parts)
        is_package = parts[-1] == "__init__"
        if is_package:
            parts.pop()
        module = ".".join(parts)
        imports: set[str] = set()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    package = parts if is_package else parts[:-1]
                    base = ".".join(package[:len(package) - node.level + 1] + ([base] if base else []))
                imports.add(base)
                imports.update(f"{base}.{alias.name}" for alias in node.names)
        graph[module] = imports
    return {module: {dependency for dependency in imports if dependency in graph}
            for module, imports in graph.items()}


def main() -> int:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    contracts = config["tool"]["importlinter"]["contracts"]
    graph = import_graph(ROOT)
    errors: list[str] = []
    for contract in contracts:
        if contract["type"] != "forbidden":
            errors.append(f"Unsupported contract type: {contract['type']}")
            continue
        for source in contract["source_modules"]:
            if source not in graph:
                errors.append(f"Missing contract source: {source}")
                continue
            # A package source denotes its whole subtree, including modules
            # that its __init__ does not export or import.
            roots = [module for module in graph if module == source or module.startswith(source + ".")]
            pending = [(module, [module]) for module in roots]
            seen: set[str] = set()
            while pending:
                module, trail = pending.pop()
                if module in seen:
                    continue
                seen.add(module)
                for dependency in graph.get(module, set()):
                    chain = [*trail, dependency]
                    if any(dependency == forbidden or dependency.startswith(forbidden + ".")
                           for forbidden in contract["forbidden_modules"]):
                        errors.append(f"{contract['name']}: {' -> '.join(chain)}")
                    else:
                        pending.append((dependency, chain))
    for error in errors:
        print(error)
    print(f"Static import contracts: {len(contracts)} checked, {len(errors)} violations")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
