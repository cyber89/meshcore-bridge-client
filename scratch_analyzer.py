import ast
import os
import sys

def calculate_complexity(node):
    complexity = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.With, ast.AsyncWith, ast.Try, ast.ExceptHandler, ast.Match, ast.BoolOp)):
            complexity += 1
    return complexity

def analyze_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    try:
        tree = ast.parse(content)
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
        return

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start_line = node.lineno
            end_line = node.end_lineno
            length = end_line - start_line + 1
            cc = calculate_complexity(node)
            
            # Check type hints
            has_return_hint = node.returns is not None
            has_arg_hints = all(arg.annotation is not None for arg in node.args.args if arg.arg not in ('self', 'cls'))
            has_hints = has_return_hint and has_arg_hints
            
            if length > 70 or cc > 15 or not has_hints:
                print(f"{os.path.basename(filepath)} - {node.name} (Lines: {length}, CC: {cc}, Hints: {has_hints})")

def main():
    files_to_check = [
        "src/admin/cli_command_executor.py",
        "src/admin/local_config_executor.py",
        "src/admin/repeater_executor.py",
        "src/admin/traceroute_executor.py",
        "src/admin/__init__.py",
        "src/web/http_server.py",
        "src/web/api_router.py",
        "src/web/security_inspector.py",
        "src/web/map_tile_service.py"
    ]
    
    for c in os.listdir("src/web/controllers"):
        if c.endswith(".py"):
            files_to_check.append(f"src/web/controllers/{c}")
            
    for f in files_to_check:
        full_path = os.path.join(r"c:\Users\Ruby\Desktop\meshcore-bridge", f)
        if os.path.exists(full_path):
            analyze_file(full_path)

if __name__ == "__main__":
    main()
