"""
ffbin.py — Locate the ffmpeg / ffprobe executables in a cross-platform way.

Looks on PATH first (macOS / Linux / any PATH install), then falls back to
the winget install location used on Windows.
"""

import os
import shutil

_WINGET_BIN = os.path.expandvars(
    r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
)


def _find(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    winget = os.path.join(_WINGET_BIN, f"{name}.exe")
    if os.path.isfile(winget):
        return winget
    return name  # let subprocess raise a clear "not found" error


def ffmpeg() -> str:
    return _find("ffmpeg")


def ffprobe() -> str:
    return _find("ffprobe")


def ffmpeg_dir() -> str:
    return os.path.dirname(ffmpeg()) or "."
