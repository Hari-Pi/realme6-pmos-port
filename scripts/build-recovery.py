#!/usr/bin/env python3
"""Build an isolated Realme 6 recovery installer; never flash a device."""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = ROOT / "pmaports-tmp" / "build-dashboard"
BUILD_LOG = BUILD_DIR / "build.log"
BUILD_STATE = BUILD_DIR / "build.json"
CAPTURE_BUILD_OUTPUT = False

def run(*args):
    if CAPTURE_BUILD_OUTPUT:
        with BUILD_LOG.open("a") as output:
            subprocess.run([str(a) for a in args], stdout=output,
                           stderr=subprocess.STDOUT, check=True)
    else:
        subprocess.run([str(a) for a in args], check=True)

def write_state(**updates):
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    state = json.loads(BUILD_STATE.read_text()) if BUILD_STATE.exists() else {}
    state.update(updates)
    pending = BUILD_STATE.with_suffix(".json.tmp")
    pending.write_text(json.dumps(state, indent=2) + "\n")
    pending.replace(BUILD_STATE)

def checkout(path, url, revision):
    if not path.exists():
        run("git", "clone", "--depth=1", url, path)
    current = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    if current != revision:
        dirty = subprocess.check_output(["git", "-C", str(path), "status", "--porcelain"], text=True)
        if dirty:
            raise RuntimeError(f"Refusing to change a modified upstream checkout: {path}")
        run("git", "-C", path, "fetch", "--depth=1", "origin", revision)
        run("git", "-C", path, "checkout", "--detach", revision)

