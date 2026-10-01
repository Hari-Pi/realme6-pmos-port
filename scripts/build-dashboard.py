#!/usr/bin/env python3
"""Read-only live dashboard for the latest Realme 6 pmOS build."""
from datetime import datetime
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
LOG = Path(os.environ.get("PMOS_BUILD_LOG", ROOT / "pmaports-tmp/build-dashboard/build.log"))
STATE = Path(os.environ.get("PMOS_BUILD_STATE", ROOT / "pmaports-tmp/build-dashboard/build.json"))
FALLBACK_LOG = ROOT / "pmaports-tmp/work/log.txt"
PAGE = ROOT / "dashboard/index.html"
BUILDS = ROOT / "dist/builds"
MAX_LOG_BYTES = 1_500_000


def stamp_from_line(line):
    match = re.search(r"\[(\d\d):(\d\d):(\d\d)\]", line)
    if not match:
        return None
    now = datetime.now().astimezone()
    hour, minute, second = map(int, match.groups())
    return now.replace(hour=hour, minute=minute, second=second, microsecond=0).timestamp()


def snapshot(since=0, requested_source=""):
    log_path = LOG if LOG.exists() else FALLBACK_LOG
    try:
        with log_path.open("rb") as stream:
            stream.seek(max(0, log_path.stat().st_size - MAX_LOG_BYTES))
            raw = stream.read().decode("utf-8", "replace")
    except OSError:
        raw = ""
    lines = raw.splitlines()
    state = {}
    try:
        state = json.loads(STATE.read_text())
    except (OSError, json.JSONDecodeError):
        pass

    # pmbootstrap keeps its own detailed log. Pick the newest Realme kernel
    # build command, then only treat later markers as belonging to that run.
    starts = [i for i, line in enumerate(lines)
              if "pmbootstrap.py" in line and "build linux-realme-nemo" in line]
    start_index = starts[-1] if starts else 0
    run_lines = lines[start_index:]
    if starts:
        started = stamp_from_line(lines[start_index])
        if started is None:
            started = stamp_from_line(lines[start_index - 1]) if start_index else None
    else:
        started = state.get("started_at")
    if state.get("started_at") and LOG.exists():
        started = state["started_at"]

    completed = any("DONE!" in line for line in run_lines)
    state_is_current = LOG.exists() and bool(state)
    status = state.get("status", "complete" if completed else "running" if raw else "waiting")
    if status == "running" and completed and not state_is_current:
        status = "complete"
    if status == "running":
        # A stopped helper must not leave the UI spinning forever.
        updated = (LOG if LOG.exists() else FALLBACK_LOG).stat().st_mtime if log_path.exists() else 0
        if updated and time.time() - updated > 90:
            status = "stalled"

    compiler_units = sum(1 for line in run_lines
                         if re.search(r"\b(?:CC|LD|AR|AS|HOSTCC)\s+(?:\[M\]\s+)?", line))
    full_text = "\n".join(run_lines)
    if status == "complete":
        progress, phase = 100, "Recovery package ready"
    elif status == "failed":
        progress, phase = 0, "Build failed"
    elif any("install --android-recovery-zip" in line for line in run_lines):
        progress, phase = 91, "Creating recovery image"
    elif "mkinitfs" in full_text or "rootfs.tar" in full_text:
        progress, phase = 84, "Packaging the root filesystem"
    elif compiler_units:
        # This is a visual estimate; pmbootstrap doesn't report a reliable
        # total number of kernel compile actions.
        progress, phase = min(78, 7 + int(compiler_units / 55)), "Compiling the kernel · estimated"
    elif starts:
        progress, phase = 5, "Preparing the build"
    else:
        progress, phase = 0, "Waiting for a build"

    now = time.time()
    finished = state.get("finished_at")
    if not finished and completed:
        end_lines = [line for line in run_lines if "DONE!" in line]
        finished = stamp_from_line(end_lines[-1]) if end_lines else None
        if finished and started and finished < started:
            finished += 24 * 60 * 60
    elapsed = max(0, (finished or now) - started) if started else 0
    source = f"{log_path}:{int(started or 0)}"
    total_lines = len(run_lines)
    if requested_source == source and 0 <= since <= total_lines:
        visible_lines = run_lines[since:]
    else:
        visible_lines = run_lines[-1200:]
    if len(visible_lines) > 1200:
        visible_lines = visible_lines[-1200:]
    return {
        "status": status, "phase": phase, "progress": progress,
        "progressIsEstimate": status not in ("complete", "failed"),
        "startedAt": started, "finishedAt": finished,
        "elapsedSeconds": int(elapsed),
        "updatedAt": log_path.stat().st_mtime if log_path.exists() else None,
        "device": state.get("device", "Realme 6 · RMX2001"),
        "kernel": state.get("kernel", "linux-realme-nemo"),
        "jobs": state.get("jobs"), "ui": state.get("ui"),
        "compilerUnits": compiler_units,
        "source": source, "totalLines": total_lines,
        "log": visible_lines, "logBytes": log_path.stat().st_size if log_path.exists() else 0,
        "error": state.get("error"),
    }


