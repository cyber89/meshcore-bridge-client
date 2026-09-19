import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = dirname(fileURLToPath(import.meta.url));
const docsRoot = resolve(scriptDir, '..');
const sourceRepo = resolve(docsRoot, '../openhop_repeater');
const sourceSpec = resolve(docsRoot, '../openhop_repeater/repeater/web/openapi.yaml');
const targetSpec = resolve(docsRoot, 'public/openapi/repeater.yaml');
const sourceRef = process.env.OPENHOP_REPEATER_OPENAPI_REF?.trim();

if (!existsSync(sourceSpec) && !sourceRef) {
  if (existsSync(targetSpec)) {
    console.warn(
      `OpenAPI source file not found: ${sourceSpec}. Using checked-in spec at ${targetSpec}.`
    );
    process.exit(0);
  }

  console.warn(`OpenAPI source file not found, skipping sync: ${sourceSpec}`);
  process.exit(0);
}

mkdirSync(dirname(targetSpec), { recursive: true });
let source;
if (sourceRef) {
  if (!existsSync(resolve(sourceRepo, '.git'))) {
    throw new Error(
      `OPENHOP_REPEATER_OPENAPI_REF requires a Git checkout at ${sourceRepo}`
    );
  }
  source = execFileSync(
    'git',
    ['-C', sourceRepo, 'show', `${sourceRef}:repeater/web/openapi.yaml`],
    { encoding: 'utf8' }
  );
} else {
  source = readFileSync(sourceSpec, 'utf8');
}

const spec = source
  .replaceAll('Check pyMC console availability', 'Check openHop Console availability')
  // Repeater's runtime and published install docs use port 8000. Keep the
  // central docs viewer from offering stale 8080 example servers until the
  // authoritative Repeater OpenAPI examples are corrected upstream.
  .replaceAll('http://localhost:8080/api', 'http://localhost:8000/api')
  .replaceAll('http://{host}:8080/api', 'http://{host}:8000/api');
writeFileSync(targetSpec, spec);
console.log(
  `Synced OpenAPI spec: ${sourceRef ? `${sourceRepo}@${sourceRef}` : sourceSpec} -> ${targetSpec}`
);
