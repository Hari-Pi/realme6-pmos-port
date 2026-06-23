# SSH access on the Realme 6

After TWRP installs the recovery zip and the device reboots, postmarketOS is
reachable over USB. The device presents an NCM (network control model) USB
interface and runs a small DHCP server that assigns itself `172.16.42.1` and
the host `172.16.42.2`. This page covers the network setup, the SSH command,
and what to check if the connection doesn't go through.

For the build pipeline itself, see [build.md](build.md).
For the boot image verification procedure, see [verify.md](verify.md).

## 1. USB network topology

postmarketOS's `usb-moded` switches the device into developer mode when it
sees a host that's not a charger. In that mode the device exposes an NCM USB
interface as `ncm.usb0` and starts a tiny DHCP server
(`unudhcpd@usb0.service`). The server's hard-coded address range:

```
UNUDHCPD_SERVER=172.16.42.1   # the device
UNUDHCPD_CLIENT=172.16.42.2   # the host (laptop)
```

The same scheme is used by every postmarketOS device in developer mode. The
configuration is in `/usr/lib/systemd/system/unudhcpd@.service` on the device.

On the host, the USB interface typically shows up as `enp<...>s<...>u<...>` (or
just `usb0` if you have an old `cdc_ether` driver). After plugging the phone
in with developer mode active, the host should pick up `172.16.42.2`:

```bash
$ ip -br addr
enp1s0u1u1  UP   172.16.42.2/24 ...
```

If you don't see `172.16.42.2` on any interface, the device hasn't entered
developer mode yet. Things to check on the device (via touchscreen + a USB
keyboard, or already-ssh'd):

```bash
systemctl status usb-moded-developer-mode
systemctl status unudhcpd@usb0
ip addr
```

## 2. The SSH command

```bash
ssh user@172.16.42.1
```

`172.16.42.2` is the host. If `sshd` is not running on the host, that
address returns `Connection refused`. Connecting to `.1` (the device) is the
path that works.

Login:

- **user**: `user` (UID 10000, the standard postmarketOS user)
- **password**: whatever you passed to `pmbootstrap install --password …` at
  build time. The build commands in [build.md](build.md) use `1234`.

If you forget the password, rebuild the recovery zip with a new one — there's
no in-place way to reset the `user` account without a chroot.

## 3. What serves SSH on the device

The chroot installs `openssh-server-pam` (Alpine package), whose only binary
is `/usr/sbin/sshd.pam`. The `sshd.service` unit's `ExecStart=/usr/sbin/sshd.pam
-D` points at it. Configuration:

- `Port 22` (default; nothing overrides it).
- `ListenAddress 0.0.0.0` (default).
- `PasswordAuthentication yes` (default).
- `PubkeyAuthentication yes` (default).
- `UsePAM yes` (set by `/etc/ssh/sshd_config.d/50-postmarketos-ui-policy.conf`).
- `AllowTcpForwarding no` (set by the upstream config — useful to know if you
  intend to tunnel).

`sshd` generates its host keys on first start if they're missing. An empty
`/etc/ssh/` in the chroot is normal; the keys appear on first boot.

The `nftables` firewall is disabled by pmbootstrap's
`80-pmbootstrap-install-disable-nftables.preset`, so port 22 is reachable
from the USB interface.

## 4. Switching to key-based auth

By default the device has no `authorized_keys` for the `user` account — only
password auth works. To add a key (after the first password login):

On the device:

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
cat > ~/.ssh/authorized_keys <<'EOF'
ssh-ed25519 AAAA... your-key-here
EOF
chmod 600 ~/.ssh/authorized_keys
```

On the host, an entry in `~/.ssh/config` saves the IP:

```
Host nemo
    HostName 172.16.42.1
    User user
    PreferredAuthentications publickey,password
```

`ssh nemo` then works from anywhere on the host.

## 5. Troubleshooting

- **`Connection refused` on `172.16.42.1`** — sshd hasn't started, or the
  device hasn't entered developer mode. On the device, check `systemctl
  status sshd`, `systemctl status usb-moded-developer-mode`, and `ip addr`.

- **`No route to host` on `172.16.42.1`** — the host's USB interface is down
  or the device never brought up `usb0`. Re-plug the cable; the host's
  `usb0` (or similar) should get `172.16.42.2` from the device's DHCP.

- **`Connection refused` on `172.16.42.2`** — `.2` is the host, not the
  device. Connect to `.1` instead (see section 1).

- **Wrong password** — the chroot's `/etc/shadow` password is whatever was
  passed to `pmbootstrap install --password`. Rebuild with a different
  `--password` if it's lost.
