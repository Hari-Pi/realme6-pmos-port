# postmarketOS Port for Realme 6 (RMX2001 / nemo)

This repository contains the initial working postmarketOS (pmOS) port for the Realme 6 (`realme-nemo`) featuring the MediaTek Helio G90T (MT6785) SoC.

## Current Status
* **Kernel**: Mainline 6.16.4 based on `mt6785-mainline` fork.
* **Booting**: Successfully boots mainline kernel to initramfs and SSH (`dropbear`).
* **GUI**: Black screen (display/panel driver porting is pending).
* **Networking**: USB RNDIS networking works out of the box.

## Device Quirks & Fixes Applied
1. **AVB Footer Required**: MTK bootloader requires an AVB footer padded to 32MB, otherwise the device bootloops. See `docs/avb.md`.
2. **Cmdline Overflow**: LK bootloader overflows and panics if the kernel cmdline is larger than ~93 chars. Removed plymouth splash arguments to keep it under 75 chars. See `docs/cmdline_overflow.md`.
3. **Empty DTBO Requirement**: `mkbootimg` must be supplied with an empty DTBO via `--recovery_dtbo` for the device to boot correctly.

## How to use
Copy the `device-realme-nemo` and `linux-realme-nemo` directories to your local `pmaports` tree (`device/testing/`). Run `pmbootstrap checksum` then `pmbootstrap build`.

See `docs/progress.md` for full installation logic and debugging notes.
