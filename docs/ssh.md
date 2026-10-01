# USB SSH for first boot

Connect the phone to a host using a data-capable USB cable. The existing port
documents USB NCM networking with the device at `172.16.42.1` and host at
`172.16.42.2`. Test:

```sh
ssh user@172.16.42.1
```

Use the image password chosen at build time. Pass a public key to
`scripts/build-recovery.py --ssh-key /path/to/id_ed25519.pub` for key login.
If the host does not receive a DHCP address, identify the new USB network
interface and configure `172.16.42.2/24` on that interface. Windows, macOS and
Linux use different interface names; do not assume `usb0` on the host.

A black screen is expected while the mainline panel driver is missing.
Lack of a display does not prove a failed boot. Conversely, successful SSH
must be measured on the newly built image, not inferred from a historical test.

Once connected:

```sh
uname -a
findmnt / /boot
lsblk -o NAME,SIZE,FSTYPE,LABEL,PARTLABEL,MOUNTPOINTS
systemctl --failed
systemctl status sshd usb-signaller unudhcpd@usb0
ip -br addr
journalctl -b -p warning
```

Current upstream uses `usb-signaller` for mode management; historical builds
used `usb-moded`. Check the actual service names with `systemctl list-units '*usb*' '*dhcp*'` if
they differ on the selected repository snapshot. The build leaves sshd enabled
through pmbootstrap and disables the firewall for development access.

`Connection refused` means the address is reachable but nothing accepted port
22. `No route to host` indicates host networking, cable, gadget enumeration or
device initialization problems. `172.16.42.2` is the host, not the phone.
For a failed boot, enter recovery and collect the recovery install log and
pstore logs where available before changing the image.
