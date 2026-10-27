import os
import shutil

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_LOCAL_BIN = os.path.join(_BACKEND_DIR, "bin")

def get_ffmpeg_dir() -> str:
    """Return directory containing ffmpeg and ffprobe."""
    local_ffmpeg = os.path.join(_LOCAL_BIN, "ffmpeg.exe")
    if os.path.isfile(local_ffmpeg):
        return _LOCAL_BIN
    which = shutil.which("ffmpeg")
    if which:
        return os.path.dirname(which)
    # Search winget packages dynamically if not in local bin or PATH
    winget_base = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
    if os.path.isdir(winget_base):
        for root, dirs, files in os.walk(winget_base):
            if "ffmpeg.exe" in files:
                return root
    return _LOCAL_BIN

def get_ffmpeg_exe() -> str:
    """Return full path to ffmpeg executable."""
    local = os.path.join(_LOCAL_BIN, "ffmpeg.exe")
    if os.path.isfile(local):
        return local
    which = shutil.which("ffmpeg")
    if which:
        return which
    return os.path.join(get_ffmpeg_dir(), "ffmpeg.exe")

def get_ffprobe_exe() -> str:
    """Return full path to ffprobe executable."""
    local = os.path.join(_LOCAL_BIN, "ffprobe.exe")
    if os.path.isfile(local):
        return local
    which = shutil.which("ffprobe")
    if which:
        return which
    return os.path.join(get_ffmpeg_dir(), "ffprobe.exe")
