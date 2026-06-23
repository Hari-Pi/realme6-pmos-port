# Building postmarketOS for the Realme 6 (nemo)

This is the working build flow as of this repo. It uses `pmbootstrap` to produce a
TWRP-flashable recovery zip. Everything is reproducible from this repo + a Linux host.

For the boot image verification procedure, see [verify.md](verify.md).
For SSH access on the booted device, see [ssh.md](ssh.md).

## 1. Host prerequisites

- Linux (x86_64, aarch64, armv7), kernel 3.17+
- Python 3.10+
- `git`, `openssl`, `tar`, `ps`, `sudo` (or doas)
- Network access to `gitlab.postmarketos.org`, `gitlab.com`, and `dl-cdn.alpinelinux.org`
- For verification: `avbtool`, `mkbootimg`, `unpack_bootimg`, `dtc` (Alpine package
  `android-tools` and `dtc`)

The first build downloads ~250 MB of Alpine packages and ~1 GB of kernel source
(plus all `pmaports` build deps). A full cold build of `linux-realme-nemo` takes
~10–15 min on a recent x86_64 host; `device-realme-nemo` is trivial.

## 2. Layout

The build artifacts live in `pmaports-tmp/` next to this repo's tracked files:

```
realme6-pmos-port/
├── device-realme-nemo/        # tracked device pkg (pmaports-format)
├── linux-realme-nemo/         # tracked kernel pkg (pmaports-format)
├── docs/
│   ├── build.md               # this file
│   ├── verify.md              # boot image verification
│   └── ssh.md                 # SSH access on the device
├── pmaports-tmp/
│   ├── pmbootstrap/           # shallow clone of gitlab.postmarketos.org/postmarketOS/pmbootstrap
│   ├── aports/                # shallow clone of gitlab.postmarketos.org/postmarketOS/pmaports,
│   │                          #   with our device/ and linux/ packages overlaid
│   ├── work/                  # pmbootstrap's work dir (chroots, packages, cache) — gitignored
│   └── notes/                 # build outputs, verification, REPORT.md — .img/.zip gitignored
├── .gitignore
└── README.md
```

`pmaports-tmp/work/` and the binary outputs in `pmaports-tmp/notes/` are gitignored
(see `.gitignore`). The metadata in `pmaports-tmp/notes/` (REPORT, verify script,
diff, verify report) is tracked.

## 3. Set up pmbootstrap

```bash
cd /path/to/realme6-pmos-port
mkdir -p pmaports-tmp
git clone --depth=1 https://gitlab.postmarketos.org/postmarketOS/pmbootstrap.git pmaports-tmp/pmbootstrap
ln -sfn "$PWD/pmaports-tmp/pmbootstrap/pmbootstrap.py" ~/.local/bin/pmbootstrap
export PATH="$HOME/.local/bin:$PATH"
pmbootstrap --version    # 3.10.1+
```

`pmbootstrap` lives in the temp folder and is *not* tracked. The symlink at
`~/.local/bin/pmbootstrap` is outside the repo.

## 4. Set up local pmaports

```bash
git clone --depth=1 https://gitlab.postmarketos.org/postmarketOS/pmaports.git pmaports-tmp/aports
cp -a device-realme-nemo  pmaports-tmp/aports/device/testing/device-realme-nemo
cp -a linux-realme-nemo   pmaports-tmp/aports/device/testing/linux-realme-nemo
```

The two tracked packages are overlays on top of the upstream `pmaports` tree.
They are not `git submodule`s — they're just plain `cp -a` copies that happen to
sit inside the aports tree.

## 5. Init pmbootstrap

Either run the wizard non-interactively, or write the config directly:

```bash
pmbootstrap config work  "$PWD/pmaports-tmp/work"
pmbootstrap config aports "$PWD/pmaports-tmp/aports"
pmbootstrap config device realme-nemo
pmbootstrap config kernel realme-nemo
pmbootstrap config ui phosh
# Optional: pre-select extra pkgs (none for now)
pmbootstrap config extra_packages ""
```

