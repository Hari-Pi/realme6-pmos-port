# postmarketOS Port for Realme 6 (RMX2001 / nemo)

postmarketOS port for the Realme 6 (`realme-nemo`), a MediaTek Helio G90T
(MT6785) device. This repo contains the pmaports packages
(`device-realme-nemo`, `linux-realme-nemo`) and the documentation for the
build pipeline.

## Current Status

- **Kernel**: Mainline 6.16.4 based on the `mt6785-mainline` fork.
- **Boot**: Boots the mainline kernel to the initramfs and to a working
  SSH login on USB (see [docs/ssh.md](docs/ssh.md)).
- **GUI**: Phosh is installed but the display panel driver is not yet
  ported. A previous attempt at a panel patch broke the build and was
  reverted; this repo is the working baseline.
- **Install method**: TWRP recovery zip; flash the zip from TWRP on the
  device's `userdata` partition.

## Documentation

- [docs/build.md](docs/build.md) — full pmbootstrap build and install
  procedure, plus a list of device quirks and how the device and kernel
  packages are configured.
- [docs/verify.md](docs/verify.md) — boot image structure, inspection
  commands, AVB padding procedure, and a reference-image diff.
- [docs/ssh.md](docs/ssh.md) — USB networking topology and SSH access on
  the booted device.

## Quick start

```bash
# 1. Clone pmbootstrap and pmaports into pmaports-tmp/
mkdir -p pmaports-tmp
git clone --depth=1 https://gitlab.postmarketos.org/postmarketOS/pmbootstrap.git pmaports-tmp/pmbootstrap
ln -sfn "$PWD/pmaports-tmp/pmbootstrap/pmbootstrap.py" ~/.local/bin/pmbootstrap
export PATH="$HOME/.local/bin:$PATH"

git clone --depth=1 https://gitlab.postmarketos.org/postmarketOS/pmaports.git pmaports-tmp/aports
cp -a device-realme-nemo  pmaports-tmp/aports/device/testing/device-realme-nemo
cp -a linux-realme-nemo   pmaports-tmp/aports/device/testing/linux-realme-nemo

# 2. Init pmbootstrap (one-time)
pmbootstrap config work  "$PWD/pmaports-tmp/work"
pmbootstrap config aports "$PWD/pmaports-tmp/aports"
pmbootstrap config device realme-nemo
pmbootstrap config kernel realme-nemo
pmbootstrap config ui phosh
mkdir -p pmaports-tmp/work && printf '8\n' > pmaports-tmp/work/version

# 3. Build
pmbootstrap -p "$PWD/pmaports-tmp/aports" -w "$PWD/pmaports-tmp/work" build linux-realme-nemo
pmbootstrap -p "$PWD/pmaports-tmp/aports" -w "$PWD/pmaports-tmp/work" build device-realme-nemo

# 4. Produce the TWRP-flashable recovery zip
pmbootstrap -p "$PWD/pmaports-tmp/aports" -w "$PWD/pmaports-tmp/work" \
    install --android-recovery-zip \
    --no-firewall \
    --recovery-install-partition userdata \
    --password 1234
```

The output zip lands in
`pmaports-tmp/work/chroot_buildroot_aarch64/var/lib/postmarketos-android-recovery-installer/pmos-realme-nemo.zip`.
Copy it to the device, reboot into TWRP, and install.

## Repository layout

```
.
├── device-realme-nemo/   # pmaports device package
├── linux-realme-nemo/    # pmaports kernel package
├── docs/                 # build, verify, ssh
├── pmaports-tmp/         # pmbootstrap work dir, builds, recovery zip (gitignored)
└── README.md
```

`pmaports-tmp/work/` (chroots, build cache, packages) and the binary outputs in
`pmaports-tmp/notes/` (`*.img`, `*.zip`) are gitignored. The metadata in
`pmaports-tmp/notes/` (REPORT.md, verify script, diff) is tracked.
