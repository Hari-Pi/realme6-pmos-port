# Hardware bring-up ledger

This page records what was actually tested on the Realme 6 (RMX2001), separate
from what a package or static verifier says should work.

## 2026-10-01 OpenRC milestone

The recovery installer built at `20261001-061128` completed successfully in
OrangeFox. It erased and repartitioned `userdata`, extracted a fresh Phosh
rootfs, and wrote its generated boot image. Recovery and LK were not installer
targets.

Artifact identity:

| Item | SHA-256 |
| --- | --- |
| `pmos-realme-nemo.zip` | `0a17a38c1be72c8dd5f835341994bbf125ea432fdffdfdf7542b173f3370c7bd` |
| generated mainline `boot.img` | `5bf4aa58ab4a04b314483a08f6c71db894f4c2c2ffa29f9205c1590aaa2c8e94` |
| tested downstream hybrid boot image | `f003e5eaa7b5dc30053aee0068939135bc1f02a084b3e673e14929c6306521d8` |

Before the first boot, the generated mainline boot image was deliberately
replaced with the tested downstream 4.14 hybrid image. Therefore this run
validates the OpenRC root filesystem with that downstream kernel; it does not
claim that the generated mainline boot image reached userspace.

Validated on the installed root:

- `/sbin/init` resolves to BusyBox/OpenRC and the `openrc` package is present.
- The `systemd` package is absent.
- `greetd`, NetworkManager, `sshd`, elogind, USB signaling, cgroups and the
  other default OpenRC services are enabled.
- NetworkManager loaded the recovery-seeded Wi-Fi profile and acquired
  `10.0.0.7` on the test LAN.
- TCP port 22 was reachable over Wi-Fi.
- USB gadget initialization reached Windows as `UsbNcm Host Device`.

The USB host initially self-assigned a `169.254.x.x` address. Giving the host
side `172.16.42.2/24` did not make `172.16.42.1` answer. Wi-Fi SSH is therefore
the confirmed management path; the phone-side USB address/service still needs
diagnosis.

## Why OpenRC

The previous image used systemd 262 with the downstream Linux 4.14.141 kernel.
That systemd release expects a Linux 5.14 baseline and no longer supports the
legacy cgroup-v1 setup. The vendor kernel also lacks namespaces, cgroup PIDs and
the cgroup device controller. Removing the legacy cgroup command-line argument
did not solve that incompatibility and produced an early reboot.

OpenRC avoids that userspace/kernel contract. It is now the builder default;
`--service-manager systemd` remains available for future mainline-kernel tests.
The installer uses `--zap` so a failed or interrupted build cannot leak an old
root filesystem into a new archive.

## OrangeFox loop-device trap

After the recovery installer repartitions `userdata`, an old `/dev/loop0`
mapping can retain stale filesystem state in the running recovery session.
Mounting that node after installation showed the previous systemd root even
though the ZIP contained OpenRC.

The installer-created mapper node `/dev/block/mapper/sdc51p2` showed the correct
fresh OpenRC filesystem. Always inspect the current kpartx mapper after an
in-place repartition, or reboot recovery before mounting the new root. Do not
judge the installed image from a pre-existing loop mapping.

## Display status

Kernel commit `18e1ca2df` in the downstream reference tree stabilizes the
framebuffer handoff and stops the repeated display flashing seen in earlier
hybrid images. The phone has rendered the Phosh on-screen keyboard with that
kernel. Touch input did not respond reliably in the earlier systemd image.
The OpenRC graphical session and touch stack have not yet been conclusively
validated in this checkpoint.

## Recovery safety

Known-good boot, recovery and LK partitions were saved before installation.
The final tested boot partition hash matched the downstream hybrid image before
reboot. The recovery ZIP writes only its subpartitions inside `userdata` and the
top-level `boot` partition; it does not overwrite recovery or LK.

## Next checks

1. Log in over Wi-Fi SSH and capture `rc-status -a`, `dmesg`, greetd logs, and
   the Phosh/phoc process state.
2. Determine why USB-NCM enumerates but the phone does not answer at
   `172.16.42.1`.
3. Confirm whether greetd starts Phosh under OpenRC and whether framebuffer,
   input and seat devices are accessible to that session.
4. Keep the downstream hybrid and generated mainline boot images labeled as
   different test targets.
