# postmarketOS Realme 6 build — final report

## What was built
- `pmbootstrap` 3.10.1 (cloned into `pmaports-tmp/pmbootstrap`, symlinked at `~/.local/bin/pmbootstrap`).
- `pmaports` shallow clone at `pmaports-tmp/aports`, with `device-realme-nemo/` and `linux-realme-nemo/` overlaid.
- Fresh work dir at `pmaports-tmp/work/` (zap-and-rebuild each run; old `~/.local/var/pmbootstrap/` was left alone).
- Kernel: `linux-realme-nemo-6.16.4-r0.apk` (20.5 MB) — built cross-native for aarch64.
- Device: `device-realme-nemo-2-r0.apk` (3 KB) — built via crossdirect.
- TWRP-flashable recovery zip: `pmaports-tmp/notes/pmos-realme-nemo.zip` (**759 MB**) — produced by
  `pmbootstrap install --android-recovery-zip --no-firewall --recovery-install-partition userdata`.

## Fix that was needed (in temp copy only)
The kernel APKBUILD shipped in the repo had a wrong assumption: the prepare() function's comment claimed `mt6785-realme-nemo.dts` is "already in the kernel source tree", but it isn't. The gitlab tarball does not contain it. The fix was applied **only** in `pmaports-tmp/aports/device/testing/linux-realme-nemo/APKBUILD` (i.e. the copy inside the temp folder, not the original in the repo):
- Added `mt6785-realme-nemo.dts` to the `source=` list.
- `prepare()` now `install -D`'s it into `arch/arm64/boot/dts/mediatek/`.
- Added the matching `sha512sum` entry.

The original `/linux-realme-nemo/APKBUILD` was not modified. See `diff_apkbuild.txt` for the side-by-side.

## Partition fix
The device has no `system` partition — it uses Android's `super` (dynamic partitions) on Android 11+. The default `pmbootstrap install --android-recovery-zip` writes `INSTALL_PARTITION='system'` into the zip's `install_options`, which doesn't exist on this device. The historical working zips used `INSTALL_PARTITION='userdata'`.

pmbootstrap does **not** expose a `deviceinfo_recovery_install_partition` key — the partition is purely a CLI flag (`--recovery-install-partition`). The fix is to always pass it:

```bash
pmbootstrap ... install --android-recovery-zip \
    --no-firewall \
    --recovery-install-partition userdata
```

Diff between the broken (first) and fixed (current) zip's `chroot/install_options`:
```diff
-INSTALL_PARTITION='system'
+INSTALL_PARTITION='userdata'
```

All other fields (`SYSTEM_PARTLABEL='userdata'`, `KERNEL_PARTLABEL='boot'`, etc.) were already correct.

## Where everything lives

| Path | What |
|---|---|
| `pmaports-tmp/notes/pmos-realme-nemo.zip` | TWRP-flashable zip (759 MB) — what you flash via TWRP |
| `pmaports-tmp/notes/boot-produced.img` | Raw `boot.img` extracted from the chroot (24.6 MB) — confirmed boots on the device |
| `pmaports-tmp/notes/boot-produced-avb.img` | Same image, padded to 32 MiB + AVB footer (32 MB) |
| `pmaports-tmp/notes/verify_report.txt` | Full diff against `/home/dazai/Projects/working/boot-fixed.img` |
| `pmaports-tmp/notes/verify_bootimg.py` | Verification script (re-runnable) |
| `pmaports-tmp/work/packages/edge/aarch64/` | Built `.apk` files |

## Boot-image verification — TL;DR

`verify_report.txt` has the full diff. Headline:

| Metric | Reference (`boot-fixed.img`) | Produced (`boot-produced.img`) | Match? |
|---|---|---|---|
| File size (raw) | 33,554,432 B | 24,623,104 B | **no** (raw isn't padded; AVB-padded version is 33,554,432 B) |
| Magic | `ANDROID!` | `ANDROID!` | yes |
| Header version | 2 | 2 | yes |
| Page size | 2048 | 2048 | yes |
| kernel_addr | 0x40080000 | 0x40080000 | yes |
| ramdisk_addr | 0x47c80000 | 0x47c80000 | yes |
| tags_addr | 0x4bc80000 | 0x4bc80000 | yes |
| dtb_addr | 0x4bc80000 | 0x41f00000 | **no** (depends on second/empty.dtbo placement; both layouts work) |
| **dtb sha256** | `a340f0aa2ea190df…` | `a340f0aa2ea190df…` | **YES (bit-identical)** |
| **recovery_dtbo sha256** | `f72e1df5…` | `f72e1df5…` | **YES (bit-identical)** |
| DTB model | `Realme 6` | `Realme 6` | yes |
| DTB compatible | `realme,nemo` | `realme,nemo` | yes |
| cmdline length | 72 chars | 142 chars | **NO** (phosh+distro additions) |
| cmdline content | `bootopt=…gpt=1 loop.max_part=7 rw pmos_rootfsopts=defaults` | `quiet splash plymouth.ignore-serial-consoles plymouth.prefer-fbcon bootopt=…androidboot.serialconsole=0 gpt=1 loop.max_part=7 rw` | no |
| AVB footer | present, Algorithm=NONE, 32 MiB, partition=boot | **absent on raw**; **present on `boot-produced-avb.img`** | no (raw); yes (AVB-padded) |
| **Boots on device?** | yes (you confirmed historical) | **yes (you confirmed)** | — |

## Reproducing
```bash
cd /home/dazai/Projects/fresh/realme6-pmos-port
export PATH="$HOME/.local/bin:$PATH"

# (only needed on a clean tree; everything is already built)
pmbootstrap -p "$PWD/pmaports-tmp/aports" -w "$PWD/pmaports-tmp/work" build linux-realme-nemo
pmbootstrap -p "$PWD/pmaports-tmp/aports" -w "$PWD/pmaports-tmp/work" build device-realme-nemo

# Always pass --recovery-install-partition userdata — the device has no system partition.
pmbootstrap -p "$PWD/pmaports-tmp/aports" -w "$PWD/pmaports-tmp/work" \
    install --android-recovery-zip \
    --no-firewall \
    --recovery-install-partition userdata \
    --password changeme

# Re-verify
python3 pmaports-tmp/notes/verify_bootimg.py
```

## What was NOT done
- Original `device-realme-nemo/` and `linux-realme-nemo/` in this repo are untouched.
- No git operations in the repo (no pull/push/checkout/reset/switch).
- No flashing; no TWRP interaction.
- The kconfig-community warnings (~100 of them) were not fixed — they're not blockers for the build, just required for a future `community`-category promotion.
- No automated AVB-padding step in the device APKBUILD — the TWRP zip's `boot.img` is the raw 24.6 MB image. If you want the zip itself to be directly flashable via fastboot (without TWRP), the device APKBUILD's `package()` would need a `avbtool add_hash_footer` post-step. (Not needed for the TWRP install path you used.)
