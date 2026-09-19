---
title: Security and Authentication
description: Secure dashboard, API, WebSocket, identity, and integration access to openHop Repeater.
sidebar:
  order: 12.5
---

The embedded HTTP service is designed for a trusted network. It is not a hardened
public-internet boundary.

## First login

Use `http://<repeater-ip>:8000/setup` for initial onboarding. Replace all example or
default admin and guest passwords. When no JWT secret exists, Repeater generates
one; keep the resulting config private.

Completing the wizard persists `setup_completed: true`. A configured non-default
admin password also closes anonymous provisioning on legacy configurations.
Changing the node name or choosing a null radio does not reopen setup. A
configured installation requires authentication for setup/import operations;
restoring defaults through the authenticated importer does not reopen anonymous
provisioning. Complete first boot on an isolated trusted network.

Most `/api` routes require authentication. Public setup and documentation routes
are intentionally limited. Do not assume an endpoint is harmless because it is a
GET request, and do not expose the interactive API viewer to untrusted users.

## Authentication methods

- **Dashboard login:** username `admin` with
  `repeater.security.admin_password`. `guest_password` and `allow_read_only`
  govern MeshCore mesh-client access, not dashboard guest/anonymous access.
- **Web sessions:** JWTs in `Authorization: Bearer …`; token lifetime is set by
  `jwt_expiry_minutes`, and valid sessions can be refreshed. Failed logins are
  throttled with HTTP `429` and `Retry-After`; wait rather than repeatedly retrying.
- **Automation:** API tokens created through the authenticated dashboard/API
  are sent in `X-API-Key`, not as a JWT Bearer token. The plaintext is shown only
  at creation; retain it securely and revoke retired integrations.
- **WebSocket/SSE:** use the client's authenticated connection flow. SSE supports
  a JWT query token because EventSource cannot add custom headers. Protect proxy
  and access logs: removing a query token before handler dispatch cannot remove
  it from an upstream log. Prefer headers for ordinary HTTP requests.

**API tokens are administrator-equivalent, not scoped read-only credentials.**
They can administer plugins, install uploaded wheels, and read plugin settings
as well as read status. Separate tokens help revocation and identification but
do not limit permissions. Do not give one to an untrusted or telemetry-only
consumer. Never share tokens in screenshots, issue reports, or shell history.

## Network exposure

The default listener is `0.0.0.0:8000`. Prefer one of:

- trusted LAN plus firewall rules;
- authenticated VPN;
- authenticated HTTPS reverse proxy.

CORS is disabled by default. Enabling it permits broad browser cross-origin access;
do so only for a known frontend and treat the bearer token as the remaining
security boundary.

## Protect secret material

Treat these as secrets:

- `repeater.identity_key` or the configured identity file;
- JWT secret and configured admin/guest passwords (the current local login
  compares the password stored in config; do not assume it is hashed);
- API tokens;
- modem, MQTT, LetsMesh, and Glass tokens or credentials;
- backups containing configuration or databases.

Do not paste the complete config into support requests. Redact values while leaving
field names and non-sensitive topology details visible.

The main Repeater identity, room-server identities, companion identities, and
transport keys serve different purposes. Back them up separately and do not reuse
one as another.

## Plugin trust boundary

[Plugins](/projects/openhop-repeater/plugins/) run as external applications under
the service account (or configured container account). Separate processes and
virtual environments isolate dependencies, **not** filesystem, network, or
credential access. Never run the manager as root to bypass a permissions error.

Application UI assets under `/plugins/{id}/…` are static browser code; they are
not a private storage location. Only the declared UI subtree is served, with
path/symlink confinement, but this is not a sandbox for untrusted JavaScript.
Do not package credentials, logs, or runtime data as UI assets.

Catalogue wheel checksums verify the approved wheel, not every dependency pip
resolves. Trust both plugin authors and dependency sources; use controlled
dependency sources when reproducibility is required. Back up plugin data and
protect settings as secrets. See the [Plugin Development guide](/projects/openhop-repeater/plugin-development/)
for packaging boundaries.

For existing native installs, perform one administrator-run updated
`manage.sh upgrade` to refresh the privileged OTA helper. A wheel-only update
cannot replace that root-owned helper safely. Do not make the Repeater venv
service-writable or bypass trusted-directory checks to enable plugin updates.

## Backup and recovery

Back up `/etc/openhop_repeater` and `/var/lib/openhop_repeater` together. Store the
backup encrypted and test recovery off-air or in `no_tx`/null-radio mode. Restoring
only the database without the matching identity/config can produce a different
node identity or unusable integration credentials.

## Related pages

- [Identity Management](/projects/openhop-repeater/identity-management/)
- [API Reference](/projects/openhop-repeater/api-reference/)
- [Troubleshooting](/projects/openhop-repeater/troubleshooting/)

## Implementation references

- [Local login implementation](https://github.com/openhop-dev/openhop_repeater/blob/ffd239d/repeater/web/auth_endpoints.py)
- [HTTP authentication middleware](https://github.com/openhop-dev/openhop_repeater/blob/ffd239d/repeater/web/auth/cherrypy_tool.py)
- [Provisioning authorization regressions](https://github.com/openhop-dev/openhop_repeater/blob/ffd239d/tests/test_setup_authorization_hardening.py)
