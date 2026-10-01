# postmarketOS for Realme 6 (RMX2001 / nemo)

This repository builds a self-contained recovery installer for the Realme 6.
It contains the MT6785 kernel package, initramfs and postmarketOS rootfs.

## Current hardware status

The OpenRC + Phosh root filesystem was installed from recovery and reached
userspace on real hardware on 2026-10-01 when paired with the known-good
downstream 4.14 hybrid boot image. NetworkManager joined Wi-Fi, the phone
appeared as a USB-NCM device, and SSH became reachable over Wi-Fi.

The repository's mainline 6.16 kernel remains a separate, experimental target.
Display and touch are not implemented in its board device tree. The downstream
kernel can display Phosh without the earlier framebuffer flashing, but touch
and the graphical session still require validation. See the
[bring-up ledger](docs/bringup.md) for exact artifacts, results, and next steps.

## Build on Linux

```sh
git clone https://github.com/Hari-Pi/realme6-pmos-port.git
cd realme6-pmos-port
python3 scripts/build-recovery.py
```

The tool prompts for the image's login password and produces:

- `dist/pmos-realme-nemo.zip` — recovery installer
- `dist/verification.json` — archive, boot header, DTB and AVB checks
- `dist/SHA256SUMS` — transfer checksum
- `dist/build.lock.json` — source revisions
- `dist/build-manifest.json` — package input checksums and image configuration

For unattended builds, supply `PMOS_PASSWORD` in the build environment. Passwords
may appear in pmbootstrap's local logs, so keep the work directory private.
An optional `--ssh-key /path/to/id_ed25519.pub` embeds your **public** key.
`--setup-only` verifies the setup and package sources without compiling;
`--jobs 12` limits build parallelism. `--ui phosh` selects the graphical
userspace; it does not add a panel driver to the mainline kernel.

## Install from recovery

**Installing this zip erases the phone's userdata, including the existing
Droidian/Android rootfs, and replaces boot.** Save boot, recovery, userdata and
personal-file backups off the phone first. The bootloader must be unlocked,
with verification disabled as in the working port; an unsigned AVB footer is
not a substitute for unlocking or disabling verification.

Copy the zip to a microSD card or use TWRP's ADB sideload. Do not keep the only
copy on internal `/data`, because the installer repartitions it. In TWRP,
unmount data, install the zip, then reboot to system. Recovery itself is not
replaced. A mainline image may have a black display; test USB SSH.

See [build](docs/build.md), [verification](docs/verify.md),
[USB SSH](docs/ssh.md), [hardware bring-up](docs/bringup.md), and the
[documentation audit](docs/audit.md).

## Sources

`device-realme-nemo/` and `linux-realme-nemo/` are the authoritative pmaports
overlays. The helper pins pmbootstrap and pmaports using `build.lock.json`, then
copies these packages into its own ignored `pmaports-tmp/aports` checkout.
Linux source is pinned to the checksum-verified MT6785 `6.16.4-r0` archive.
Alpine/postmarketOS binary repositories are rolling: these pins record source
inputs, but do not promise byte-for-byte reproducible images over time.

The working [Droidian reference](https://github.com/Hari-Pi/kernel_realme_RMX2001)
supplies boot-layout facts and downstream hardware reference code. Its 4.14
kernel, Halium initramfs and adaptation `.deb` are not dependencies of this
mainline postmarketOS image.

`pmaports-tmp/notes/` preserves historical reports; use the new build helper and
verification report for current artifacts.