Then prime the work dir's version file (pmbootstrap 3.10.x refuses to start in an
empty work dir without it):

```bash
mkdir -p pmaports-tmp/work
printf '8\n' > pmaports-tmp/work/version
```

Verify:

```bash
pmbootstrap -p "$PWD/pmaports-tmp/aports" -w "$PWD/pmaports-tmp/work" status
# Channel: systemd-edge (pmaports: main, dirty)
# Device:  realme-nemo (aarch64)
# UI:      phosh
# systemd: yes
```

The `dirty` marker is expected — our overlaid packages are not committed in the
`pmaports` clone.

## 6. Build the kernel and device packages

```bash
pmbootstrap -p "$PWD/pmaports-tmp/aports" -w "$PWD/pmaports-tmp/work" \
    build linux-realme-nemo

pmbootstrap -p "$PWD/pmaports-tmp/aports" -w "$PWD/pmaports-tmp/work" \
    build device-realme-nemo
```

`pmbootstrap build linux-realme-nemo` is the long step (~10–15 min cold; seconds
warm thanks to ccache). It cross-compiles the kernel for aarch64 with
`aarch64-alpine-linux-musl-gcc`.

`pmbootstrap build device-realme-nemo` is fast — it runs `devicepkg_build` plus
the `dtc` + `mkdtboimg create empty.dtbo` step (see quirk #4 below).

`pmbootstrap kconfig check linux-realme-nemo` will fail with ~100 warnings — those
are the `community` category kconfig requirements (hardening, filesystems,
netmount, etc.). They are *not* build blockers, only CI/promotion blockers. The
device currently lives in the `testing` category; fixing them is a prerequisite
for promoting to `community`.

## 7. Generate the TWRP-flashable recovery zip

```bash
pmbootstrap -p "$PWD/pmaports-tmp/aports" -w "$PWD/pmaports-tmp/work" \
    install --android-recovery-zip \
    --no-firewall \
    --recovery-install-partition userdata \
    --password 1234
```

Flags explained:

- `--android-recovery-zip` — produce a TWRP-flashable zip instead of a raw image.
- `--no-firewall` — drop the phosh default nftables rules (port 22 etc).
- `--recovery-install-partition userdata` — **required**, see quirk #5. The
  Realme 6 has no `system` partition (uses `super` / dynamic partitions), so the
  recovery installer must target `userdata`.
- `--password 1234` — sets the `user` account password baked into the chroot's
  `/etc/shadow`. Replace with anything you like (kept secret — it lands in
  pmbootstrap's log).

The output zip lands at:

```
pmaports-tmp/work/chroot_buildroot_aarch64/var/lib/postmarketos-android-recovery-installer/pmos-realme-nemo.zip
```

The produced `boot.img` is at:

```
pmaports-tmp/work/chroot_rootfs_realme-nemo/boot/boot.img
```

(Copies of both are also in `pmaports-tmp/notes/`, minus the binary artifacts
which are gitignored.)

## 8. Flash

Copy `pmos-realme-nemo.zip` to the device, reboot into TWRP, and install the zip.
TWRP runs the bundled `pmos_install` script which:

1. Reads `chroot/install_options` (the file pmbootstrap embeds with our partition
   choice).
2. Creates an MBR on `userdata` with a small `pmOS_boot` (vfat) and a large
   `pmOS_root` (f2fs).
3. Extracts the rootfs tarball into `pmOS_root`.
4. Flashes the bundled `boot.img` to the boot partition.

After TWRP finishes, reboot. The kernel + initramfs take over from there.

## Device quirks (why the device pkg and kernel pkg look the way they do)

### 1. `mt6785-realme-nemo.dts` is not in the upstream kernel tarball

The kernel source is the `mt6785-mainline` fork at
`https://gitlab.postmarketos.org/mt6785-mainline/linux/-/archive/6.16.4-r0/`.
It contains `mt6785.dtsi` and `mt6785-xiaomi-begonia.dts` but not the Realme
6 DTS. The kernel APKBUILD needs to:

- Add `mt6785-realme-nemo.dts` to `source=` with a matching sha512sum.
- In `prepare()`, install it into `arch/arm64/boot/dts/mediatek/` and patch
  the Makefile to add `dtb-$(CONFIG_ARCH_MEDIATEK) += mt6785-realme-nemo.dtb`
  after the `mt6785-xiaomi-begonia.dtb` line.

If the DTS is missing from the source tree, the kernel build fails with
`No rule to make target 'arch/arm64/boot/dts/mediatek/mt6785-realme-nemo.dtb'`.

### 2. AVB footer on `boot.img`

The MediaTek LK bootloader on this device requires an AVB hash footer on
`boot.img`. The flash partition is exactly 32 MiB
(`33554432` bytes). pmbootstrap's `mkbootimg` does not add this automatically; we
add it as a post-step:

```bash
avbtool add_hash_footer \
  --image boot.img \
  --partition_name boot \
  --partition_size 33554432 \
  --algorithm NONE \
  --salt $(openssl rand -hex 32)
```

Algorithm `NONE` is enough — the stock ROM's `vbmeta.img` already has verification
disabled (`Flags: 3`). The TWRP recovery zip path also works without AVB padding
because TWRP itself writes to the partition; you only need AVB padding for
direct fastboot / dd flashing. See [verify.md](verify.md) for the full procedure.

### 3. Kernel cmdline length

The MediaTek LK bootloader panics with `cmdline overflow` if the kernel command
line is > ~93 chars. pmbootstrap's phosh base adds
`quiet splash plymouth.ignore-serial-consoles plymouth.prefer-fbcon` (~52 chars)
to the distro's default cmdline. Our device's `kernel-cmdline.conf` has 76 chars
of its own plus the disto's additions, which is right at the limit. The original
SXMO build had 76 chars without phosh's plymouth args, which works comfortably.

If you switch to a non-phosh UI (e.g. sxmo) or strip plymouth, the cmdline is
fine as-is.

### 4. Empty DTBO is required

`mkbootimg` on this device needs a `--recovery_dtbo` arg, even when the DTBO
is empty. The device APKBUILD's `build()` step generates one:

```sh
echo '/dts-v1/;/{};' | dtc -I dts -O dtb -o "$builddir/empty.dtb"
mkdtboimg create "$builddir/empty.dtbo" "$builddir/empty.dtb"
```

If the empty DTBO is missing, the bootloader refuses to load `boot.img`.

### 5. Recovery zip targets `userdata`, not `system`

The Realme 6 has no `system` partition; storage uses Android's `super`
(dynamic partitions). pmbootstrap's default recovery target is `system`,
which doesn't exist on this device. Pass
`--recovery-install-partition userdata` to install to the correct partition.
The flag isn't exposed via `deviceinfo_*`; it has to be passed on the
command line.

The historical working TWRP zips targeted `/dev/block/sdc51` (userdata). The
pmbootstrap-generated installer's `pmos_install_part` script will find
`userdata` automatically given this option.

### 6. `deviceinfo_flash_method=fastboot` (not used here)

`deviceinfo` says `flash_method=fastboot` because the original porting effort
planned to use `pmbootstrap flasher`. We're not using fastboot at all — the TWRP
path is what works. The `flash_method` field is irrelevant for
`--android-recovery-zip` and can be ignored.

## Verification

See [verify.md](verify.md) for the full procedure: header checks, AVB inspection,
DTB / `recovery_dtbo` comparison against the known-good reference.

The provided script `pmaports-tmp/notes/verify_bootimg.py` automates the diff
against a reference image. It expects a reference at
`/home/dazai/Projects/working/boot-fixed.img`; point it elsewhere if you keep
your own reference.