def available_builds():
    result = []
    if not BUILDS.is_dir():
        return result
    for directory in sorted(BUILDS.iterdir(), reverse=True):
        if not directory.is_dir() or not re.fullmatch(r"\d{8}-\d{6}", directory.name):
            continue
        metadata = {}
        try:
            metadata = json.loads((directory / "artifact.json").read_text())
        except (OSError, json.JSONDecodeError):
            pass
        filename = metadata.get("filename", "pmos-realme-nemo.zip")
        if not re.fullmatch(r"[A-Za-z0-9._-]+", filename):
            continue
        archive = directory / filename
        if not archive.is_file():
            continue
        verification = {}
        try:
            verification = json.loads((directory / "verification.json").read_text())
        except (OSError, json.JSONDecodeError):
            pass
        try:
            started = datetime.strptime(directory.name, "%Y%m%d-%H%M%S").astimezone().timestamp()
        except ValueError:
            started = archive.stat().st_mtime
        result.append({
            "id": directory.name,
            "startedAt": metadata.get("started_at", started),
            "finishedAt": metadata.get("finished_at", archive.stat().st_mtime),
            "device": metadata.get("device", "realme-nemo"),
            "kernel": metadata.get("kernel", "linux-realme-nemo"),
            "ui": metadata.get("ui", "console"),
            "kind": metadata.get("kind", "Recovery ZIP"),
            "filename": filename,
            "size": archive.stat().st_size,
            "sha256": metadata.get("sha256", verification.get("sha256")),
            "downloadUrl": f"/downloads/{directory.name}/{filename}",
        })
    return result


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def download_path(self, request_path):
        match = re.fullmatch(r"/downloads/(\d{8}-\d{6})/([A-Za-z0-9._-]+)", request_path)
        if not match:
            return None, None
        return match.group(1), BUILDS / match.group(1) / match.group(2)

    def serve_download(self, build_id, archive, head_only=False):
        if not archive.is_file():
            self.send_error(404)
            return
        stat = archive.stat()
        start, end, status = 0, stat.st_size - 1, 200
        range_header = self.headers.get("Range")
        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
            try:
                if not match or not any(match.groups()):
                    raise ValueError
                first, last = match.groups()
                if first:
                    start = int(first)
                    end = int(last) if last else stat.st_size - 1
                else:
                    suffix = int(last)
                    if suffix <= 0:
                        raise ValueError
                    start = max(0, stat.st_size - suffix)
                if start >= stat.st_size or end < start:
                    raise ValueError
                end = min(end, stat.st_size - 1)
                status = 206
            except ValueError:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{stat.st_size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        length = end - start + 1
        self.send_response(status)
        content_type = "application/zip" if archive.suffix == ".zip" else "application/octet-stream"
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition",
                         f'attachment; filename="{archive.name}"')
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Last-Modified", formatdate(stat.st_mtime, usegmt=True))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{stat.st_size}")
        self.send_header("Content-Length", str(length))
        self.end_headers()
        if head_only:
            return
        try:
            with archive.open("rb") as stream:
                stream.seek(start)
                remaining = length
                while remaining:
                    block = stream.read(min(1024 * 1024, remaining))
                    if not block:
                        break
                    self.wfile.write(block)
                    remaining -= len(block)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_HEAD(self):
        request = urlparse(self.path)
        build_id, archive = self.download_path(request.path)
        if archive is None:
            self.send_error(404)
            return
        self.serve_download(build_id, archive, head_only=True)

    def do_GET(self):
        request = urlparse(self.path)
        if request.path == "/api/build":
            query = parse_qs(request.query)
            try:
                since = max(0, int(query.get("since", ["0"])[0]))
            except ValueError:
                since = 0
            source = query.get("source", [""])[0]
            body = json.dumps(snapshot(since, source)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if request.path == "/api/builds":
            body = json.dumps({"builds": available_builds()}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        build_id, archive = self.download_path(request.path)
        if archive is not None:
            self.serve_download(build_id, archive)
            return
        if request.path not in ("/", "/index.html"):
            self.send_error(404)
            return
        try:
            body = PAGE.read_bytes()
        except OSError:
            self.send_error(503, "Dashboard page is missing")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"dashboard: {self.address_string()} {fmt % args}", flush=True)


if __name__ == "__main__":
    host = os.environ.get("PMOS_DASHBOARD_HOST", "0.0.0.0")
    port = int(os.environ.get("PMOS_DASHBOARD_PORT", "8765"))
    print(f"Realme 6 build dashboard listening on {host}:{port}", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
