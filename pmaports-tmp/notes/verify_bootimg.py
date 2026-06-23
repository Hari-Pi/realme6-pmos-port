#!/usr/bin/env python3
"""
Verify the produced boot.img against the reference boot-fixed.img.
"""
import hashlib
import struct
import subprocess
import sys
from pathlib import Path

REF = Path("/home/dazai/Projects/working/boot-fixed.img")
PROD = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/dazai/Projects/fresh/realme6-pmos-port/pmaports-tmp/notes/boot-produced.img")
PROD_AVB = Path("/home/dazai/Projects/fresh/realme6-pmos-port/pmaports-tmp/notes/boot-produced-avb.img")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_bootimg(path: Path) -> dict:
    with open(path, "rb") as f:
        data = f.read(2048)
    fields = struct.unpack_from("<8I16I", data, 8)
    return {
        "magic": data[:8],
        "kernel_size": fields[0],
        "kernel_addr": fields[1],
        "ramdisk_size": fields[2],
        "ramdisk_addr": fields[3],
        "second_size": fields[4],
        "second_addr": fields[5],
        "tags_addr": fields[6],
        "page_size": fields[7],
        "header_version": fields[8],
        "os_version": fields[9],
        "name": data[48:64].split(b"\x00", 1)[0].decode("utf-8", "replace"),
        "cmdline": data[64:576].split(b"\x00", 1)[0].decode("utf-8", "replace"),
        "extra_cmdline": data[576:1024].split(b"\x00", 1)[0].decode("utf-8", "replace"),
        "sha_in_header": data[1024:1024 + 32].hex(),
    }


def unpack(path: Path, dest: Path) -> dict:
    dest.mkdir(parents=True, exist_ok=True)
    for f in dest.iterdir():
        if f.is_file():
            f.unlink()
    subprocess.run(["unpack_bootimg", "--boot_img", str(path), "--out", str(dest)], check=True)
    out = {}
    for n in ["kernel", "ramdisk", "dtb", "recovery_dtbo"]:
        p = dest / n
        if p.exists():
            out[n] = {"size": p.stat().st_size, "sha256": sha256(p)}
    return out


def avb_info(path: Path) -> str:
    try:
        r = subprocess.run(["avbtool", "info_image", "--image", str(path)], capture_output=True, text=True, check=True)
        return r.stdout
    except subprocess.CalledProcessError as e:
        return f"avbtool error: {e.stderr or e.stdout}"


def dtb_summary(dts_path: Path) -> dict:
    if not dts_path.exists():
        return {}
    text = dts_path.read_text(errors="replace")
    model = ""
    compat = ""
    for line in text.splitlines():
        if not model and "model " in line:
            model = line.split('"')[1] if '"' in line else line
        if not compat and "compatible " in line and "realme" in line:
            compat = line.split('"')[1] if '"' in line else line
    return {"model": model, "compatible": compat}


def main() -> int:
    print(f"=== Comparing {PROD.name} vs boot-fixed.img ===\n")

    # File size
    ref_size = REF.stat().st_size
    prod_size = PROD.stat().st_size
    print(f"[file size]   ref={ref_size:>12,}  prod={prod_size:>12,}  delta={prod_size - ref_size:+,}")

    # Header
    h_ref = parse_bootimg(REF)
    h_prod = parse_bootimg(PROD)

    print(f"\n[boot image header]")
    keys = ["magic", "header_version", "page_size", "kernel_addr", "kernel_size",
            "ramdisk_addr", "ramdisk_size", "second_size", "tags_addr", "name",
            "cmdline", "extra_cmdline"]
    for k in keys:
        rv, pv = h_ref[k], h_prod[k]
        same = "==" if rv == pv else "!="
        if k == "cmdline":
            print(f"  {k:20s}  ref={rv!r}  ({len(rv)} chars)")
            print(f"  {'':20s}  prod={pv!r}  ({len(pv)} chars) {same}")
        else:
            print(f"  {k:20s}  ref={rv!r}  prod={pv!r} {same}")

    # Unpack both
    tmp = Path("/tmp/verify-boot")
    tmp.mkdir(parents=True, exist_ok=True)
    ref_dir = tmp / "ref"
    prod_dir = tmp / "prod"
    print("\n[unpacking]")
    u_ref = unpack(REF, ref_dir)
    u_prod = unpack(PROD, prod_dir)
    for k in ["kernel", "ramdisk", "dtb", "recovery_dtbo"]:
        r, p = u_ref.get(k, {}), u_prod.get(k, {})
        print(f"  {k:14s}  ref=size={r.get('size','?'):>8,} sha={r.get('sha256','?')[:16]}...  prod=size={p.get('size','?'):>8,} sha={p.get('sha256','?')[:16]}...  "
              f"same_sha={'YES' if r.get('sha256') == p.get('sha256') else 'NO'}")

    # DTB details
    print("\n[DTB details]")
    print("  ref :", dtb_summary(ref_dir / "kernel.dts"))
    # The unpacked kernel isn't a dts; we need to compile the dtb back to dts
    if (ref_dir / "dtb").exists():
        subprocess.run(["dtc", "-I", "dtb", "-O", "dts", "-o", str(ref_dir / "kernel.dts"), str(ref_dir / "dtb")], check=False, capture_output=True)
    if (prod_dir / "dtb").exists():
        subprocess.run(["dtc", "-I", "dtb", "-O", "dts", "-o", str(prod_dir / "kernel.dts"), str(prod_dir / "dtb")], check=False, capture_output=True)
    print("  ref model/compat :", dtb_summary(ref_dir / "kernel.dts"))
    print("  prod model/compat:", dtb_summary(prod_dir / "kernel.dts"))

    # AVB footer
    print("\n[AVB footer]")
    print("--- REF ---")
    print(avb_info(REF))
    print("--- PROD (raw) ---")
    print(avb_info(PROD))
    if PROD_AVB.exists():
        print("--- PROD (AVB-padded to 32 MiB) ---")
        print(avb_info(PROD_AVB))

    return 0


if __name__ == "__main__":
    sys.exit(main())
