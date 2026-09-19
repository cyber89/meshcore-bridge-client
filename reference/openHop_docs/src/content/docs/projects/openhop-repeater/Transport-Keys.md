---
title: Transport Keys
description: Configure scoped flood regions and transport-key policy without exposing key material.
sidebar:
  order: 13
---

Transport keys scope flood traffic to a region or group. A scoped flood carries a
derived transport code; a repeater compares that code with its stored keys and
applies the matching key's flood policy. They are **routing scope**, not a
replacement for message encryption or dashboard authentication. Direct forwarding
is not gated by flood policy, although a locally generated flood reply to a
direct request may use the configured default scope.

## Where keys are stored

Transport keys are runtime records in Repeater storage, not a static
`transport_keys:` block in `config.yaml.example`. Manage them through the
authenticated dashboard or API. The API supports listing, creating, reading,
updating, and deleting keys under the Transport Keys endpoints.

The Repeater caches the stored key list briefly for packet processing. Create,
update, and delete operations invalidate that cache through the supported API
path; do not edit the SQLite database directly. Storage changes also rebuild the
served-region map shared by the dispatcher and companion bridges, including the
default flood-reply scope.

Use **System → Configuration → Access → Regions/Keys**. Records include `name`,
`flood_policy` (`allow` or `deny`), optional `parent_id`, and base64 key material.
The API routes are `GET`/`POST /api/transport_keys` and
`GET`/`PUT`/`DELETE /api/transport_key/{key_id}`. Listing/reading records exposes
key material to authenticated callers; do not publish those responses.

## Public and private regions

Public region keys are normally derived from the region name using MeshCore
key derivation. A known public name therefore does not provide secret group
membership. Private `$` regions need stored key material that cannot be
reconstructed from the name; imported custom keys also need to be distributed
consistently. The runtime region map preserves custom 16-byte material rather
than replacing it with the public name-derived key.

The `*` wildcard represents unscoped traffic, not a named region entry. It is
controlled by `mesh.unscoped_flood_allow` rather than a private wildcard key.

## Flood policy interaction

- `mesh.unscoped_flood_allow` controls flood traffic that has no transport code.
- A scoped flood must match a stored transport key.
- Each matching key has an allow/deny flood policy.
- `mesh.default_region` scopes locally originated repeater adverts when set.
- `mesh.path_hash_mode` and `mesh.loop_detect` control different routing
  behaviors and do not replace transport-key policy.

## Configure a default region

Use the dashboard or mesh CLI to select a stored region for repeater-originated
flood adverts. Keep `mesh.default_region: null` when locally originated floods
should remain unscoped. Clearing a region must clear both the name and effective
key; use the supported UI/API/CLI rather than editing partial values.

## Flood reply scope

The dispatcher and companion bridges use the served-region map to retain a
matched request's region when generating a flood reply. An explicitly unscoped
flood request stays unscoped. Deny-flood regions are excluded from inbound
matching; a default does not make such a region accepted for inbound floods.

When the request scope is unknown (for example a direct request without a
usable return path), the default reply scope resolves from `mesh.default_region`
in the served-region table. A private default uses its stored key. Unset, `*`,
missing, or unusable defaults resolve to no default key, so that fallback reply
is unscoped. The region map is refreshed after supported region/key edits;
check the selected default after deleting or re-keying a region.

This is independent of the neighbour-scope discovery UI and optional MQTT
publication: [MQTT and LetsMesh Integration](/projects/openhop-repeater/letsmesh-integration/).

## Security and operations

- Treat the raw 16-byte key as a secret. Do not paste it into issues, logs,
  screenshots, or public config examples.
- Distribute a region key through a trusted channel.
- Name regions consistently so operators can identify intended scope.
- Test with a non-critical key and monitor denied/matched traffic before broadly
  enforcing a policy.
- During rotation, account for nodes still using the old key before removing it.
- Back up Repeater state securely; transport-key records live with runtime data.

See [Configuration Reference](/projects/openhop-repeater/config-file/#mesh) and
the authenticated [API Reference](/projects/openhop-repeater/api-reference/) for
the current controls.

## Implementation references

- [Served-region and default-scope implementation](https://github.com/openhop-dev/openhop_repeater/blob/ffd239d/repeater/region_map_builder.py)
- [Region map regression tests](https://github.com/openhop-dev/openhop_repeater/blob/ffd239d/tests/test_region_map_wiring.py)
