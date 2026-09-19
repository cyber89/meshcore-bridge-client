---
title: USB Device Setup
description: Pass an openHop USB modem or KISS serial radio into the non-privileged Unraid container.
sidebar:
  order: 3
---

A TCP modem does not need a Docker device mapping. Use this guide for USB serial
openHop Modems and KISS radios that appear as `/dev/ttyACM*` or `/dev/ttyUSB*`.

## Identify the device

Open **Terminal** in Unraid and prefer a stable identifier:

```bash
ls -l /dev/serial/by-id/
```

If none exists, compare common devices before and after connecting the modem:

```bash
ls -l /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
```

Do not guess. Mapping the wrong serial interface can interfere with other hardware.

## Add it to the container

1. Open **Docker** and stop **openHop-Repeater**.
2. Select the container, choose **Edit**, then **Add another Path, Port, Variable,
   Label or Device**.
3. Set **Config Type** to **Device**.
4. Use the detected host path. If separate host/container fields appear, use the
   same path for both.
5. Keep **Privileged** disabled and click **Apply**.

Example:

```text
/dev/serial/by-id/usb-Your_Modem_Name-if00
```

## Configure Repeater

Open `http://<unraid-ip>:8000/setup`, choose the matching openHop USB or KISS
backend, and enter the exact container device path. Confirm the baud rate and all
mesh/RF settings before transmitting.

## Verify

```bash
docker inspect openHop-Repeater --format '{{json .HostConfig.Devices}}'
docker logs --tail 100 openHop-Repeater
```

For a simple serial path:

```bash
docker exec openHop-Repeater ls -l /dev/ttyACM0
```

Replace the example with the configured path.

## Troubleshooting

- **Path changed:** prefer `/dev/serial/by-id/...`; otherwise update the Device
  mapping after reconnect/reboot.
- **Permission denied:** confirm it is a Device rather than a Path mapping. The
  official template runs as root while remaining non-privileged.
- **Device busy:** stop any other host process or container using that serial port.
- **Repeated disconnects:** check the data cable, adapter, hub, and power supply,
  then recreate/restart the container after reconnection.
- **No serial interface:** verify the cable supports data and review `dmesg` after
  reconnecting. If the modem is networked, remove the Device mapping and use TCP.
