#!/usr/bin/env node
'use strict';

// Read-only catalogue audit. It never starts a bridge, browser, or radio driver.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
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
for (const suffix of ['client', 'repeater', 'sensor', 'room', 'local', 'unknown']) references.add('node.role_' + suffix);
for (const filename of files(jsRoot).filter(file => file.endsWith('.js') && !file.endsWith('i18n.js'))) {
  const content = fs.readFileSync(filename, 'utf8');
  for (const match of content.matchAll(/\b(?:I18n|window\.I18n)\.t\(\s*(['"])([^'"]+)\1/g)) references.add(match[2]);
  for (const match of content.matchAll(/\bI18n\.setText\([^,\n]+,\s*(['"])([^'"]+)\1/g)) references.add(match[2]);
  for (const match of content.matchAll(/\bkey:\s*(['"])([^'"]+)\1/g)) references.add(match[2]);
  for (const match of content.matchAll(/\b(?:I18n|window\.I18n)\.t\(\s*([^'"\s][^)]*)\)/g)) {
    dynamic.push({ file: path.relative(root, filename), expression: match[1] });
    for (const literal of match[1].matchAll(/['"]([a-z]+\.[a-z_]+)['"]/g)) references.add(literal[1]);
  }
  content.split('\n').forEach((line, index) => {
    if (/^\s*(\/\/|\*|console\.)/.test(line)) return;
    if (/(showToast|_notify|alert|confirm|textContent\s*=|innerHTML\s*=|\.title\s*=)/.test(line) &&
        /[áéíóúñ¿¡]|\b(Canal|Sin|Espera|Borrar|Sondeando|Transmitiendo|Guardando)\b/.test(line) &&
        !/I18n\.(?:t|setText)/.test(line)) {
      candidates.push({ file: path.relative(root, filename), line: index + 1, source: line.trim() });
    }
    if (/I18n\.setText\([^;]+\)\.replace\(/.test(line)) findings.push(`Invalid setText chaining: ${path.relative(root, filename)}:${index + 1}`);
  });
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
  findings, dynamicReferences: dynamic, untranslatedCandidates: candidates,
  limitations: [
    'Static reference and interpolation audit; visual behavior and selector matches require browser verification.',
    'User content, firmware responses, backend diagnostics, protocol labels, and numeric units retain their original content.',
    'Dynamic translation-key expressions are listed for manual review; this scan does not prove every UI string is localized.',
  ],
};
process.stdout.write(JSON.stringify(report, null, 2) + '\n');
process.exitCode = findings.length ? 1 : 0;
