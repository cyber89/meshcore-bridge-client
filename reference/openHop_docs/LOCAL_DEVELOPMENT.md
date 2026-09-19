# Local Development

This site runs with Astro and Starlight.

## Requirements

- Node.js `22.12.0` or newer
- `npm`

If you use `nvm`:

```bash
nvm install 22.12.0
nvm use 22.12.0
```

## Install Dependencies

```bash
npm install
```

## Run The Dev Server

```bash
npm run dev
```

Default local URL:

- `http://localhost:4321/`

## Build The Site

```bash
npm run build
```

## OpenAPI Sync Behavior

Before `dev` and `build`, the repo runs:

```bash
npm run sync:openapi
```

If a local sibling repo exists at:

```text
../openhop_repeater/repeater/web/openapi.yaml
```

the checked-in repeater OpenAPI file will be refreshed from that source.

To build against a specific Repeater Git ref without switching the sibling
checkout, set `OPENHOP_REPEATER_OPENAPI_REF`. For example, to use the fetched
development branch exactly:

```bash
git -C ../openhop_repeater fetch origin
OPENHOP_REPEATER_OPENAPI_REF=origin/dev npm run build
```

An explicitly requested ref must exist in the sibling Git checkout; the sync
fails rather than silently using a different spec.

If that local repo is not present, the docs site falls back to the checked-in spec in:

```text
public/openapi/repeater.yaml
```

## Content Locations

- Main docs content: `src/content/docs/`
- openHop Core docs: `src/content/docs/projects/openhop-core/`
- openHop Repeater docs: `src/content/docs/projects/openhop-repeater/`
- openHop Modem docs: `src/content/docs/projects/openhop-modem/`
- openHop HA Integration docs: `src/content/docs/projects/openhop-ha-integration/`
- openHop HA Add-on docs: `src/content/docs/projects/openhop-ha-addon/`
- openHop for Unraid docs: `src/content/docs/projects/openhop-unraid/`

## Common Commands

```bash
npm run dev
npm run build
npm run preview
```
