---
title: Dashboard Template
description: Use the included Lovelace YAML dashboard template for the integration.
sidebar:
  order: 5
---

The repository includes a native Lovelace YAML dashboard template:

```text
dashboards/openhop_repeater_dashboard.yaml
```

## How to use it

1. Open the YAML file from the repository.
2. Replace `REPEATER_SLUG` with your repeater entity prefix.
3. Create or edit a dashboard **view** and open that view's YAML editor.
4. Paste the template there. In a complete dashboard's raw YAML, it belongs as
   one entry under `views:`, not at the document root.
5. Update any example dynamic entities so they match your own installation.
6. If the external sensor is not named `modem`, replace `_sensor_modem_` with
   that sensor's actual slug.

## Notes

- the template uses built-in Home Assistant cards only
- it is one Lovelace **view**, not a complete top-level `views:` dashboard
- broker and companion rows may need minor edits because those entities are generated from live repeater data
- the template now uses neutral placeholder names instead of install-specific examples
- current sections cover radio health, packet flow, LBT diagnostics, routing,
  neighbor links, plugins, GPS, external modem readings, controls, advert tuning,
  MQTT, companions, updates, and database metrics

The comprehensive template uses the current **Sections** frontend, which requires
a newer Home Assistant frontend than the integration's 2024.1 minimum. A smaller
native view is available as `dashboards/openhop_operations.yaml`.

Radio child-device prefixes are independent of `REPEATER_SLUG`. Replace complete
dynamic entity IDs with those shown in your installation, including area prefixes
or numeric suffixes; repeat rows for multiple sources and remove unsupported rows.
Back up the dashboard before replacing an existing view.

## Optional alert blueprints

The repository includes opt-in templates under `blueprints/automation/openhop/`
for low battery, high temperature, Repeater unavailability, MQTT disconnection,
stale sources, plugin failure, and available updates. Installing the integration
does not create these automations or choose a notification destination.

In **Settings → Automations & scenes → Blueprints → Import Blueprint**, paste the
GitHub URL of the desired YAML file from the
[blueprint directory](https://github.com/openhop-dev/openHop-HA-Integration/tree/main/blueprints/automation/openhop).
Then create an automation, select the actual monitored entity, set duration and
threshold where applicable, and supply your own actions. Match thresholds to the
sensor's unit; use an individual broker or plugin entity for those alerts.

Alerts trigger after sustained state/threshold transitions, not repeatedly while
a condition stays active. Home Assistant restarts and automation reloads reset
the waiting timers.

Source: [dashboard and blueprint guide at `fc60f15`](https://github.com/openhop-dev/openHop-HA-Integration/blob/fc60f15aed1473a65a0f4363cdb85b7c670736e8/README.md#dashboard-template).

## Related

- [Entities and Controls](/projects/openhop-ha-integration/entities-and-controls/)
