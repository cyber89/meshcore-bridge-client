'use strict';

const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const root = path.resolve(__dirname, '../src/web/static/js');

function sources(directory) {
  return fs.readdirSync(directory, {withFileTypes: true}).flatMap(entry => {
    const filename = path.join(directory, entry.name);
    if (entry.isDirectory()) return sources(filename);
    return entry.isFile() && filename.endsWith('.js') && !filename.endsWith('.min.js')
      ? [filename] : [];
  });
}

let failures = 0;
const files = sources(root);
for (const filename of files) {
  const result = spawnSync(process.execPath, ['--check', filename], {stdio: 'inherit'});
  if (result.error || result.status !== 0) {
    failures += 1;
    if (result.error) console.error(result.error.message);
  }
}
console.log(`JavaScript syntax: ${files.length} files, ${failures} failures`);
process.exitCode = failures ? 1 : 0;
