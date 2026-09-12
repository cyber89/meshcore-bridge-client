import os

i18n_path = r'c:\Users\Ruby\Desktop\meshcore-bridge\src\web\static\js\i18n.js'
with open(i18n_path, 'r', encoding='utf-8') as f:
    content = f.read()

app_es = '''
      // App
      'app.light_theme_title':     'Cambiar a modo claro',
      'app.dark_theme_title':      'Cambiar a modo oscuro',
      'app.web_online':            'Web: Online',
      'app.web_connecting':        'Web: Conectando...',
      'app.web_offline':           'Web: Desconectada',
      'app.radio_online':          'Radio: {port}',
      'app.radio_online_fallback': 'Radio: Online',
      'app.radio_offline':         'Radio: Desconectada',
'''

app_en = '''
      // App
      'app.light_theme_title':     'Switch to light mode',
      'app.dark_theme_title':      'Switch to dark mode',
      'app.web_online':            'Web: Online',
      'app.web_connecting':        'Web: Connecting...',
      'app.web_offline':           'Web: Disconnected',
      'app.radio_online':          'Radio: {port}',
      'app.radio_online_fallback': 'Radio: Online',
      'app.radio_offline':         'Radio: Disconnected',
'''

content = content.replace("// Common", app_es + "\n      // Common", 1)
content = content.replace("// Common", app_en + "\n      // Common", 1)

with open(i18n_path, 'w', encoding='utf-8') as f:
    f.write(content)

app_js_path = r'c:\Users\Ruby\Desktop\meshcore-bridge\src\web\static\js\app.js'
with open(app_js_path, 'r', encoding='utf-8') as f:
    app_content = f.read()

replacements = [
    ('"Cambiar a modo claro"', "I18n.t('app.light_theme_title')"),
    ('"Cambiar a modo oscuro"', "I18n.t('app.dark_theme_title')"),
    ('"Web: Online"', "I18n.t('app.web_online')"),
    ('"Web: Conectando?"', "I18n.t('app.web_connecting')"),
    ('"Web: Conectando..."', "I18n.t('app.web_connecting')"),
    ('"Web: Desconectada"', "I18n.t('app.web_offline')"),
    ('`Radio: ${portName || "Online"}`', "portName ? I18n.t('app.radio_online').replace('{port}', portName) : I18n.t('app.radio_online_fallback')"),
    ('"Radio: Desconectada"', "I18n.t('app.radio_offline')"),
]

for old, new in replacements:
    app_content = app_content.replace(old, new)

with open(app_js_path, 'w', encoding='utf-8') as f:
    f.write(app_content)

print("app.js patched")
