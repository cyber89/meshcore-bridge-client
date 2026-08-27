import re
import sys

def main():
    with open('src/web/static/js/app.js', 'r', encoding='utf-8') as f:
        content = f.read()

    # Simple text assignments
    content = content.replace('.innerHTML = "Ejecutando comprobaciones de diagnóstico...";', '.textContent = "Ejecutando comprobaciones de diagnóstico...";')
    content = content.replace('.innerHTML = "";', '.textContent = "";')
    content = content.replace('.innerHTML = "Ejecutando auto-diagnóstico de subsistemas...";', '.textContent = "Ejecutando auto-diagnóstico de subsistemas...";')
    
    # Use textContent where pre formatting was used (need to preserve formatting if pre, but textContent inside pre works, wait... the div is quickDiagBody. If I set textContent on a div, newlines are ignored unless it has white-space: pre. So better keep innerHTML = <pre>...
    
    # Ensure all template literals are using escapeHtml
    content = re.sub(r'\$\{([^}]+)\}', lambda m: escape_if_needed(m.group(1)), content)
    
    with open('src/web/static/js/app.js', 'w', encoding='utf-8') as f:
        f.write(content)

def escape_if_needed(var_name):
    var_name = var_name.strip()
    # List of variables to escape
    to_escape = ['name', 'alias', 'n.name', 'n.alias', 'c.name', 'c.alias', 'ch.name', 'sender', 'msg.text', 'cleanText', 'senderName', 'log.message', 'log.source']
    if var_name in to_escape and not var_name.startswith('this.escapeHtml'):
        return f'${{this.escapeHtml({var_name})}}'
    return f'${{{var_name}}}'

if __name__ == "__main__":
    main()
