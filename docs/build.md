# Recovery build

## Host

Use Linux with Python 3.10+, git, openssl, sudo, mount, losetup and kpartx.
pmbootstrap builds Alpine chroots; don't run it directly on macOS.
Ubuntu WSL2 on the rig is our current build host. WSL is not officially
supported by pmbootstrap, so a normal Linux host is the fallback if chroot,
loop-device or emulation support fails.

On recent Ubuntu:

```sh
sudo apt-get update
sudo apt-get install git python3 openssl sudo kpartx binfmt-support qemu-user-binfmt
```

Some older distributions call the emulation package `qemu-user-static`.
pmbootstrap also installs/checks its own binfmt handlers. The build host needs
network access to GitLab, Alpine and postmarketOS mirrors and several GB of
disk space. Prefer the Linux filesystem under WSL, not `/mnt/c` or `/mnt/d`.

## One command

```sh
python3 scripts/build-recovery.py --jobs 12
```

## Live build monitor

Enable the read-only dashboard on the rig once:

```sh
sudo install -m 644 ops/pmos-build-dashboard.service \
    /etc/systemd/system/pmos-build-dashboard.service
sudo systemctl enable --now pmos-build-dashboard.service
```

Open `http://rig:8765` from the Mac on the same network or tailnet. The server
reads the build helper's `pmaports-tmp/build-dashboard/build.log` and status
file, then refreshes the browser view while a build runs. A build started with
`build-recovery.py` replaces those latest-run files and captures its output and
start/end status automatically. Progress while compiling is an estimate based
on compiler output; completion and failure are reported from the build result.
Every successful recovery package is also copied to `dist/builds/<timestamp>/`
with its verification report, manifest, source lock and checksum. The dashboard
lists these builds newest first and serves the selected ZIP for download.
ZIP responses include a stable timestamped filename, `Content-Length`, and HTTP
byte-range support, so browser downloads and resumable CLI clients such as
`aria2c` can use the same link. Right-click the dashboard's **Download ZIP**
link to copy its direct URL.
The page is read-only and is intended for access over the trusted home LAN or
Tailscale network.

The helper uses an isolated config, work directory and upstream checkouts under
`pmaports-tmp/`; it does not change your global pmbootstrap configuration. Normal
users need sudo. A dedicated root-owned WSL build directory uses pmbootstrap's
explicit `--as-root` option, keeping root-owned files away from other projects.
The current rig checkout is `/opt/realme6-pmos/port`.

The build selects edge + OpenRC by default, device `realme-nemo`, kernel `realme-nemo`,
console UI, hostname `realme-nemo`, and login `user`. It explicitly installs
the USB mode manager and developer profile so networking does not rely on
Phosh pulling those packages in. It verifies package source checksums,
builds the kernel and device APKs, and runs:

```sh
pmbootstrap -c pmaports-tmp/pmbootstrap.cfg install \
    --android-recovery-zip --recovery-install-partition userdata --no-firewall
```

The helper handles `--as-root` when applicable. It deliberately enables SSH and
disables the image firewall for USB bring-up. Revisit firewall policy before
exposing network services beyond the development connection.

OpenRC is intentional for the downstream vendor kernel. Current systemd 262
requires a Linux 5.14 baseline and no longer supports the legacy cgroup-v1
configuration used by this 4.14 kernel. A systemd image remains available for
mainline-kernel testing with `--service-manager systemd`.

The recovery installer excludes `/home` and recreates it from `/etc/skel`.
pmbootstrap's native key-copy code applies to disk images, not recovery zips.
`--ssh-key` therefore seeds `/etc/skel/.ssh/authorized_keys` before the install,
then checks the key inside the archive. Only a public key is accepted.

## Boot image generation

The device package generates an empty recovery DTBO and installs its board
settings and command-line fragment. The kernel package explicitly installs
the local Realme DTS, then enables its DTB in the MediaTek Makefile.

boot-deploy generates a header-v2 image with the Droidian-validated absolute
kernel/ramdisk/tags/DTB load addresses, Android 10.0.0 and patch level 2021-08.
The supported `deviceinfo_mkinitfs_postprocess` hook adds an AVB hash footer
for the 33,554,432-byte boot partition **before** rootfs tar/zip creation or
kernel updates. The image therefore carries its footer inside the recovery zip.

The console build removes quiet/splash/Plymouth parameters, keeping the
historically reported command-line budget below 93 characters. The verifier
checks the final generated command line, including boot-deploy additions.
That historical budget is a conservative check, not a proven universal LK limit.
The Android-only `androidboot.serialconsole=0` is omitted, matching the shorter
historical mainline reference and leaving room for `pmos_rootfsopts=defaults`.

## What recovery does

The pinned recovery-installer package resolves `PARTLABEL=userdata` and
`PARTLABEL=boot`, with recovery-fstab fallback. It writes an MBR **inside the
userdata partition**, a roughly 256 MB ext2 `pmOS_boot` subpartition and an ext4
`pmOS_root` subpartition. It maps them using kpartx, extracts the rootfs, creates
the user home from `/etc/skel`, then writes `/boot/boot.img` to boot.

This replaces all contents of userdata. The top-level Android partition table,
recovery, super and vendor are not install targets. No `/dev/block/sdcNN` paths
are hard-coded. The UFS image sector size is 4096 in deviceinfo; the recovery
installer probes the actual target through parted/kpartx.

## Maintenance

Edit the top-level packages, not only copies in `pmaports-tmp/aports`. Regenerate
checksums with `pmbootstrap checksum` against the isolated configuration after
changing package sources and propagate those updates to the top-level APKBUILD.
Advance the source lock deliberately; the helper refuses to change revisions
of a modified upstream checkout. Kernel config promotion requirements and
display/touch work are separate from recovery-image bring-up.
