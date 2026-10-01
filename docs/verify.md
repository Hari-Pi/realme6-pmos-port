# Verify the recovery artifact

```sh
python3 scripts/verify-recovery.py dist/pmos-realme-nemo.zip \
    --report dist/verification.json
sha256sum -c dist/SHA256SUMS
```

The verifier reads the actual rootfs tar inside the zip, rather than trusting
a separate image or historical reference. It checks zip CRCs, the recovery
entrypoint, `INSTALL_PARTITION='userdata'`, kernel flashing enabled and FDE off,
absence of stale root/boot UUIDs in fstab and the UID-10000 `user` account. It validates:

| Boot field | Required value |
| --- | --- |
| Android magic / header / page size | `ANDROID!` / 2 / 2048 |
| Kernel address | `0x40080000` |
| Ramdisk address | `0x47c80000` |
| Tags and DTB address | `0x4bc80000` |
| Android OS / patch fields | 10.0.0 / 2021-08 |
| Boot partition image size | 33,554,432 bytes |
| AVB partition / algorithm | boot / NONE |
| AVB hash | SHA-256 over salt + original image, independently recomputed |
| Command line | MTK bootopt, no splash, at most 93 characters |
| Device tree | Realme 6 / realme,nemo, identical to packaged board DTB |
| Recovery DTBO | DTBO table, identical to packaged empty.dtbo |

Offsets in deviceinfo are relative to `0x40078000`. Their sums match the
working Droidian port's absolute addresses. The DTB offset is supplied
explicitly in custom mkbootimg arguments: setting custom arguments suppresses
boot-deploy's normal DTB/header argument generation.

The AVB footer lives at the image's last 64 bytes. Its VBMeta offset and size
are parsed from the footer and bounds-checked; they are not assumed to be fixed
at `partition_size - 512`. An unsigned `NONE` image requires an unlocked,
verification-disabled boot chain. TWRP does not exempt the image from the
bootloader's checks.

The finalization hook runs `avbtool verify_image` during image creation. The
archive verifier repeats the hash check independently after packaging.

Archive validation cannot prove a hardware boot. After installation, confirm
USB SSH, `uname -a`, root and boot mounts, storage visibility, logs and repeated
reboots. Save the results beside the artifact before calling it hardware-tested.
The report leaves `hardware_boot_tested` false until that separate test occurs.
