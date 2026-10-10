#!/usr/bin/env node
'use strict';

// Build tools stay outside Python/runtime dependencies. Never minify in a request.
const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const zlib = require('node:zlib');
const esbuild = require('../tools/frontend/node_modules/esbuild');

const root = path.resolve(__dirname, '../src/web/static');
const manifestPath = path.join(root, 'asset-manifest.json');
const check = process.argv.includes('--check');
const hash = data => crypto.createHash('sha256').update(data).digest('hex');
const normalize = value => value.split(path.sep).join('/');
const vendor = new Set([
  'js/bootstrap.bundle.min.js',
  'css/bootstrap.min.css',
  'css/bootstrap-slate.min.css',
  'css/bootstrap-zephyr.min.css',
  'css/bootstrap-icons.min.css',
]);

async function sources(directory) {
  const files = [];
  for (const entry of await fs.readdir(directory, { withFileTypes: true })) {
    const filename = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await sources(filename));
    else if (entry.isFile()) {
      const relative = normalize(path.relative(root, filename));
      if (relative === 'index.html' || vendor.has(relative)
          || (/\.(js|css)$/.test(relative) && !/\.min\.(js|css)$/.test(relative))) {
        files.push(relative);
      }
    }
  }
  return files.sort();
}

async function artifact(relative, contents, mismatches) {
  const filename = path.join(root, relative);
  if (check) {
    const actual = await fs.readFile(filename).catch(error => {
      if (error.code === 'ENOENT') return null;
      throw error;
    });
    if (!actual || !contents.equals(actual)) mismatches.push(relative);
    return;
  }
  const temporary = filename + '.tmp';
  await fs.writeFile(temporary, contents);
  await fs.rename(temporary, filename);
}

async function main() {
  const assets = {};
  const pending = new Map();
  const mismatches = [];
  for (const source of await sources(root)) {
    const original = await fs.readFile(path.join(root, source));
    const extension = path.extname(source);
    let file = source;
    let content = original;
    if (source === 'css/bootstrap-zephyr.min.css') {
      // Preserve the official vendor file and license; serve a derived theme
      // without its Google Fonts import, since app.css uses system fonts.
      content = Buffer.from(original.toString('utf8').replace(
        /@import\s+url\(\s*https:\/\/fonts\.googleapis\.com\/[^)]*\)\s*;/g, '',
      ));
      file = 'css/bootstrap-zephyr.local.min.css';
      pending.set(file, content);
    } else if (!vendor.has(source) && (extension === '.js' || extension === '.css')) {
      // Keep relative ESM imports untouched: the server selects each minimized
      // module using this manifest. Classic scripts keep their public globals.
      const module = source === 'js/app.js' || source.startsWith('js/core/')
        || source.startsWith('js/modules/');
      const result = await esbuild.transform(original.toString('utf8'), {
        loader: extension === '.css' ? 'css' : 'js',
        sourcefile: source,
        minifyWhitespace: true,
        minifySyntax: true,
        minifyIdentifiers: module,
        ...(module ? { format: 'esm' } : {}),
        target: 'es2022',
        charset: 'utf8',
        legalComments: 'inline',
      });
      for (const warning of result.warnings) {
        console.warn((await esbuild.formatMessages([warning], { kind: 'warning' })).join(''));
      }
      file = source.replace(/\.(js|css)$/, '.min.$1');
      content = Buffer.from(result.code);
      pending.set(file, content);
    }
    const compressed = zlib.gzipSync(content, { level: 9 });
    // The gzip OS field otherwise depends on the build host. 255 means unknown
    // and keeps the header identical across Windows/POSIX without changing data.
    compressed[9] = 255;
    // Verify generated gzip representation against the exact served bytes.
    if (!zlib.gunzipSync(compressed).equals(content)) throw new Error(`Invalid gzip: ${file}`);
    pending.set(file + '.gz', compressed);
    assets[source] = {
      file,
      source_sha256: hash(original),
      sha256: hash(content),
      gzip_sha256: hash(compressed),
      source_bytes: original.length,
      bytes: content.length,
      gzip_bytes: compressed.length,
    };
  }
  for (const [file, content] of pending) await artifact(file, content, mismatches);
  // Publishing the manifest last lets partial rebuilds fall back to originals.
  await artifact('asset-manifest.json', Buffer.from(JSON.stringify({
    version: 1,
    generator: `esbuild ${esbuild.version}; gzip level 9`,
    assets,
  }, null, 2) + '\n'), mismatches);
  if (mismatches.length) {
    console.error(`Stale or missing artifacts (${mismatches.length}):\n${mismatches.join('\n')}`);
    process.exitCode = 1;
    return;
  }
  const totals = Object.values(assets).reduce((sum, asset) => ({
    source: sum.source + asset.source_bytes,
    minimized: sum.minimized + asset.bytes,
    gzip: sum.gzip + asset.gzip_bytes,
  }), { source: 0, minimized: 0, gzip: 0 });
  console.log(`${check ? 'Verified' : 'Built'} ${Object.keys(assets).length} assets: `
    + `${totals.source} source bytes → ${totals.minimized} served bytes → ${totals.gzip} gzip bytes.`);
}

main().catch(error => { console.error(error); process.exitCode = 1; });