def main():
    global CAPTURE_BUILD_OUTPUT
    build_id = None
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--setup-only", action="store_true")
    parser.add_argument("--jobs", type=int, default=min(os.cpu_count() or 1, 12))
    parser.add_argument("--ui", choices=["console", "phosh"], default="console")
    parser.add_argument("--service-manager", choices=["openrc", "systemd"], default="openrc",
                        help="init system (openrc is compatible with the vendor 4.14 kernel)")
    parser.add_argument("--ssh-key", type=Path)
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("Run on Linux (the rig's Ubuntu WSL2 is the current build host).")
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    if not args.setup_only:
        BUILD_DIR.mkdir(parents=True, exist_ok=True)
        started = time.time()
        build_id = datetime.fromtimestamp(started).strftime("%Y%m%d-%H%M%S")
        BUILD_LOG.write_text("Realme 6 postmarketOS build started\n")
        write_state(started_at=started, finished_at=None, status="running",
                    build_id=build_id,
                    device="realme-nemo", kernel="linux-realme-nemo",
                    jobs=args.jobs, ui=args.ui)
        CAPTURE_BUILD_OUTPUT = True
    lock = json.loads((ROOT / "build.lock.json").read_text())
    tmp = ROOT / "pmaports-tmp"
    tmp.mkdir(exist_ok=True)
    for name in ("pmbootstrap", "pmaports"):
        checkout(tmp / ("aports" if name == "pmaports" else name),
                 f"https://gitlab.postmarketos.org/postmarketOS/{name}.git", lock[name])
    aports = tmp / "aports"
    for package in ("device-realme-nemo", "linux-realme-nemo"):
        shutil.copytree(ROOT / package, aports / "device/testing" / package, dirs_exist_ok=True)
    work = tmp / "work"
    work.mkdir(exist_ok=True)
    # Read the pinned tool's own work-directory version; don't hard-code it.
    sys.path.insert(0, str(tmp / "pmbootstrap"))
    import pmb.config
    version = work / "version"
    if not version.exists():
        version.write_text(str(pmb.config.work_version) + "\n")
    config = configparser.ConfigParser()
    config["pmbootstrap"] = {
        "aports": str(aports), "work": str(work), "device": "realme-nemo",
        "kernel": "realme-nemo", "ui": args.ui, "user": "user",
        "hostname": "realme-nemo", "jobs": str(args.jobs),
        "service_manager": args.service_manager, "timezone": "Asia/Kolkata",
        "ssh_keys": "false",
        "extra_packages": "postmarketos-usb-moded,postmarketos-usb-moded-default-profile-developer",
    }
    if args.ssh_key:
        key = args.ssh_key.resolve()
        if not key.is_file() or not key.read_text().startswith(("ssh-", "ecdsa-")):
            parser.error("--ssh-key must name an OpenSSH PUBLIC key")
    config["mirrors"] = {
        "alpine": "https://dl-cdn.alpinelinux.org/alpine/",
        "pmaports": "https://mirror.postmarketos.org/postmarketos/",
        "systemd": "https://mirror.postmarketos.org/postmarketos/extra-repos/systemd/",
    }
    cfg = tmp / "pmbootstrap.cfg"
    with cfg.open("w") as stream:
        config.write(stream)
    cfg.chmod(0o600)
    pmb = [sys.executable, str(tmp / "pmbootstrap/pmbootstrap.py"), "-c", str(cfg)]
    if os.geteuid() == 0:
        # Supported opt-in; use a dedicated root-owned work dir on WSL.
        pmb.append("--as-root")
    def invoke(*cmd):
        run(*pmb, *cmd)
    invoke("status")
    invoke("kconfig", "check", "linux-realme-nemo")
    invoke("checksum", "--verify", "linux-realme-nemo", "device-realme-nemo")
    if args.setup_only:
        return
    invoke("build", "linux-realme-nemo", "device-realme-nemo")
    if args.ssh_key:
        # Recovery zips omit /home, and the native copy_ssh_keys path only
        # applies to disk-image installs. Seed skel before tar creation.
        invoke("chroot", "-r", "true")
        target = work / "chroot_rootfs_realme-nemo/etc/skel/.ssh"
        privilege = [] if os.geteuid() == 0 else ["sudo"]
        run(*privilege, "install", "-d", "-m", "700", target)
        run(*privilege, "install", "-m", "600", key, target / "authorized_keys")
        run(*privilege, "chown", "-R", "10000:10000", target)
    # PMOS_PASSWORD is passed by the caller for unattended builds. Otherwise
    # pmbootstrap asks interactively. Never print/store it in tracked files.
    install = ["install", "--zap", "--android-recovery-zip",
               "--recovery-install-partition", "userdata", "--no-firewall"]
    if "PMOS_PASSWORD" in os.environ:
        install += ["--password", os.environ["PMOS_PASSWORD"]]
    # Avoid echoing the command because it may contain a password.
    if CAPTURE_BUILD_OUTPUT:
        with BUILD_LOG.open("a") as output:
            result = subprocess.run(pmb + install, stdout=output, stderr=subprocess.STDOUT)
    else:
        result = subprocess.run(pmb + install)
    if result.returncode:
        raise RuntimeError("pmbootstrap install failed; inspect pmaports-tmp/work/log.txt")
    archive = work / "chroot_buildroot_aarch64/var/lib/postmarketos-android-recovery-installer/pmos-realme-nemo.zip"
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    final = dist / "pmos-realme-nemo.zip"
    verification = [sys.executable, ROOT / "scripts/verify-recovery.py", archive,
                    "--report", dist / "verification.json"]
    if args.ssh_key:
        verification += ["--expected-key", key]
    run(*verification)
    shutil.copy2(archive, final)
    shutil.copy2(lock_path := ROOT / "build.lock.json", dist / lock_path.name)
    inputs = [ROOT / "build.lock.json"]
    for package in ("device-realme-nemo", "linux-realme-nemo", "scripts"):
        inputs += sorted(path for path in (ROOT / package).iterdir() if path.is_file())
    manifest = {"ui": args.ui, "service_manager": args.service_manager, "channel": lock["channel"],
                "inputs": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                           for path in inputs}}
    (dist / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    archive_sha256 = hashlib.sha256(final.read_bytes()).hexdigest()
    (dist / "SHA256SUMS").write_text(f"{archive_sha256}  {final.name}\n")
    build_dir = dist / "builds" / build_id
    build_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "id": build_id, "started_at": started, "finished_at": time.time(),
        "device": "realme-nemo", "kernel": "linux-realme-nemo",
        "ui": args.ui, "filename": final.name, "size": final.stat().st_size,
        "sha256": archive_sha256,
    }
    (build_dir / "artifact.json").write_text(json.dumps(artifact, indent=2) + "\n")
    for item in (final, dist / "verification.json", dist / "build-manifest.json",
                 dist / "build.lock.json", dist / "SHA256SUMS"):
        shutil.copy2(item, build_dir / item.name)
    print(f"Verified recovery package: {final}")
    if CAPTURE_BUILD_OUTPUT:
        write_state(status="complete", finished_at=time.time(),
                    artifact=str(final), build_id=build_id)

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        if CAPTURE_BUILD_OUTPUT:
            write_state(status="failed", finished_at=time.time(),
                        error=str(error))
        raise
