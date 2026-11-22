"""
ffbin.py — Locate the ffmpeg / ffprobe / yt-dlp executables in a cross-platform way.

Search order for ffmpeg / ffprobe:
    1. ``backend/bin/ffmpeg/`` — where the in-app installer puts them
    2. ``PATH`` (macOS / Linux / any PATH install)
    3. the winget install location on Windows (any FFmpeg version)

yt-dlp is looked up next to the running Python first (the project's
virtualenv, where ``pip install yt-dlp`` puts it), then on ``PATH``.
"""

import glob
import os
import shutil
import sys

_EXE = ".exe" if os.name == "nt" else ""

#: Folder the in-app installer downloads FFmpeg into (gitignored via backend/bin/).
LOCAL_FFMPEG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin", "ffmpeg")

_WINGET_GLOB = os.path.expandvars(
    r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\ffmpeg-*\bin"
)


def _find(name: str) -> str | None:
    local = os.path.join(LOCAL_FFMPEG_DIR, name + _EXE)
    if os.path.isfile(local):
        return local
    found = shutil.which(name)
    if found:
        return found
    if os.name == "nt":
        for bin_dir in sorted(glob.glob(_WINGET_GLOB), reverse=True):
            candidate = os.path.join(bin_dir, f"{name}.exe")
            if os.path.isfile(candidate):
                return candidate
    return None


def find_ffmpeg() -> str | None:
    """Full path to ffmpeg, or None if it isn't installed."""
    return _find("ffmpeg")


def find_ffprobe() -> str | None:
    """Full path to ffprobe, or None if it isn't installed."""
    return _find("ffprobe")


def find_ytdlp() -> str | None:
    """Full path to yt-dlp, or None if it isn't installed."""
    scripts_dir = os.path.dirname(sys.executable)  # venv/Scripts or venv/bin
    local = os.path.join(scripts_dir, "yt-dlp" + _EXE)
    if os.path.isfile(local):
        return local
    return shutil.which("yt-dlp")


# The helpers below always return something runnable so callers can pass the
# result straight to subprocess; if the tool is missing, subprocess raises a
# clear "not found" error (and /api/system/status reports it to the UI).

def ffmpeg() -> str:
    return find_ffmpeg() or "ffmpeg"


def ffprobe() -> str:
    return find_ffprobe() or "ffprobe"


def ytdlp() -> str:
    return find_ytdlp() or "yt-dlp"


def ffmpeg_dir() -> str:
    return os.path.dirname(ffmpeg()) or "."
