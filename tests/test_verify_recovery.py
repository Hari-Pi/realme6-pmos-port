"""Exercise corruption detection without requiring a phone or build chroots."""
import importlib.util
from pathlib import Path
import struct
import unittest
import hashlib
import io
import tarfile
import tempfile
import zipfile

spec = importlib.util.spec_from_file_location("verify", Path(__file__).parents[1] / "scripts/verify-recovery.py")
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)

def image():
    page = 2048
    dtb = b"\xd0\x0d\xfe\xedRealme 6\0realme,nemo\0mediatek,mt6785\0"
    dtbo = b"\xd7\xb7\xab\x1e" + b"\0" * 132
    data = bytearray(33554432)
    data[:8] = b"ANDROID!"
    struct.pack_into("<10I", data, 8, 4, 0x40080000, 4, 0x47c80000,
                     0, 0, 0x4bc80000, page, 2, (10 << 25) | (21 << 4) | 8)
    cmdline = b"bootopt=64S3,32N2,64N2 androidboot.serialconsole=0 gpt=1 loop.max_part=7 rw"
    data[64:64 + len(cmdline)] = cmdline
    struct.pack_into("<IQI", data, 1632, len(dtbo), page * 3, 1660)
    struct.pack_into("<IQ", data, 1648, len(dtb), 0x4bc80000)
    data[page:page + 4] = b"kern"
    data[page * 2:page * 2 + 4] = b"init"
    data[page * 3:page * 3 + len(dtbo)] = dtbo
    data[page * 4:page * 4 + len(dtb)] = dtb
    original = page * 5
    salt = b"test-salt"
    digest = hashlib.sha256(salt + data[:original]).digest()
    variable = b"boot" + salt + digest
    descriptor = bytearray(132 + len(variable))
    descriptor += b"\0" * ((-len(descriptor)) % 8)
    struct.pack_into(">QQQ", descriptor, 0, 2, len(descriptor) - 16, original)
    descriptor[24:30] = b"sha256"
    struct.pack_into(">III", descriptor, 56, 4, len(salt), len(digest))
    descriptor[132:132 + len(variable)] = variable
    vbmeta = bytearray(256) + descriptor
    vbmeta[:4] = b"AVB0"
    struct.pack_into(">QQI", vbmeta, 12, 0, len(descriptor), 0)
    struct.pack_into(">QQ", vbmeta, 96, 0, len(descriptor))
    data[original:original + len(vbmeta)] = vbmeta
    struct.pack_into(">4sIIQQQ", data, len(data) - 64, b"AVBf", 1, 0, original, original, len(vbmeta))
    return data, dtb, dtbo

class VerifyBootTests(unittest.TestCase):
    def test_valid_hash_and_header(self):
        data, dtb, dtbo = image()
        result = verify.verify_boot(data, dtb, dtbo)
        self.assertTrue(result["avb_hash_verified"])
        self.assertLessEqual(result["cmdline_length"], 93)

    def test_corrupt_kernel_rejected_by_hash(self):
        data, dtb, dtbo = image()
        data[2048] ^= 1
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            verify.verify_boot(data, dtb, dtbo)

class VerifyArchiveTests(unittest.TestCase):
    def archive(self, path, partition="userdata"):
        data, dtb, dtbo = image()
        files = {
            "boot/boot.img": data, "boot/empty.dtbo": dtbo,
            "boot/dtbs/mediatek/mt6785-realme-nemo.dtb": dtb,
            "etc/passwd": b"user:x:10000:10000::/home/user:/bin/sh\n",
            "etc/fstab": b"# Root and boot are mounted by initramfs.\n",
            "usr/share/deviceinfo/device-realme-nemo": b'deviceinfo_codename="realme-nemo"\n',
        }
        rootfs = io.BytesIO()
        with tarfile.open(fileobj=rootfs, mode="w:gz") as tar:
            for name, content in files.items():
                member = tarfile.TarInfo("./" + name)
                member.size = len(content)
                tar.addfile(member, io.BytesIO(content))
            member = tarfile.TarInfo("./usr/share/deviceinfo/deviceinfo")
            member.type = tarfile.SYMTYPE
            member.linkname = "device-realme-nemo"
            tar.addfile(member)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("META-INF/com/google/android/update-binary", "#!/bin/sh\n")
            archive.writestr("chroot/install_options", f"DEVICE='realme-nemo'\nINSTALL_PARTITION='{partition}'\nFLASH_KERNEL='true'\nFDE='false'\n")
            archive.writestr("rootfs.tar.gz", rootfs.getvalue())

    def test_recovery_archive_with_deviceinfo_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "pmos-realme-nemo.zip"
            self.archive(path)
            result = verify.verify(path)
            self.assertEqual(result["install_partition"], "userdata")
            self.assertFalse(result["hardware_boot_tested"])

    def test_wrong_install_partition_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "wrong.zip"
            self.archive(path, "system")
            with self.assertRaisesRegex(ValueError, "INSTALL_PARTITION"):
                verify.verify(path)

    def test_wrong_packaged_dtb_rejected(self):
        data, dtb, dtbo = image()
        with self.assertRaisesRegex(ValueError, "Embedded DTB differs"):
            verify.verify_boot(data, dtb + b"changed", dtbo)

    def test_missing_footer_rejected(self):
        data, dtb, dtbo = image()
        data[-64:] = b"\0" * 64
        with self.assertRaisesRegex(ValueError, "Missing AVB footer"):
            verify.verify_boot(data, dtb, dtbo)

    def test_wrong_dtb_address_rejected(self):
        data, dtb, dtbo = image()
        struct.pack_into("<Q", data, 1652, 0x41f00000)
        with self.assertRaisesRegex(ValueError, "DTB layout"):
            verify.verify_boot(data, dtb, dtbo)

if __name__ == "__main__":
    unittest.main()
