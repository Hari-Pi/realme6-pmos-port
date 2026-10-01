# Recovery build audit — 2026-09-28

The first deliverable is a recovery-installable mainline postmarketOS image.
The working Droidian port is the hardware and boot-layout reference.

## Official sources examined

- [pmbootstrap installation](https://docs.postmarketos.org/pmbootstrap/main/installation.html): Linux host requirements; WSL is unofficial.
- [pmbootstrap usage](https://docs.postmarketos.org/pmbootstrap/main/usage.html): install, recovery zip, export, checksums, configuration and root opt-in.
- [Deviceinfo schema](https://gitlab.postmarketos.org/postmarketOS/pmaports/-/blob/main/deviceinfo_schema.toml): UFS sector size, custom boot arguments and supported postprocessing hook.
- [Kernel command-line packaging](https://gitlab.postmarketos.org/postmarketOS/pmaports/-/blob/main/docs/packaging/kernel-packages/kernel-cmdline.md): one parameter per line and `-` removal directives.
- [Kernel configuration checks](https://gitlab.postmarketos.org/postmarketOS/pmaports/-/blob/main/docs/packaging/kernel-packages/kconfigcheck.md): default boot requirements and community promotion checks.
- [pmbootstrap recovery implementation](https://gitlab.postmarketos.org/postmarketOS/pmbootstrap/-/blob/main/pmb/install/recovery.py): config options, home exclusion, tar creation and zip creation order.
- [Recovery installer](https://gitlab.com/postmarketOS/postmarketos-android-recovery-installer): partition lookup, MBR subpartitions, ext2/ext4, boot writing and skel home creation; installed package version is determined by the pinned pmaports recipe.
- [boot-deploy](https://gitlab.postmarketos.org/postmarketOS/boot-deploy): custom args bypass normal DTB arguments; postprocess runs after mkbootimg, before copying/flashing.
- [MT6785 sibling port](https://wiki.postmarketos.org/wiki/Xiaomi_Redmi_Note_8_Pro_(xiaomi-begonia)): recovery zip flow and MediaTek mainline context. Its deviceinfo source was also compared.

Some wiki pages deny automated access. Current checked-out official source and
its documentation are the primary evidence for implementation details. Source
revisions are recorded in `build.lock.json`; links above may move with main.

## Corrections

| Gap | Resolution |
| --- | --- |
| Realme DTS fix existed only in ignored historical build copy | Include/copy/checksum DTS in authoritative kernel APKBUILD |
| Global pmbootstrap settings and manually primed work version | Isolated helper config; work version read from pinned tool |
| Recovery target easy to omit | Helper always passes userdata explicitly |
| AVB described as optional for TWRP | Finalize and verify boot inside zip via supported postprocess |
| DTB load address not passed with custom args | Explicit dtb_offset; match validated Droidian layout |
| Android header fields missing | OS 10.0.0 and patch 2021-08 from validated Droidian config |
| Command-line docs inconsistent | One parameter per line, remove splash; verify final length |
| f2fs/vfat description differed from installer | Document actual ext4 root and ext2 boot |
| Fixed historical DTB hash/size treated as universal | Compare embedded blobs against this artifact's packaged blobs |
| Missing root-owned WSL build dependencies | Install host prerequisites and verify chroot/emulation |
| Historical verifier depended on an unavailable local reference | Standalone zip verifier with independent AVB hash check |
| Default kernel requirements failed | Enable SYN cookies, NLS ASCII, module zstd/decompression, BPF LSM/BTF, DWARF5, probes and path security; add pahole; require default kconfig check |
| Console UI does not pull in the phone USB-mode packages | Install USB mode manager and developer profile explicitly |

## Droidian evidence

[debian/kernel-info.mk](https://github.com/Hari-Pi/kernel_realme_RMX2001/blob/droidian/debian/kernel-info.mk)
provides the 32 MiB boot partition, header version 2, 2048 page size, base/offset
values, Android OS and patch fields, and A-only device facts.
[AVB-FOOTER-FIX.md](https://github.com/Hari-Pi/kernel_realme_RMX2001/blob/droidian/helpers/AVB-FOOTER-FIX.md)
records three successful real-device reboots after fixing those fields.
[KERNEL-BUILD-AND-TEST.md](https://github.com/Hari-Pi/kernel_realme_RMX2001/blob/droidian/helpers/KERNEL-BUILD-AND-TEST.md)
provides the package audit and hardware-validation procedure. The local Droidian
checkout contains unrelated edits, which were preserved.

The downstream kernel's appended DTB, Droidian cmdline, Android HAL services
and adaptation package are not transferred blindly to mainline. The existing
pmOS board DTS and MT6785 fork remain our mainline baseline. Kernel config
includes built-in UFS, MTK UFS PHY, dual-role USB and ext4 with ext2 support;
default initramfs module rules include loop, dm-crypt and USB network functions.

This remains a testing-category device. The old APKBUILD claimed community
configuration checks despite failing them. That opt-in is removed while the
mandatory default checks are fixed and enforced in the helper. Community
promotion (additional netmount, accessibility, container and hardening configs)
is a later milestone, not silently claimed by this package.

## Remaining hardware work

Verify this new zip in the installed TWRP version and boot it on the Realme 6.
Confirm userdata/boot labels, the actual verification-disabled boot chain,
USB enumeration and SSH, mounts, charging and stable reboots. Display, touch,
Wi-Fi and other hardware remain separate porting milestones. A build that
passes static verification is an untested artifact, not a validated release.
