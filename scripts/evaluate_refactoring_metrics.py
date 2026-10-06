"""Recursive AST inventory with a documented decision score, not a quality certificate.

Score starts at one; if/conditional expression, loops, each exception handler,
each comprehension generator/filter and each additional Boolean operand add one.
With/async-with and definitions of other functions/classes add no decisions.
This convention excludes implicit exception paths and is not exact graph McCabe.
"""

from __future__ import annotations

import ast
from pathlib import Path


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[1]


class DecisionVisitor(ast.NodeVisitor):
    """Visit one function body without descending into other lexical scopes."""

    def __init__(self) -> None:
        self.score = 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        pass

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        pass

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        pass

    def visit_Lambda(self, node: ast.Lambda) -> None:
        pass

    def generic_visit(self, node: ast.AST) -> None:
        if isinstance(node, (ast.If, ast.IfExp, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler)):
            self.score += 1
        elif isinstance(node, ast.BoolOp):
            self.score += len(node.values) - 1
        elif isinstance(node, ast.comprehension):
            self.score += 1 + len(node.ifs)
        super().generic_visit(node)


def calculate_cyclomatic_complexity(node: ast.AST) -> int:
    """Compatibility name for the decision score defined in the module docstring."""
    visitor = DecisionVisitor()
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for statement in node.body:
            visitor.visit(statement)
    else:
        visitor.visit(node)
    return visitor.score


def analyze_file_metrics(file_path: Path) -> list[str]:
    """Return findings; IO/parse errors propagate so callers cannot report clean."""
    tree = ast.parse(file_path.read_text(encoding="utf-8-sig"), filename=str(file_path))
    issues = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        score = calculate_cyclomatic_complexity(node)
        if score > 15:
            issues.append(f"[DECISIONES] {file_path}:{node.lineno} '{node.name}' score={score} (señal: 15)")
        args_count = len(node.args.posonlyargs) + len(node.args.args) + len(node.args.kwonlyargs)
        if args_count > 6:
            issues.append(f"[PARAMETROS] {file_path}:{node.lineno} '{node.name}' argumentos={args_count} (señal: 6)")
    return issues


def main(root: Path | None = None) -> int:
    source = (root or get_project_root()) / "src"
    analyzed = 0
    excluded = 0
    errors = 0
    findings = []
    for file_path in sorted(source.rglob("*.py")):
        if "__pycache__" in file_path.parts:
            excluded += 1
            print(f"[EXCLUIDO] {file_path}")
            continue
        try:
            findings.extend(analyze_file_metrics(file_path))
        except (OSError, SyntaxError, UnicodeError) as exc:
            errors += 1
            print(f"[ERROR] {file_path}: {exc}")
        else:
            analyzed += 1
            print(f"[ANALIZADO] {file_path}")
    for finding in findings:
        print(f"[WARN] {finding}")
    print(f"[INVENTARIO] analizados={analyzed}, excluidos={excluded}, errores={errors}, hallazgos={len(findings)}")
    print("Score AST orientativo de decisiones y parámetros; no acredita ausencia de errores, SOLID ni rendimiento.")
    return 1 if errors or not analyzed else 0


if __name__ == "__main__":
    raise SystemExit(main())
