#!/usr/bin/env node
'use strict';

// Read-only catalogue audit. It never starts a bridge, browser, or radio driver.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Only showQrModal consumes an options.key as a translation key. Chart series
// and custom-variable payloads also use key, with a different meaning.
function qrTitleReferences(content) {
  return [...content.matchAll(/\bshowQrModal\s*\([^;]*?\bkey\s*:\s*(['"])([^'"]+)\1/g)].map(match => match[2]);
}

if (process.argv.includes('--scan-qr-keys')) {
  process.stdout.write(JSON.stringify(qrTitleReferences(fs.readFileSync(0, 'utf8'))) + '\n');
  return;
}

// Lexical inspection of UI arguments: comments, regexes and translated keys are
// masked, while template interpolation expressions remain inspectable.
function scanUiLiterals(content, dictionary = {}, filename = '<stdin>') {
  const masked = content.split('');
  const literals = [];
  const hide = (start, end) => {
    for (let i = start; i < end; i++) if (masked[i] !== '\n') masked[i] = ' ';
  };
  const decode = value => value.replace(/\\u([0-9a-fA-F]{4})|\\x([0-9a-fA-F]{2})|\\([nrt'"`\\])/g,
    (_, unicode, hex, escaped) => unicode || hex ? String.fromCharCode(parseInt(unicode || hex, 16)) : ({ n: '\n', r: '\r', t: '\t' }[escaped] || escaped));
  const add = (start, end) => {
    if (end > start) literals.push({ start, end, value: decode(content.slice(start, end)) });
    hide(start, end);
  };
  function scan(start, interpolation = false) {
    let depth = 0;
    let i = start;
    while (i < content.length) {
      const char = content[i];
      if (interpolation && char === '}' && depth === 0) return i + 1;
      if (char === '/' && content[i + 1] === '/') {
        const end = content.indexOf('\n', i);
        hide(i, end < 0 ? content.length : end);
        i = end < 0 ? content.length : end;
      } else if (char === '/' && content[i + 1] === '*') {
        const end = content.indexOf('*/', i + 2);
        const next = end < 0 ? content.length : end + 2;
        hide(i, next);
        i = next;
      } else if (char === '"' || char === "'") {
        const quote = char;
        const begin = i++;
        const textStart = i;
        while (i < content.length && content[i] !== quote) i += content[i] === '\\' ? 2 : 1;
        add(textStart, i);
        hide(begin, Math.min(i + 1, content.length));
        i++;
      } else if (char === '`') {
        hide(i, i + 1);
        let segment = ++i;
        while (i < content.length) {
          if (content[i] === '\\') i += 2;
          else if (content[i] === '`') {
            add(segment, i);
            hide(i, i + 1);
            i++;
            break;
          } else if (content[i] === '$' && content[i + 1] === '{') {
            add(segment, i);
            hide(i, i + 2);
            i = scan(i + 2, true);
            hide(i - 1, i);
            segment = i;
          } else i++;
        }
      } else if (char === '/' && /(?:[=(:,\[!&|?;{}]|\breturn)\s*$/.test(content.slice(0, i))) {
        const begin = i++;
        let inClass = false;
        while (i < content.length) {
          if (content[i] === '\\') i += 2;
          else if (content[i] === '/' && !inClass) { i++; break; }
          else { if (content[i] === '[') inClass = true; if (content[i] === ']') inClass = false; i++; }
        }
        hide(begin, i);
      } else {
        if (char === '{') depth++;
        if (char === '}') depth--;
        i++;
      }
    }
    return i;
  }
  scan(0);
  const code = masked.join('');
  function argumentEnd(start, assignment = false) {
    const stack = [];
    for (let i = start; i < code.length; i++) {
      const char = code[i];
      if (!stack.length && (char === ';' || (!assignment && (char === ',' || char === ')')))) return i;
      if ('([{'.includes(char)) stack.push(char);
      else if (')]}'.includes(char)) {
        if (!stack.length) return i;
        stack.pop();
      }
    }
    return code.length;
  }
  const translatedKeys = [];
  for (const match of code.matchAll(/\b(?:I18n|window\.I18n)\.(t|setText)\s*\(/g)) {
    let start = match.index + match[0].length;
    if (match[1] === 'setText') start = argumentEnd(start) + 1;
    const end = argumentEnd(start);
    translatedKeys.push({ start, end, keys: literals.filter(literal => literal.start >= start && literal.end <= end).map(literal => literal.value) });
  }
  const candidates = [];
  const exclusions = [];
  const seen = new Set();
  const spanish = /[áéíóúñ¿¡]|\b(?:canal|sin|espera|borrar|sondeando|transmitiendo|guardando|guardar|obteniendo|descargando|selecciona|primero|objetivo|fallo|desconocido|agregar|eliminar|nombre|contacto|repetidor|identidad|red|nodo|hace|activo|ayer)\b/i;
  const sinks = /\b(?:showToast|_notify|alert|confirm|append(?:Local)?TerminalLine|Error)\s*\(|\.(?:textContent|innerHTML|title|placeholder)\s*=(?!=)/g;
  for (const match of code.matchAll(sinks)) {
    const start = match.index + match[0].length;
    const end = argumentEnd(start, match[0].includes('='));
    const keys = translatedKeys.filter(key => key.start >= start && key.end <= end).flatMap(key => key.keys);
    for (const literal of literals.filter(item => item.start >= start && item.end <= end)) {
      if (!spanish.test(literal.value) || seen.has(literal.start)) continue;
      seen.add(literal.start);
      if (translatedKeys.some(key => literal.start >= key.start && literal.end <= key.end)) continue;
      const line = content.slice(0, literal.start).split('\n').length;
      const item = { file: filename, line, literal: literal.value, sink: match[0].trim() };
      // Existing Spanish fallbacks are reachable only when translation support
      // is absent; accept solely an exact catalogue value of a key in this sink.
      const fallbackKey = keys.find(key => dictionary[key] === literal.value.trim());
      const before = content.slice(start, literal.start);
      if (fallbackKey && /(?:\|\||:)\s*['"`]?\s*$/.test(before)) {
        exclusions.push({ ...item, reason: 'Exact Spanish catalogue fallback', key: fallbackKey });
      } else candidates.push(item);
    }
  }
  return { untranslatedCandidates: candidates, reviewedExclusions: exclusions };
}

if (process.argv.includes('--self-test')) {
  const cases = [
    ['mixed_literal', '_notify("Error guardando radio: " + I18n.t("settings.unknown"));', 1],
    ['catch_template', 'try {} catch (e) { showToast(`Error de red al guardar canal: ${e.message}`); }', 1],
    ['terminal', 'appendTerminalLine("Selecciona primero un repetidor objetivo.");', 1],
    ['throw', 'throw new Error("Fallo al guardar identidad");', 1],
    ['translated', 'showToast(I18n.t("settings.unknown"));', 0],
    ['backend_parameter', 'showToast(I18n.t("settings.network_error", { p0: err.message }));', 0],
    ['technical', 'throw new Error(`HTTP ${response.status}`);', 0],
    ['comments_regex', '// alert("Selecciona primero");\nconst expression = /alert("Selecciona primero")/;', 0],
    ['multiline', 'alert(\n  "Error descargando archivo de logs"\n);', 1],
    ['template_interpolation', 'element.innerHTML = `<span>${I18n.t("settings.unknown")}</span> Selecciona primero`;', 1],
    ['precise_fallback', 'showToast(I18n.t("settings.unknown") || "Desconocido");', 0],
  ];
  const results = cases.map(([name, input, expected]) => {
    const report = scanUiLiterals(input, { 'settings.unknown': 'Desconocido' });
    return { name, expected, actual: report.untranslatedCandidates.length, passed: report.untranslatedCandidates.length === expected };
  });
  process.stdout.write(JSON.stringify({ selfTest: results, passed: results.every(result => result.passed) }, null, 2) + '\n');
  process.exitCode = results.every(result => result.passed) ? 0 : 1;
  return;
}

const root = path.resolve(__dirname, '..');
const jsRoot = path.join(root, 'src/web/static/js');
const source = fs.readFileSync(path.join(jsRoot, 'i18n.js'), 'utf8');
const context = {
  window: {}, navigator: { language: 'es' },
  localStorage: { getItem: () => null },
  document: { readyState: 'loading', addEventListener() {} },
};
vm.runInNewContext(source.replace('  // ── Public API',
  '  window.__audit = { DICT, DOM_MAP };\n  // ── Public API'), context);
const { DICT, DOM_MAP } = context.window.__audit;
if (process.argv.includes('--scan-source')) {
  const report = scanUiLiterals(fs.readFileSync(0, 'utf8'), DICT.es);
  process.stdout.write(JSON.stringify(report, null, 2) + '\n');
  process.exitCode = report.untranslatedCandidates.length ? 1 : 0;
  return;
}
const findings = [];
const esStart = source.indexOf('    es: {');
const enStart = source.indexOf('    en: {');
const catalogEnd = source.indexOf('  const DOM_MAP');
for (const [lang, section] of [['es', source.slice(esStart, enStart)], ['en', source.slice(enStart, catalogEnd)]]) {
  const seen = new Set();
  for (const match of section.matchAll(/^\s*(['"])([^'"]+)\1\s*:/gm)) {
    if (seen.has(match[2])) findings.push(`Duplicate ${lang}: ${match[2]}`);
    seen.add(match[2]);
  }
}
const placeholders = value => [...value.matchAll(/\{([a-zA-Z0-9_]+)\}/g)].map(m => m[1]).sort().join(',');
const allKeys = new Set([...Object.keys(DICT.es), ...Object.keys(DICT.en)]);
for (const key of allKeys) {
  if (!Object.hasOwn(DICT.es, key) || !Object.hasOwn(DICT.en, key)) findings.push(`Language parity: ${key}`);
  else if (placeholders(DICT.es[key]) !== placeholders(DICT.en[key])) findings.push(`Placeholder parity: ${key}`);
}
function files(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap(entry =>
    entry.isDirectory() ? files(path.join(dir, entry.name)) : [path.join(dir, entry.name)]);
}
const references = new Set(DOM_MAP.map(entry => entry.k));
const dynamic = [];
const candidates = [];
const reviewedExclusions = [];
for (const suffix of ['client', 'repeater', 'sensor', 'room', 'local', 'unknown']) references.add('node.role_' + suffix);
for (const filename of files(jsRoot).filter(file => file.endsWith('.js') && !file.endsWith('i18n.js'))) {
  const content = fs.readFileSync(filename, 'utf8');
  for (const match of content.matchAll(/\b(?:I18n|window\.I18n)\.t\(\s*(['"])([^'"]+)\1/g)) references.add(match[2]);
  for (const match of content.matchAll(/\bI18n\.setText\([^,\n]+,\s*(['"])([^'"]+)\1/g)) references.add(match[2]);
  for (const key of qrTitleReferences(content)) references.add(key);
  for (const match of content.matchAll(/\b(?:I18n|window\.I18n)\.t\(\s*([^'"\s][^)]*)\)/g)) {
    dynamic.push({ file: path.relative(root, filename), expression: match[1] });
    for (const literal of match[1].matchAll(/['"]([a-z]+\.[a-z_]+)['"]/g)) references.add(literal[1]);
  }
  content.split('\n').forEach((line, index) => {
    if (/I18n\.setText\([^;]+\)\.replace\(/.test(line)) findings.push(`Invalid setText chaining: ${path.relative(root, filename)}:${index + 1}`);
  });
  const uiReport = scanUiLiterals(content, DICT.es, path.relative(root, filename));
  candidates.push(...uiReport.untranslatedCandidates);
  reviewedExclusions.push(...uiReport.reviewedExclusions);
}
const html = fs.readFileSync(path.join(root, 'src/web/static/index.html'), 'utf8');
for (const match of html.matchAll(/data-i18n(?:-[a-z-]+)?\s*=\s*['"]([^'"]+)['"]/g)) {
  if (!match[0].startsWith('data-i18n-params')) references.add(match[1]);
}
for (const key of references) {
  for (const lang of ['es', 'en']) if (!Object.hasOwn(DICT[lang], key)) findings.push(`Missing ${lang}: ${key}`);
}
const report = {
  catalog: { es: Object.keys(DICT.es).length, en: Object.keys(DICT.en).length },
  referencedKeys: references.size, staticSelectors: DOM_MAP.length,
  findings, dynamicReferences: dynamic, untranslatedCandidates: candidates, reviewedExclusions,
  limitations: [
    'Static reference and interpolation audit; visual behavior and selector matches require browser verification.',
    'User content, firmware responses, backend diagnostics, protocol labels, and numeric units retain their original content.',
    'Dynamic translation-key expressions are listed for manual review; this scan does not prove every UI string is localized.',
    'UI-literal analysis is lexical, not a JavaScript AST or runtime data-flow proof. Exact Spanish catalogue fallbacks are individually listed as exclusions.',
  ],
};
process.stdout.write(JSON.stringify(report, null, 2) + '\n');
process.exitCode = findings.length || candidates.length ? 1 : 0;
