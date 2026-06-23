# Boot image verification

After `pmbootstrap install --android-recovery-zip` you get
`pmaports-tmp/work/chroot_rootfs_realme-nemo/boot/boot.img`. The TWRP install
path does not care if the AVB footer is present or if the image is padded to
32 MiB — TWRP writes whatever bytes you give it to the boot partition. But for
direct `fastboot flash boot boot.img`, or for sanity-checking the image is the
shape the MTK bootloader expects, you need to verify it.

This document covers:

1. The structure a "correct" Realme 6 `boot.img` must have.
2. How to inspect a `boot.img` against this spec.
3. How to apply the AVB padding + footer if it's missing.
4. A reference image diff and what to expect.

For the build pipeline itself, see [build.md](build.md).
For SSH access once the device is up, see [ssh.md](ssh.md).

## 1. Required structure

A working `boot.img` is exactly **33,554,432 bytes** (32 MiB), and contains
an `mkbootimg` header v2 image followed by an AVB hash footer.

| Field | Value | Notes |
|---|---|---|
| Magic | `ANDROID!` | 8 bytes |
| Header version | 2 | |
| Page size | 2048 | |
| `kernel_addr` | `0x40080000` | |
| `ramdisk_addr` | `0x47c80000` | |
| `tags_addr` | `0x4bc80000` | |
| `kernel_size` | ~10.4 MB (gzip-compressed `vmlinuz`) | small per-build variation OK |
| `ramdisk_size` | ~14.1 MB (gzip-compressed initramfs) | small per-build variation OK |
| `recovery_dtbo` | 136 bytes | the empty DTBO our device pkg generates |
| AVB partition name | `boot` | |
| AVB Algorithm | `NONE` | matches the stock `vbmeta.img` Flags: 3 |
| AVB Image size | 33,554,432 | partition size |
| AVB VBMeta size | 512 | |
| AVB VBMeta offset | 33,554,432 − 512 = 33,553,920 | |
| AVB Hash algo | sha256 | |
| AVB Salt | 32 random bytes (different per build) | |

DTB and `recovery_dtbo` payloads must be **bit-identical** to the kernel source
you built. Their sha256 hashes are:

| Blob | Size | sha256 |
|---|---|---|
| `dtb` (`mt6785-realme-nemo.dtb`) | 41,585 B | `a340f0aa2ea190dfe822a61803934f72b4c0360a77376f3ba39879ddce1013a7` |
| `recovery_dtbo` (the `mkdtboimg`-wrapped empty DTB) | 136 B | `f72e1df52c33bde1676863a21b3e7f8c3cb9a21b8ed7addefe2ac0eb8cce0635` |

DTB model and compatible must be `Realme 6` and `realme,nemo`,
`mediatek,mt6785`.

## 2. Inspecting a `boot.img`

### Magic + header

```bash
file boot.img
# Android bootimg, kernel (0x40080000), ramdisk (0x47c80000), page size: 2048, ...
```

### Unpack

```bash
mkdir -p /tmp/boot-unpack
unpack_bootimg --boot_img boot.img --out /tmp/boot-unpack
ls -la /tmp/boot-unpack/
# drwxr-xr-x  ...  kernel
# drwxr-xr-x  ...  ramdisk
# drwxr-xr-x  ...  dtb
# drwxr-xr-x  ...  recovery_dtbo
```

### Verify DTB and recovery_dtbo

```bash
sha256sum /tmp/boot-unpack/dtb
# expect: a340f0aa2ea190dfe822a61803934f72b4c0360a77376f3ba39879ddce1013a7  /tmp/boot-unpack/dtb

sha256sum /tmp/boot-unpack/recovery_dtbo
# expect: f72e1df52c33bde1676863a21b3e7f8c3cb9a21b8ed7addefe2ac0eb8cce0635  /tmp/boot-fixed-unpack/recovery_dtbo
```

### Verify DTB model/compatible

```bash
dtc -I dtb -O dts -o /tmp/boot-unpack/dtb.dts /tmp/boot-unpack/dtb
grep -E "model|compatible" /tmp/boot-unpack/dtb.dts | head
# model = "Realme 6";
# compatible = "realme,nemo", "mediatek,mt6785";
```

### AVB footer

```bash
avbtool info_image --image boot.img
# Footer version:           1.0
# Image size:               33554432 bytes
# Original image size:      <raw_image_size>
# VBMeta offset:            33553920
# VBMeta size:              512 bytes
# --
# Minimum libavb version:   1.0
# ...
# Algorithm:                NONE
# ...
#     Hash descriptor:
#       Partition Name:        boot
#       Hash Algorithm:        sha256
```

If `avbtool info_image` errors with `Given image does not look like a vbmeta image`,
the AVB footer is missing — go to step 3.

## 3. Applying the AVB padding + footer

If you only have the raw `boot.img` from pmbootstrap (~24.6 MB, no padding, no
AVB), run:

```bash
cp boot.img boot-with-avb.img
avbtool add_hash_footer \
  --image boot-with-avb.img \
  --partition_name boot \
  --partition_size 33554432 \
  --algorithm NONE \
  --salt $(openssl rand -hex 32)
# avbtool will pad the file to 33554432 bytes and append a 512-byte VBMeta.
```

`avbtool` aligns the VBMeta to a page boundary, so the VBMeta offset may end up
slightly below `image_size - 512` (typically 2 KiB of padding between image data
and VBMeta). That's fine.

The stock `vbmeta.img` has `Flags: 3` (verification disabled), so `Algorithm: NONE`
on the boot image is correct.

## 4. Reference diff

The script `pmaports-tmp/notes/verify_bootimg.py` automates the full diff. By
default it compares against `/home/dazai/Projects/working/boot-fixed.img`. If you
have a different reference, pass its path as the argument:

```bash
python3 pmaports-tmp/notes/verify_bootimg.py /path/to/your/boot-fixed.img
```

The script prints a side-by-side comparison of all header fields, DTB and
`recovery_dtbo` sha256s, and the AVB footer. See
`pmaports-tmp/notes/verify_report.txt` for a real example run.

Expected diff (raw pmbootstrap output vs. AVB-padded reference):

| Field | Reference | pmbootstrap raw | Notes |
|---|---|---|---|
| File size | 33,554,432 B | 24,623,104 B | raw lacks AVB padding; fix with step 3 |
| Magic | `ANDROID!` | `ANDROID!` | match |
| Header version | 2 | 2 | match |
| Page size | 2048 | 2048 | match |
| `kernel_addr` | 0x40080000 | 0x40080000 | match |
| `ramdisk_addr` | 0x47c80000 | 0x47c80000 | match |
| `tags_addr` | 0x4bc80000 | 0x4bc80000 | match |
| `dtb_addr` | 0x4bc80000 | 0x41f00000 | differs if `--recovery_dtbo` is in use; both layouts are valid |
| `dtb` sha256 | `a340f0aa…` | `a340f0aa…` | **bit-identical** |
| `recovery_dtbo` sha256 | `f72e1df5…` | `f72e1df5…` | **bit-identical** |
| DTB model | `Realme 6` | `Realme 6` | match |
| AVB | present, Algorithm=NONE | absent | run step 3 |
| cmdline | 72 chars | 142 chars | disto adds `quiet splash plymouth.*`; OK in practice (TWRP works) |
