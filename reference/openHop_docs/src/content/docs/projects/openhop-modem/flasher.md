---
title: Firmware Flasher
description: Flash openHop Modem firmware with the browser-based Web Serial flasher.
---

The openHop MeshCore Flasher is a static browser app that flashes supported modem firmware over Web Serial. It does not require a local flashing server; the browser talks directly to the device.

Open the flasher here:

[https://flasher.openhop.dev/](https://flasher.openhop.dev/)

Source repository:

[https://github.com/openhop-dev/openHop-Modem-Flasher](https://github.com/openhop-dev/openHop-Modem-Flasher)

## Browser requirements

Use a browser with Web Serial support, such as Chrome, Edge, or Chromium. The site must be served over HTTPS, which the hosted flasher already does.

## Firmware source

The flasher reads most modem firmware files from:

[https://github.com/openhop-dev/openhop_modem/tree/main/firmware](https://github.com/openhop-dev/openhop_modem/tree/main/firmware)

ESP32-family firmware variants use this layout:

| File | Used for |
| --- | --- |
| `firmware.factory.bin` | Complete first install or recovery image written at `0x0`. |
| `bootloader.bin` | Bootloader component; its offset is selected by the target toolchain. |
| `partitions.bin` | Partition-table component used to assemble a complete install. |
| `firmware.bin` | App-only update, normally written at `0x10000` on a compatible existing layout. |
| `manifest.json` | Browser flasher manifest, present only for web-manifest-enabled targets. |
| `SHA256SUMS.txt` | Checksums for the staged assets. |

nRF52 variants provide `firmware.hex`, `firmware.zip`, `firmware.uf2`, and
`SHA256SUMS.txt`. The RAK4631 Ethernet target also stages `firmware.ota`, but it
is groundwork and is not an installable update path. Do not apply ESP32 offsets
to nRF52 targets.
ESP32-P4 bootloader offsets also differ from common ESP32-S3 layouts, so prefer
the factory image or the hosted flasher instead of a hand-written component
command. Its complete factory image is still written at `0x0`; the P4 bootloader
component begins at `0x2000`.

## Flash a device

The hosted flasher covers its published supported targets. Some boards and
recovery cases require esptool, PlatformIO, or nRF52 DFU instead.

1. Connect a flasher-supported modem board to your computer over USB.
2. Open [flasher.openhop.dev](https://flasher.openhop.dev/).
3. Select the exact device model.
4. Select the openHop Modem firmware role/version shown by the flasher.
5. For an ESP32-family target, click the browser serial connect button, choose the
   board's serial port, and click **Flash** for a normal update.
6. For an nRF52 target, connect to the application serial port and click
   **Enter DFU mode**. Then click **Flash** and select the newly appearing
   bootloader port.
7. Use **Erase Device** only on ESP32-family targets, and only for a first install,
   a corrupted device, or when changing layouts. It is not an nRF52 action.

Do not disconnect the board while flashing. After a successful flash, reset or power-cycle the board if it does not reboot automatically.

## Which flash action to choose

| Action | Meaning | When to use |
| --- | --- | --- |
| Flash | Writes the application firmware using the selected variant's manifest. | Normal updates on a board that already has a compatible bootloader and partition table. |
| Erase Device | On ESP32-family targets, erases and installs the selected variant's complete firmware layout. | Fresh installs, recovery, or switching an ESP32-family board from another firmware layout. |

## Board bootloader notes

Some ESP32-family boards enter download mode automatically. If the browser cannot connect or flashing fails before transfer starts, put the board into bootloader mode manually:

- Many ESP32 boards: hold **BOOT**, tap **RESET**, release **RESET**, then release **BOOT**.
- Some XIAO ESP32 boards: double-tap reset or hold the boot button while plugging in USB.
- WaveShare ESP32-P4-Nano: use the native USB-Serial-JTAG USB-C port for flashing, not the CH343P debug UART port.

## After flashing

For USB serial deployments, connect the board to the Repeater host and configure `radio_type: modem_usb`.

For Wi-Fi deployments:

1. Connect to the device setup AP if this is the first boot.
2. Open `http://192.168.4.1`.
3. Save Wi-Fi credentials and restart.
4. Find the assigned hostname/IP.
5. Configure Repeater with `radio_type: modem_tcp`.

Wired Ethernet targets normally use DHCP rather than the Wi-Fi setup AP. The
RAK4631 WisMesh Ethernet modem has no mDNS or `/update` route; update it through
Bluetooth DFU with `firmware.zip`, or recover it through USB serial DFU.

See [Repeater Integration](/projects/openhop-modem/repeater-integration/) for the Repeater config blocks.

## Troubleshooting

- If no serial port appears, try another USB cable and confirm it is a data cable.
- If flashing starts but fails, lower the baud rate if the flasher exposes that option.
- If the board will not enter download mode, use the board-specific boot sequence above.
- If the modem is on Wi-Fi but Repeater cannot connect, verify `curl -u admin:REPLACE_WITH_PASSWORD http://<modem-host>/api/stats` and TCP port `5055` from the Repeater host.
