#!/usr/bin/env python3
"""Verify the actual boot image and installation options inside a recovery zip."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import tarfile
import zipfile

def require(condition, message):
    if not condition:
        raise ValueError(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def verify_boot(data, dtb, dtbo):
    require(len(data) == 33554432, "boot.img must fill the 32 MiB boot partition")
    require(data[:8] == b"ANDROID!", "Missing Android boot magic")
    fields = struct.unpack_from("<10I", data, 8)
    kernel_size, kernel_addr, ramdisk_size, ramdisk_addr, second_size, second_addr, tags_addr, page, version, os_version = fields
    require(version == 2 and page == 2048, "Expected header v2, page size 2048")
    require((kernel_addr, ramdisk_addr, tags_addr) == (0x40080000, 0x47c80000, 0x4bc80000), "Unexpected boot load addresses")
    require(kernel_size > 0 and ramdisk_size > 0 and second_size == 0, "Missing kernel/ramdisk or unexpected second image")
    require(os_version == (10 << 25) | (21 << 4) | 8, "Expected Android 10.0.0 / 2021-08 header")
    cmdline = (data[64:576].split(b"\0", 1)[0] + data[608:1632].split(b"\0", 1)[0]).decode()
    require(len(cmdline) <= 93, f"Command line exceeds historical LK budget: {len(cmdline)}")
    require("bootopt=64S3,32N2,64N2" in cmdline, "Missing MTK bootopt")
    require(not any(x in cmdline.split() for x in ["quiet", "splash", "plymouth.prefer-fbcon", "plymouth.ignore-serial-consoles"]), "Unexpected splash arguments")
    recovery_size, recovery_offset, header_size = struct.unpack_from("<IQI", data, 1632)
    dtb_size, dtb_addr = struct.unpack_from("<IQ", data, 1648)
    require(header_size == 1660 and dtb_addr == 0x4bc80000, "Unexpected v2 DTB layout")
    aligned = lambda size: (size + page - 1) // page * page
    dtb_offset = page + aligned(kernel_size) + aligned(ramdisk_size) + aligned(second_size) + aligned(recovery_size)
    require(data[dtb_offset:dtb_offset + dtb_size] == dtb, "Embedded DTB differs from packaged DTB")
    require(data[recovery_offset:recovery_offset + recovery_size] == dtbo, "Embedded recovery DTBO differs from packaged DTBO")
    require(dtb[:4] == b"\xd0\x0d\xfe\xed" and b"realme,nemo\0" in dtb and b"Realme 6\0" in dtb, "DTB isn't the Realme 6 board")
    require(dtbo[:4] == b"\xd7\xb7\xab\x1e", "Missing DTBO table header")
    magic, major, minor, original, vbmeta_offset, vbmeta_size = struct.unpack_from(">4sIIQQQ", data, len(data) - 64)
    require(magic == b"AVBf" and major == 1, "Missing AVB footer")
    require(dtb_offset + dtb_size <= original <= vbmeta_offset and vbmeta_offset + vbmeta_size <= len(data) - 64, "AVB footer bounds invalid")
    vbmeta = data[vbmeta_offset:vbmeta_offset + vbmeta_size]
    require(vbmeta[:4] == b"AVB0", "Missing VBMeta header")
    auth_size, aux_size, algorithm = struct.unpack_from(">QQI", vbmeta, 12)
    require(algorithm == 0, "Expected AVB algorithm NONE")
    descriptor_offset, descriptor_size = struct.unpack_from(">QQ", vbmeta, 96)
    cursor = 256 + auth_size + descriptor_offset
    end = cursor + descriptor_size
    require(end <= len(vbmeta) and 256 + auth_size + aux_size <= len(vbmeta), "VBMeta descriptor bounds invalid")
    found = False
    while cursor < end:
        tag, length = struct.unpack_from(">QQ", vbmeta, cursor)
        require(cursor + 16 + length <= end and length > 0, "Malformed AVB descriptor")
        if tag == 2:
            image_size = struct.unpack_from(">Q", vbmeta, cursor + 16)[0]
            algo = vbmeta[cursor + 24:cursor + 56].rstrip(b"\0")
            name_len, salt_len, digest_len = struct.unpack_from(">III", vbmeta, cursor + 56)
            payload = cursor + 132
            name = vbmeta[payload:payload + name_len]
            salt = vbmeta[payload + name_len:payload + name_len + salt_len]
            digest = vbmeta[payload + name_len + salt_len:payload + name_len + salt_len + digest_len]
            require(name == b"boot" and algo == b"sha256" and image_size == original, "Unexpected AVB hash descriptor")
            require(hashlib.sha256(salt + data[:image_size]).digest() == digest, "AVB image hash mismatch")
            found = True
        cursor += 16 + length
    require(found, "Missing AVB boot hash descriptor")
    return {"size": len(data), "sha256": sha(data), "header_version": version,
            "cmdline": cmdline, "cmdline_length": len(cmdline), "dtb_sha256": sha(dtb),
            "recovery_dtbo_sha256": sha(dtbo), "avb_hash_verified": True}

def verify(path, expected_key=None):
    wanted = {"boot/boot.img", "boot/empty.dtbo", "boot/dtbs/mediatek/mt6785-realme-nemo.dtb",
              "etc/fstab", "etc/passwd", "usr/share/deviceinfo/device-realme-nemo"}
    files = {}
    if expected_key:
        wanted.add("etc/skel/.ssh/authorized_keys")
    with zipfile.ZipFile(path) as archive:
        require(archive.testzip() is None, "Zip CRC check failed")
        require("META-INF/com/google/android/update-binary" in archive.namelist(), "Missing recovery entrypoint")
        options = archive.read("chroot/install_options").decode()
        for value in ["DEVICE='realme-nemo'", "INSTALL_PARTITION='userdata'", "FLASH_KERNEL='true'", "FDE='false'"]:
            require(value in options.splitlines(), f"Missing installer setting: {value}")
        with archive.open("rootfs.tar.gz") as rootfs, tarfile.open(fileobj=rootfs, mode="r|gz") as tar:
            for member in tar:
                name = member.name.removeprefix("./")
                if name in wanted and member.isfile():
                    require(member.size < 40 * 1024 * 1024, f"Unexpected size: {name}")
                    files[name] = tar.extractfile(member).read()
        require(wanted <= files.keys(), f"Missing rootfs files: {wanted - files.keys()}")
        require(b"user:x:10000:" in files["etc/passwd"], "Expected user account UID 10000")
        # Current base fstab leaves / and /boot to the initramfs. Reject stale
        # host-build UUID entries, which cannot match recovery-created filesystems.
        for line in files["etc/fstab"].decode().splitlines():
            fields = line.split()
            if fields and not line.lstrip().startswith("#") and len(fields) >= 2:
                if fields[1] in ("/", "/boot"):
                    label = "LABEL=pmOS_root" if fields[1] == "/" else "LABEL=pmOS_boot"
                    require(fields[0] == label, "Stale or unexpected root/boot fstab source")
        if expected_key:
            require(files["etc/skel/.ssh/authorized_keys"] == expected_key.read_bytes(), "Public key missing from recovery home skeleton")
        boot = verify_boot(files["boot/boot.img"], files["boot/dtbs/mediatek/mt6785-realme-nemo.dtb"], files["boot/empty.dtbo"])
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"archive": path.name, "size": path.stat().st_size, "sha256": digest.hexdigest(),
            "install_partition": "userdata", "boot": boot, "hardware_boot_tested": False}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--expected-key", type=Path)
    args = parser.parse_args()
    report = verify(args.archive, args.expected_key)
    text = json.dumps(report, indent=2) + "\n"
    if args.report:
        args.report.write_text(text)
        (args.report.parent / "SHA256SUMS").write_text(f"{report['sha256']}  {args.archive.name}\n")
    print(text, end="")

if __name__ == "__main__":
    main()
