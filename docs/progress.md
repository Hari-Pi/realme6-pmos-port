# postmarketOS Realme 6 (nemo) Progress

## Goal
Boot postmarketOS with Phosh on Realme 6 (RMX2001, codename `nemo`, MT6785 Helio G90T) from a TWRP-flashable recovery zip.

## Device Info
- **SoC**: Mediatek MT6785 (Helio G90T)
- **Boot partition**: `/dev/block/sdc43` (32 MB)
- **Userdata partition**: `/dev/block/sdc51` (~111 GB)
- **No physical system partition** — uses `super` for dynamic partitions (Android 11+)
- **Bootloader**: Mediatek LK (Little Kernel) with AVB (Android Verified Boot) enforcement
- **Recovery**: TWRP with ADB

## Key Constraints Discovered

### 1. AVB Footer Required
The MTK bootloader enforces AVB — boot.img must have an AVB footer. `--algorithm NONE` works but requires `--salt` (bare `--algorithm NONE` fails with `'NoneType' object has no attribute 'encode'`).

```bash
avbtool add_hash_footer --image boot.img --partition_name boot \
  --partition_size 33554432 --algorithm NONE \
  --salt $(openssl rand -hex 32)
```

### 2. Kernel Cmdline Length Limit (MTK Bootloader Overflow)
The MTK bootloader (LK) has a tight limit on kernel cmdline length. Overflow causes `cmdline overflow` error and boot abort.
- 93 chars: overflow
- 67 chars: overflow
- 76 chars: **works** (proven with SXMO build)
- 39-42 chars: no overflow

**Hypothesis**: The limit is somewhere between 67 and 76 chars, or `pmos.debug-shell` triggers the overflow specifically. Needs more testing.

Proven working cmdline (76 chars):
```
bootopt=64S3,32N2,64N2 androidboot.serialconsole=0 gpt=1 loop.max_part=7 rw
```

### 3. MBR Partition Table on Userdata (Single-Partition Bug)
The pmOS recovery installer creates an MBR on `/dev/block/sdc51` (userdata) with two sub-partitions:
- Partition 1: LBA 2048–62463 (~30 MB, vfat boot)
- Partition 2: LBA 62464+ (~6.5 GB, f2fs root)

**Bug**: If both `kpartx` and `losetup` fail in the installer, it falls back to "single partition mode" where `PMOS_BOOT = ROOT_PARTITION = INSTALL_DEVICE`. Running `mkfs.f2fs` on the entire sdc51 **overwrites the MBR** created by `parted`, corrupting the partition table.

**Fix applied**: Modified `partition_install_device()` in `pmos_install_functions` to:
1. Create loop device nodes explicitly (`mknod /dev/loop0`, `/dev/loop1`)
2. Use `losetup` with explicit device names instead of `-f`
3. Remove the single-partition fallback — exit with error instead

### 4. kpartx Works in TWRP
Device-mapper kernel support IS available in TWRP. In the latest successful install, kpartx created `/dev/mapper/sdc51p1` and `/dev/mapper/sdc51p2` correctly. The previous failures were caused by `INSTALL_PARTITION=system` not being found (no system partition on this device), causing the entire installer to fail.

## Installation Flow
1. Update-binary script extracts chroot and sets up environment
2. `extract_partition_table()` finds userdata at `/dev/block/sdc51`
3. `partition_install_device()` creates MBR with parted + runs kpartx
4. `set_subpartitions()` sets `PMOS_BOOT` and `ROOT_PARTITION`
5. Root partition formatted as f2fs with label `pmOS_root`
6. Boot partition formatted as vfat with label `pmOS_boot`
7. Rootfs.tar.gz extracted to `/mnt/pmOS`
8. boot.img flashed from rootfs to boot partition (`dd` to sdc43)

## Current Status

### What Works
- TWRP zip installation (MBR created, rootfs extracted, boot.img flashed)
- kpartx creates sub-partitions correctly
- MBR partition table is valid (checked via `dd` + hex dump)
- AVB footer correctly applied (verified with `avbtool info_image`)

### What Doesn't
- **Device bootloops** after every installation attempt — kernel fails to start or panics immediately
- Cannot get boot messages via UART (no serial console output observed)
- pstore/ramoops logs only capture TWRP's kernel, not our mainline kernel's output

### Latest Attempt
- **Zip**: `/tmp/pmos-realme-nemo-sxmo-cmdline.zip`
- **Boot.img cmdline**: 76 chars (SXMO-proven, no `pmos.debug-shell`)
- **Installation**: Passed all steps (MBR, kpartx, mkfs, rootfs, boot.img flash)
- **Result**: Bootloop

## Open Questions
1. Why does SXMO boot.img with the same cmdline boot the kernel, but our phosh boot.img doesn't?
2. Is the bootloop a kernel panic, initramfs failure, bootloader rejection, or cmdline overflow?
3. How to get kernel boot logs without UART (different ramoops address?)
4. Is the boot.img header structure correct for MTK's bootloader?

## Tested Zips (chronological order)

| Zip | Cmdline | Result |
|-----|---------|--------|
| `pmos-realme-nemo.zip` (original SXMO) | 76 chars, SXMO kernel | Booted to `init: Starting service 'udc'` |
| `pmos-realme-nemo-avb.zip` (phosh v1) | 93 chars (+`pmos.debug-shell`) | cmdline overflow |
| `pmos-realme-nemo-avb-v2.zip` | 67 chars (dropped `gpt=1 loop.max_part=7 rw`) | cmdline overflow |
| `pmos-realme-nemo-avb-v3.zip` | 39 chars (dropped `androidboot.serialconsole=0`) | No overflow, MBR wipe -> bootloop |
| `pmos-realme-nemo-avb-final.zip` | 42 chars (+`rw`) | No overflow, MBR wipe -> bootloop |
| `pmos-realme-nemo-sxmo-cmdline.zip` | 76 chars (SXMO cmdline) | Install OK, MBR OK, still bootloop |

## Key Files
- `/home/dazai/Projects/PMOS/device-realme-nemo/deviceinfo` — device config
- `/tmp/pmos-realme-nemo.zip` — original SXMO zip (795 MB)
- `/tmp/pmos-realme-nemo-sxmo-cmdline.zip` — latest test zip (737 MB)
- `/tmp/phosh-sxmo-cmdline-boot-avb.img` — latest boot.img (32 MB, AVB)
- `/home/dazai/.local/var/pmbootstrap/chroot_rootfs_realme-nemo/boot/boot.img` — chroot source boot.img
- `/tmp/pmos_scripts/pmos_install_functions` — fixed installer script
- `cmdline_overflow.md` — cmdline length documentation
- `avb.md` — AVB footer patch instructions
