"""
system_setup.py — Check for and install OpenClip's system requirements.

Used by the "Install" button in the frontend so beginners don't have to
install FFmpeg / yt-dlp by hand.

What gets checked:
    • FFmpeg + FFprobe   — video cutting / probing
    • yt-dlp             — YouTube downloads
    • Python packages    — everything in requirements.txt

How things are installed (no admin rights / sudo needed):
    • FFmpeg on Windows and Linux: the latest release build from
      github.com/BtbN/FFmpeg-Builds is downloaded, its SHA-256 is checked
      against the release's checksums.sha256, and only ffmpeg + ffprobe
      are extracted into ``backend/bin/ffmpeg/`` (gitignored). FFmpeg is
      downloaded to the user's own machine, never shipped in this repo.
    • FFmpeg on macOS: ``brew install ffmpeg`` (Homebrew required).
    • yt-dlp / Python packages: ``pip`` into the Python running the backend
      (the project's virtualenv).

The install runs in a background thread; progress is exposed through
``get_job()`` and polled by the frontend.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import logging
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import zipfile
from typing import Any, Callable

import httpx  # type: ignore

import ffbin  # type: ignore

logger = logging.getLogger(__name__)

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
REQUIREMENTS = os.path.join(BACKEND_DIR, "requirements.txt")
FFMPEG_RELEASE_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"

# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------

def _platform() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def _ffmpeg_build_target() -> str | None:
    """BtbN asset target for this machine, or None if there is no build."""
    machine = platform.machine().lower()
    plat = _platform()
    if plat == "windows":
        return "win64"  # also runs on Windows on ARM via emulation
    if plat == "linux":
        if machine in ("x86_64", "amd64"):
            return "linux64"
        if machine in ("aarch64", "arm64"):
            return "linuxarm64"
    return None


def _can_install_ffmpeg() -> bool:
    if _platform() == "macos":
        return shutil.which("brew") is not None
    return _ffmpeg_build_target() is not None


def _manual_ffmpeg_hint() -> str:
    return {
        "windows": "winget install Gyan.FFmpeg",
        "macos": "brew install ffmpeg",
        "linux": "sudo apt install ffmpeg",
    }[_platform()]


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def _requirement_names() -> list[str]:
    names: list[str] = []
    try:
        with open(REQUIREMENTS, encoding="utf-8") as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if not line or line.startswith("-"):
                    continue
                name = re.split(r"[\[<>=!~;\s]", line, maxsplit=1)[0]
                if name:
                    names.append(name)
    except FileNotFoundError:
        pass
    return names


def _missing_python_packages() -> list[str]:
    missing = []
    for name in _requirement_names():
        try:
            importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            missing.append(name)
    return missing


def check_status() -> dict[str, Any]:
    """Report which requirements are installed. Fast enough to call per request."""
    ffmpeg_path = ffbin.find_ffmpeg()
    ffprobe_path = ffbin.find_ffprobe()
    ytdlp_path = ffbin.find_ytdlp()
    missing_pkgs = _missing_python_packages()

    tools = [
        {
            "id": "ffmpeg",
            "name": "FFmpeg",
            "description": "Cuts and reframes your clips",
            "ok": bool(ffmpeg_path and ffprobe_path),
            "path": ffmpeg_path,
            "can_install": _can_install_ffmpeg(),
            "manual": _manual_ffmpeg_hint(),
        },
        {
            "id": "yt_dlp",
            "name": "yt-dlp",
            "description": "Downloads videos from YouTube",
            "ok": bool(ytdlp_path),
            "path": ytdlp_path,
            "can_install": True,
            "manual": "pip install yt-dlp",
        },
        {
            "id": "python_packages",
            "name": "Python packages",
            "description": "AI, captions and face tracking libraries",
            "ok": not missing_pkgs,
            "missing": missing_pkgs,
            "can_install": True,
            "manual": "pip install -r backend/requirements.txt",
        },
    ]
    return {
        "ready": all(t["ok"] for t in tools),
        "platform": _platform(),
        "tools": tools,
    }


# ---------------------------------------------------------------------------
# Install job state
# ---------------------------------------------------------------------------

_STEP_WEIGHTS = {"ffmpeg": 70.0, "yt_dlp": 10.0, "python_packages": 20.0}
_STEP_LABELS = {"ffmpeg": "FFmpeg", "yt_dlp": "yt-dlp", "python_packages": "Python packages"}

_lock = threading.Lock()
_job: dict[str, Any] = {
    "state": "idle",      # idle | running | done | error
    "percent": 0.0,
    "message": "",
    "steps": [],
    "error": None,
    "log": [],
}


def get_job() -> dict[str, Any]:
    with _lock:
        return get_job_unlocked()


def _log(line: str) -> None:
    line = line.rstrip()
    if not line:
        return
    logger.info("[installer] %s", line)
    with _lock:
        _job["log"].append(line)
        del _job["log"][:-200]


def _set_step(step_id: str, **fields: Any) -> None:
    with _lock:
        for s in _job["steps"]:
            if s["id"] == step_id:
                s.update(fields)
        total = sum(s["weight"] for s in _job["steps"]) or 1.0
        done = sum(s["weight"] * s["progress"] for s in _job["steps"])
        # Never let the ring go backwards
        _job["percent"] = max(_job["percent"], round(100.0 * done / total, 1))
        if "message" in fields:
            _job["message"] = fields["message"]


def start_install() -> tuple[bool, dict[str, Any]]:
    """
    Start installing whatever is missing. Returns (started, job).
    Does nothing if an install is already running or nothing is missing.
    """
    status = check_status()
    todo = [t for t in status["tools"] if not t["ok"] and t["can_install"]]
    with _lock:
        if _job["state"] == "running":
            return False, get_job_unlocked()
        if not todo:
            return False, get_job_unlocked()
        _job.update(
            state="running",
            percent=0.0,
            message="Starting…",
            error=None,
            log=[],
            steps=[
                {
                    "id": t["id"],
                    "name": _STEP_LABELS[t["id"]],
                    "state": "pending",   # pending | running | done | error
                    "progress": 0.0,
                    "detail": "",
                    "weight": _STEP_WEIGHTS[t["id"]],
                }
                for t in todo
            ],
        )
    threading.Thread(target=_run_install, name="openclip-installer", daemon=True).start()
    return True, get_job()


def get_job_unlocked() -> dict[str, Any]:
    return {**_job, "steps": [dict(s) for s in _job["steps"]], "log": list(_job["log"][-40:])}


def _run_install() -> None:
    runners: dict[str, Callable[[Callable[[float, str], None]], None]] = {
        "ffmpeg": _install_ffmpeg,
        "yt_dlp": _install_ytdlp,
        "python_packages": _install_python_packages,
    }
    step_ids = [s["id"] for s in get_job()["steps"]]
    for step_id in step_ids:
        name = _STEP_LABELS[step_id]
        _set_step(step_id, state="running", message=f"Installing {name}…")

        def report(fraction: float, detail: str, _id: str = step_id) -> None:
            _set_step(_id, progress=max(0.0, min(fraction, 0.99)), detail=detail, message=detail)

        try:
            runners[step_id](report)
        except Exception as exc:  # noqa: BLE001 — surface any failure to the UI
            logger.exception("Installing %s failed", name)
            _log(f"ERROR: {exc}")
            _set_step(step_id, state="error", detail=str(exc))
            with _lock:
                _job["state"] = "error"
                _job["error"] = f"Couldn't install {name}: {exc}"
                _job["message"] = _job["error"]
            return
        _set_step(step_id, state="done", progress=1.0, detail="Installed", message=f"{name} installed")

    final = check_status()
    with _lock:
        if final["ready"]:
            _job["state"] = "done"
            _job["percent"] = 100.0
            _job["message"] = "Everything is installed"
        else:
            still = ", ".join(t["name"] for t in final["tools"] if not t["ok"])
            _job["state"] = "error"
            _job["error"] = f"Still missing after install: {still}"
            _job["message"] = _job["error"]


# ---------------------------------------------------------------------------
# Subprocess helper with "creeping" progress for tools that don't report %
# ---------------------------------------------------------------------------

def _run_streaming(cmd: list[str], report: Callable[[float, str], None], label: str,
                   expected_seconds: float) -> None:
    _log("$ " + " ".join(cmd))
    start = time.monotonic()
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    assert proc.stdout is not None

    def pump() -> None:
        for line in proc.stdout:  # type: ignore[union-attr]
            _log(line)

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    # Tick on a timer (not per output line) so the ring keeps moving while the
    # tool is quiet, e.g. pip unpacking thousands of files.
    while proc.poll() is None:
        elapsed = time.monotonic() - start
        # Approaches ~95% asymptotically; real completion sets it to 100%
        report(0.95 * (1 - math.exp(-elapsed / expected_seconds)), label)
        time.sleep(0.4)
    reader.join(timeout=5)
    if proc.returncode != 0:
        raise RuntimeError(f"{os.path.basename(cmd[0])} exited with code {proc.returncode}")


# ---------------------------------------------------------------------------
# Installers
# ---------------------------------------------------------------------------

def _install_ytdlp(report: Callable[[float, str], None]) -> None:
    report(0.05, "Installing yt-dlp…")
    _run_streaming(
        # --force-reinstall repairs a half-installed yt-dlp (metadata present, exe missing)
        [sys.executable, "-m", "pip", "install", "--upgrade", "--force-reinstall", "--no-deps",
         "--disable-pip-version-check", "yt-dlp"],
        report, "Installing yt-dlp…", expected_seconds=15,
    )
    if not ffbin.find_ytdlp():
        raise RuntimeError("yt-dlp was installed but can't be found")


def _install_python_packages(report: Callable[[float, str], None]) -> None:
    report(0.02, "Installing Python packages… (this can take a few minutes)")
    _run_streaming(
        [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-r", REQUIREMENTS],
        report, "Installing Python packages… (this can take a few minutes)", expected_seconds=180,
    )


def _install_ffmpeg(report: Callable[[float, str], None]) -> None:
    if _platform() == "macos":
        report(0.02, "Installing FFmpeg with Homebrew…")
        _run_streaming(["brew", "install", "ffmpeg"], report, "Installing FFmpeg with Homebrew…",
                       expected_seconds=120)
    else:
        _download_ffmpeg_build(report)
    if not (ffbin.find_ffmpeg() and ffbin.find_ffprobe()):
        raise RuntimeError("FFmpeg was installed but can't be found")


def _download_ffmpeg_build(report: Callable[[float, str], None]) -> None:
    target = _ffmpeg_build_target()
    if not target:
        raise RuntimeError(f"No prebuilt FFmpeg for this system; run: {_manual_ffmpeg_hint()}")

    report(0.01, "Finding the latest FFmpeg release…")
    pattern = re.compile(
        rf"^ffmpeg-n(\d+(?:\.\d+)*)-latest-{re.escape(target)}-gpl-[\d.]+\.(?:zip|tar\.xz)$"
    )
    with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(30.0, read=60.0),
                      headers={"User-Agent": "OpenClip-installer"}) as client:
        release = client.get(FFMPEG_RELEASE_API)
        release.raise_for_status()
        assets = release.json().get("assets", [])

        builds = []
        checksums_url = None
        for a in assets:
            m = pattern.match(a["name"])
            if m:
                builds.append((tuple(int(x) for x in m.group(1).split(".")), a))
            elif a["name"] == "checksums.sha256":
                checksums_url = a["browser_download_url"]
        if not builds:
            raise RuntimeError("Couldn't find an FFmpeg build for this system")
        if not checksums_url:
            raise RuntimeError("FFmpeg release has no checksums; refusing to install it")
        _, asset = max(builds, key=lambda b: b[0])
        name, url, size = asset["name"], asset["browser_download_url"], asset.get("size") or 0

        sums = client.get(checksums_url)
        sums.raise_for_status()
        expected = None
        for line in sums.text.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*") == name:
                expected = parts[0].lower()
        if not expected:
            raise RuntimeError(f"No checksum listed for {name}")

        os.makedirs(ffbin.LOCAL_FFMPEG_DIR, exist_ok=True)
        archive_path = os.path.join(os.path.dirname(ffbin.LOCAL_FFMPEG_DIR), name + ".part")
        _log(f"Downloading {url}")
        sha = hashlib.sha256()
        done = 0
        try:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length") or size or 0)
                with open(archive_path, "wb") as out:
                    last = 0.0
                    for chunk in resp.iter_bytes(1024 * 256):
                        out.write(chunk)
                        sha.update(chunk)
                        done += len(chunk)
                        now = time.monotonic()
                        if total and now - last > 0.2:
                            last = now
                            report(0.02 + 0.88 * done / total,
                                   f"Downloading FFmpeg… {done / 1e6:.0f} / {total / 1e6:.0f} MB")

            report(0.91, "Verifying download…")
            if sha.hexdigest().lower() != expected:
                raise RuntimeError("Downloaded FFmpeg failed its checksum check")
            _log("Checksum OK")

            report(0.93, "Unpacking FFmpeg…")
            _extract_ffmpeg(archive_path)
        finally:
            try:
                os.remove(archive_path)
            except OSError:
                pass

    report(0.98, "Checking FFmpeg works…")
    result = subprocess.run([ffbin.find_ffmpeg() or "ffmpeg", "-version"],
                            capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError("FFmpeg was unpacked but doesn't run")
    _log(result.stdout.splitlines()[0] if result.stdout else "ffmpeg OK")


def _extract_ffmpeg(archive_path: str) -> None:
    """Pull just bin/ffmpeg and bin/ffprobe out of the archive into LOCAL_FFMPEG_DIR."""
    exe = ".exe" if os.name == "nt" else ""
    wanted = {f"ffmpeg{exe}", f"ffprobe{exe}"}
    found: set[str] = set()

    def write(name: str, data_stream) -> None:
        dest = os.path.join(ffbin.LOCAL_FFMPEG_DIR, name)
        tmp = dest + ".tmp"
        with open(tmp, "wb") as out:
            shutil.copyfileobj(data_stream, out, 1024 * 1024)
        os.chmod(tmp, 0o755)
        os.replace(tmp, dest)
        found.add(name)

    if archive_path.endswith(".zip.part"):
        with zipfile.ZipFile(archive_path) as zf:
            for info in zf.infolist():
                parts = info.filename.replace("\\", "/").split("/")
                if len(parts) >= 2 and parts[-2] == "bin" and parts[-1] in wanted:
                    with zf.open(info) as src:
                        write(parts[-1], src)
    else:
        with tarfile.open(archive_path, "r:xz") as tf:
            for member in tf.getmembers():
                parts = member.name.split("/")
                if member.isfile() and len(parts) >= 2 and parts[-2] == "bin" and parts[-1] in wanted:
                    src = tf.extractfile(member)
                    if src:
                        write(parts[-1], src)

    if found != wanted:
        raise RuntimeError(f"Archive is missing {', '.join(sorted(wanted - found))}")
