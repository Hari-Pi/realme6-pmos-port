# SSH access on the Realme 6

After TWRP installs the recovery zip and the device reboots, you reach
postmarketOS via USB. The catch: the device's IP is **172.16.42.1**, not
`.2`. Most first-time setups ssh to the wrong host. This page explains the
topology and the working command.

## 1. USB network topology

postmarketOS's `usb-moded` switches into developer mode when it sees a host
that's not a charger. In that mode the device exposes an NCM (network control
model) USB interface as `ncm.usb0` and starts a tiny DHCP server
(`unudhcpd@usb0.service`). The server's hard-coded address range:

```
UNUDHCPD_SERVER=172.16.42.1   # the device
UNUDHCPD_CLIENT=172.16.42.2   # the host (laptop)
```

So:

- **Device** (the Realme 6) is `172.16.42.1`.
- **Host** (your laptop, the Fedora box you built on) is `172.16.42.2`.

The reverse of what you might assume. This is encoded in
`/usr/lib/systemd/system/unudhcpd@.service` and applies to every postmarketOS
device in developer mode.

On the host, the USB interface typically shows up as `enp<...>s<...>u<...>` (or
just `usb0` if you have an old `cdc_ether` driver). After plugging the phone in
with developer mode active, you should see something like:

```bash
$ ip -br addr
enp1s0u1u1  UP   172.16.42.2/24 ...
```

If you don't see `172.16.42.2` on any interface, the device hasn't entered
developer mode yet — re-plug the cable, or check that `usb-moded-developer-mode`
came up on the device:

```bash
# on the device (via touchscreen + a USB keyboard, or already-ssh'd)
systemctl status usb-moded-developer-mode
systemctl status unudhcpd@usb0
```

## 2. The SSH command

```bash
ssh user@172.16.42.1
```

NOT `172.16.42.2` — that's your laptop, and Fedora's `sshd` is not running by
default, so you'll get `ssh: connect to host 172.16.42.2 port 22: Connection refused`.

Login:

- **user**: `user` (UID 10000, the standard postmarketOS user)
- **password**: whatever you passed to `pmbootstrap install --password …` at
  build time. The build commands in [build.md](build.md) use `1234`.

If you forget the password, rebuild the recovery zip with a new one — there's
no in-place way to reset the `user` account without a chroot.

## 3. What's actually serving SSH

The chroot installs `openssh-server-pam` (Alpine package), whose only binary is
`/usr/sbin/sshd.pam`. The `sshd.service` unit's `ExecStart=/usr/sbin/sshd.pam -D`
points at it. Configuration:

- `Port 22` (default; nothing overrides it).
- `ListenAddress 0.0.0.0` (default).
- `PasswordAuthentication yes` (default).
- `PubkeyAuthentication yes` (default).
- `UsePAM yes` (set by `/etc/ssh/sshd_config.d/50-postmarketos-ui-policy.conf`).
- `AllowTcpForwarding no` (set by the upstream config — useful to know if you
  intend to tunnel).

`sshd` generates its host keys on first start if they're missing. Don't be
alarmed if `/etc/ssh/` looks empty in the chroot — the keys appear on first
boot.

The `nftables` firewall is **disabled** by pmbootstrap's
`80-pmbootstrap-install-disable-nftables.preset`, so port 22 is wide open from
the USB interface.

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

On the host, in `~/.ssh/config` you can add an entry so you don't have to type
the IP every time:

```
Host nemo
    HostName 172.16.42.1
    User user
    PreferredAuthentications publickey,password
```

Then `ssh nemo` works from anywhere on the host.

## 5. Common gotchas

- **"Connection refused" on `172.16.42.1`**: sshd hasn't started yet, or the
  device hasn't entered developer mode. Check on the device
  (`systemctl status sshd`, `systemctl status usb-moded-developer-mode`,
  `ip addr`).

- **"No route to host" on `172.16.42.1`**: the USB interface on the host is
  down, or the device never brought up `usb0`. Re-plug the cable. The host's
  `usb0` (or similar) should have `172.16.42.2` once the device's DHCP server
  hands it out.

- **"Connection refused" on `172.16.42.2`**: you're sshing at the wrong host.
  See section 1. Try `.1` instead.

- **Wrong password**: the password baked into the chroot's `/etc/shadow` is
  whatever you passed to `pmbootstrap install --password`. The `--password` flag
  is what writes `/etc/shadow` for the `user` entry. Build again with a
  different password if you lost it.
