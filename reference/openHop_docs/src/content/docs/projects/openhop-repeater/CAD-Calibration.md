---
title: CAD Calibration
description: Understand, run, validate, and save Channel Activity Detection calibration for a Repeater radio.
sidebar:
  order: 10.5
---

Channel Activity Detection (CAD) is the SX1262 radio's short check for LoRa
activity on the configured channel. Before transmitting, a CAD-capable Repeater
uses this result for Listen Before Talk (LBT): a clear result lets transmission
continue, while a busy result causes a short backoff and retry.

CAD is not a general-purpose signal-strength or noise scan. It looks for LoRa
activity that matches the radio's current frequency, spreading factor,
bandwidth, and coding rate.

## What calibration changes

The radio decides whether CAD is clear or busy using three values:

- **Peak threshold** controls the required correlation peak.
- **Minimum threshold** controls the minimum correlation level.
- **CAD symbols** selects how many LoRa symbols the radio examines: `1`, `2`,
  `4`, `8`, or `16`.

Repeater starts with spreading-factor-specific Semtech defaults. Calibration
runs real CAD checks across candidate peak/minimum thresholds, records
successful detections, non-detections, timeouts, and errors, and recommends a
stable combination for the current radio settings.

Saving the recommendation writes these values under `radio.cad` in
`/etc/openhop_repeater/config.yaml` and applies them to the radio. Restart the
`openhop-repeater` service when prompted so the saved values are used from a
clean radio initialization.

## Why users should calibrate

Generic defaults cannot account for every radio module, front-end module,
antenna, board layout, and local RF environment. A threshold that is poorly
matched to the installation can produce either kind of mistake:

- **False busy:** the radio reports activity on an idle channel. LBT waits and
  retries unnecessarily, increasing transmit latency.
- **False clear:** the radio misses compatible activity. The Repeater may start
  transmitting over another packet, increasing collision and retry risk.

Calibration is therefore recommended after a new CAD-capable radio is installed
and after changing the radio hardware or its frequency, spreading factor,
bandwidth, or coding rate. It is especially useful when LBT repeatedly backs
off on an apparently quiet channel or fails to react to known compatible
traffic.

Calibration improves the clear/busy decision; it does not fix a mismatched
frequency or modulation, a poor antenna, excessive noise, incorrect RF-switch
wiring, packet decoding failures, or legal duty-cycle limits.

## Recommended calibration flow

The dashboard CAD Calibration tool is currently marked **Experimental**. Use it
only after the Repeater receives normal packets with the intended radio
configuration.

1. Open the Repeater dashboard and select **CAD Calibration**.
2. Confirm the displayed frequency, spreading factor, bandwidth, and coding rate
   match the network you intend to use.
3. Run a **Quiet baseline** while no intentional compatible transmitter is
   active. This pass looks for low false-detection rates with no timeouts or
   errors.
4. Generate repeated traffic from another LoRa device using the exact same
   frequency, spreading factor, bandwidth, and coding rate.
5. Run **Known-signal calibration** while that traffic is active. This pass
   starts from the Semtech defaults and looks for reliable detections with zero
   timeouts/errors before considering more sensitive thresholds.
6. Review the recommendation. A quiet-only run is only partially validated; do
   not treat it as proof that real packets will be detected.
7. Save only a stable, known-signal-validated recommendation, restart when
   prompted, and monitor normal traffic and LBT retry behavior.
8. Repeat the known-signal check once if conditions are variable. Keep the old
   values or return to defaults if the result is inconsistent.

Do not run the quiet baseline while the mesh is busy. If the tool reports
significant activity during quiet mode, wait for an idle period and rerun it.
Likewise, a known-signal run with no detections is inconclusive: first verify the
transmitter uses the exact same LoRa settings and is sending often enough.

## When calibration is available

The active radio backend must expose CAD support. Current direct SX1262 and
openHop Modem USB/TCP drivers support the Repeater calibration interface. The
page will report that CAD is unavailable when the configured backend does not
provide it, the radio is offline, or the event loop cannot run the checks.

Because calibration temporarily performs repeated radio checks and can apply
thresholds live, run it from an authenticated dashboard on a trusted network.
Do not start it during a maintenance window in which predictable transmit timing
is required.

## Interpreting results

Prefer a result with:

- no timeouts or errors;
- near-zero detections during a genuinely quiet baseline;
- high, repeatable detection during known compatible traffic; and
- thresholds close to the defaults unless extra sensitivity is actually needed.

More sensitive is not automatically better. It can detect weaker packets, but
it can also increase false-busy results. The calibration engine deliberately
prefers the least-sensitive stable setting that meets its known-signal target.

If calibration repeatedly times out, stop and troubleshoot the radio transport,
radio initialization, and hardware first. Do not save a recommendation derived
from unstable or incomplete samples.

See [Performance Tuning](/projects/openhop-repeater/performance-tuning/) for the
metrics to compare afterward and [Troubleshooting](/projects/openhop-repeater/troubleshooting/)
for radio and modem diagnostics.
