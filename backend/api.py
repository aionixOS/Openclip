"""
api.py — FastAPI application for OpenClip.

😂 Seriously, are you going to read this full !

This is the main entry-point for the backend.  It wires together the
database, downloader, clipper, transcriber, LLM, and settings modules
behind a REST + WebSocket API that the Next.js frontend consumes.

Pipeline stages (v2.0 — AI-powered):
    1. **Download**     — yt-dlp fetches the YouTube video.
    2. **Transcribe**   — YouTube captions or local Whisper.
    3. **Analyze**      — LLM suggests 5-8 best clip timestamps.
    4. **Cut clips**    — FFmpeg stream-copy at LLM timestamps.
    5. **Save**         — clip records persisted to SQLite.

Architecture notes:
    • ``_ws_connections`` is a dict mapping ``project_id`` to a *set* of
      connected ``WebSocket`` objects.  The background task iterates
      over this set to broadcast progress.
    • All DB calls are ``await``-ed because ``database.py`` uses
      ``aiosqlite``.
    • The download, FFmpeg, and Whisper work is CPU/IO-bound, so it is
      run inside ``asyncio.to_thread`` to avoid blocking the event loop.
"""

import os
import re
import json
import asyncio
import shutil
import logging
from typing import Optional

from fastapi import (  # type: ignore
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    HTTPException,
    Request,
    BackgroundTasks,
)
from fastapi.staticfiles import StaticFiles  # type: ignore
from fastapi.middleware.cors import CORSMiddleware  # type: ignore
from pydantic import BaseModel  # type: ignore
from dotenv import load_dotenv  # type: ignore

load_dotenv()

import ffbin  # type: ignore

# Make sure ffmpeg is on PATH for libraries that call it by name (e.g. Whisper):
# the in-app installer's folder first, plus wherever ffbin found ffmpeg.
_ffmpeg_dirs = [ffbin.LOCAL_FFMPEG_DIR]
if ffbin.find_ffmpeg():
    _ffmpeg_dirs.append(ffbin.ffmpeg_dir())
os.environ["PATH"] = os.pathsep.join(_ffmpeg_dirs + [os.environ.get("PATH", "")])

# Internal modules
import database  # type: ignore
import downloader  # type: ignore
import clipper  # type: ignore
import transcriber  # type: ignore
import llm  # type: ignore
import reframer # type: ignore
import captioner # type: ignore
import settings as settings_mod  # type: ignore
import system_setup  # type: ignore

import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="OpenClip API",
    description="Local-first video clipping engine by AIONIX",
    version="0.1.0",
)

# Allow the Next.js frontend dev server
_allowed_origins = [
    "http://localhost:3000",
    "http://localhost:5000",
]
_replit_domain = os.environ.get("REPLIT_DEV_DOMAIN")
if _replit_domain:
    _allowed_origins.append(f"https://{_replit_domain}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=r"https://.*\.replit\.dev",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Base directory for all temporary video / clip files
TMP_DIR = os.getenv("TMP_DIR", os.path.join(os.path.dirname(__file__), "..", "tmp"))
os.makedirs(TMP_DIR, exist_ok=True)

app.mount("/files", StaticFiles(directory=TMP_DIR), name="files")


# ---------------------------------------------------------------------------
# WebSocket connection registry
# ---------------------------------------------------------------------------

_ws_connections: dict[str, set[WebSocket]] = {}

# Latest progress per project, sent to a socket as soon as it connects so a
# page that opens (or reconnects) mid-run doesn't sit on "Connecting...".
_last_progress: dict[str, dict] = {}

# Projects whose pipeline is running in this process (guards double starts).
_active_pipelines: set[str] = set()


async def _broadcast(project_id: str, stage: str, percent: float, message: str) -> None:
    """
    Send a progress update to every WebSocket client listening for
    the given project.

    Args:
        project_id: UUID of the project.
        stage:      Pipeline stage name (download / clipping / done / error).
        percent:    Progress 0–100.
        message:    Human-readable status text.
    """
    payload = {"stage": stage, "percent": percent, "message": message}
    _last_progress[project_id] = payload
    dead: list[WebSocket] = []
    for ws in _ws_connections.get(project_id, set()):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    # Clean up dead connections
    for ws in dead:
        _ws_connections.get(project_id, set()).discard(ws)


# ---------------------------------------------------------------------------
# Startup event — initialise the database
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def on_startup() -> None:
    """Ensure the SQLite tables exist when the server starts."""
    await database.init_db()
    os.makedirs(TMP_DIR, exist_ok=True)
    # Pipelines run inside this process, so anything still "running" now was
    # cut off by a restart or crash. Mark it so the UI offers Retry instead of
    # spinning forever.
    n = await database.mark_interrupted_projects(INTERRUPTED_MESSAGE)
    if n:
        logger.warning("Marked %d interrupted project(s) as failed", n)
    logger.info("Database initialised, tmp dir ready at %s", TMP_DIR)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class CreateProjectRequest(BaseModel):
    """Payload for creating a new project."""
    youtube_url: str


class CreateProjectResponse(BaseModel):
    """Returned immediately after project creation."""
    project_id: str
    status: str


class ProjectListItem(BaseModel):
    """One item in the projects list."""
    id: str
    title: Optional[str] = None
    youtube_url: str
    status: str
    created_at: str
    error_message: Optional[str] = None
    clip_count: int


class ClipResponse(BaseModel):
    """Serialised clip record."""
    id: str
    project_id: str
    file_path: str
    start_time: float
    end_time: float
    duration: float
    reframed: bool
    captioned: bool
    title: Optional[str] = None
    reason: Optional[str] = None
    layout_mode: Optional[str] = None
    needs_user_confirm: bool = False
    hashtags: list[str] = []
    tags: list[str] = []
    created_at: str


class ProjectDetailResponse(BaseModel):
    """Full project detail including nested clips."""
    id: str
    title: Optional[str] = None
    youtube_url: str
    status: str
    created_at: str
    error_message: Optional[str] = None
    clips: list[ClipResponse] = []


# ---------------------------------------------------------------------------
# Background processing pipeline
# ---------------------------------------------------------------------------

INTERRUPTED_MESSAGE = (
    "Interrupted: the backend stopped while this project was running. "
    "Click Retry to continue where it left off."
)


class PipelineError(Exception):
    """A pipeline failure with a message meant for the user."""


def _read_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_json(path: str, data) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)  # atomic, so a crash never leaves half a checkpoint


async def _run_pipeline(project_id: str, youtube_url: str) -> None:
    """
    Execute the full AI-powered pipeline in the background.

    Steps:
        1. Download the video using yt-dlp.
        2. Extract transcript (YouTube captions -> Gemini Live -> Whisper).
        3. Send transcript to LLM for clip suggestions.
        4. Cut, reframe and caption each clip.
        5. Save clip records to the database.

    Each step leaves a checkpoint in the project folder (video.json,
    transcript.json, suggestions.json, and the saved clips), so running the
    pipeline again for the same project resumes after the last finished step.
    """
    if project_id in _active_pipelines:
        return
    _active_pipelines.add(project_id)

    project_dir = os.path.join(TMP_DIR, project_id)
    clips_dir = os.path.join(project_dir, "clips")
    os.makedirs(clips_dir, exist_ok=True)
    video_ckpt = os.path.join(project_dir, "video.json")
    transcript_ckpt = os.path.join(project_dir, "transcript.json")
    suggestions_ckpt = os.path.join(project_dir, "suggestions.json")

    async def fail(message: str) -> None:
        await database.update_project_status(project_id, "error", message)
        await _broadcast(project_id, "error", 0, message)

    try:
        project = await database.get_project(project_id)
        if project is None:
            return

        # Capture the running event loop for threadsafe callbacks
        loop = asyncio.get_running_loop()

        # ---- STEP 1: Download ----
        video = _read_json(video_ckpt)
        if video and os.path.isfile(os.path.join(project_dir, video.get("file", ""))):
            await _broadcast(project_id, "downloading", 25, "Video already downloaded, skipping download")
        else:
            await database.update_project_status(project_id, "downloading")
            await _broadcast(project_id, "downloading", 5, "Starting download…")

            def download_progress(percent: float, msg: str):
                asyncio.run_coroutine_threadsafe(
                    _broadcast(project_id, "downloading", min(percent * 0.2 + 5, 25), msg),
                    loop,
                )

            try:
                result = await asyncio.to_thread(
                    downloader.download_video, youtube_url, project_dir, download_progress,
                )
            except Exception as exc:
                logger.exception("Download failed for %s", project_id)
                raise PipelineError(f"Download failed: {exc}") from exc
            video = {
                "file": os.path.basename(result["file_path"]),
                "title": result["title"],
                "duration": result["duration_seconds"],
            }
            _write_json(video_ckpt, video)
            await database.update_project_title(project_id, video["title"])
            await _broadcast(project_id, "downloading", 25, "Download complete")

        file_path = os.path.join(project_dir, video["file"])
        video_duration = float(video["duration"])

        provider = await settings_mod.get_setting("llm_provider") or "openai"
        api_key = await settings_mod.get_setting("llm_api_key") or ""
        model = await settings_mod.get_setting("llm_model") or ""

        # ---- STEP 2: Extract Transcript ----
        transcript_segments = _read_json(transcript_ckpt)
        if transcript_segments:
            await _broadcast(project_id, "transcribing", 50, "Transcript already extracted, skipping")
        else:
            await database.update_project_status(project_id, "transcribing")
            await _broadcast(project_id, "transcribing", 30, "Extracting transcript…")

            def transcript_progress(percent: float, msg: str):
                scaled = 30 + (percent / 100) * 20  # 30-50 range
                asyncio.run_coroutine_threadsafe(
                    _broadcast(project_id, "transcribing", scaled, msg),
                    loop,
                )

            gemini_key = api_key if provider == "gemini" else os.environ.get("GEMINI_API_KEY", "")
            transcript_segments = await transcriber.extract_captions(
                youtube_url,
                file_path,
                progress_callback=transcript_progress,
                gemini_api_key=gemini_key,
                whisper_model=await settings_mod.get_setting("whisper_model") or "base",
            )
            if not transcript_segments:
                raise PipelineError(
                    "Could not get a transcript: this video has no captions and speech-to-text failed. "
                    "Add a Gemini API key in Settings to transcribe videos without captions."
                )
            _write_json(transcript_ckpt, transcript_segments)
            await _broadcast(project_id, "transcribing", 50, "Transcript ready")

        # ---- STEP 3: LLM Clip Suggestions ----
        suggestions = _read_json(suggestions_ckpt)
        if suggestions:
            await _broadcast(project_id, "analyzing", 75, f"Using the {len(suggestions)} clip moments found earlier")
        else:
            await database.update_project_status(project_id, "analyzing")
            await _broadcast(project_id, "analyzing", 55, "AI analyzing video…")

            def analyze_progress(stage: str, percent: float, msg: str):
                asyncio.run_coroutine_threadsafe(
                    _broadcast(project_id, stage, percent, msg),
                    loop,
                )

            try:
                suggestions = await llm.get_clip_suggestions(
                    transcript_segments, provider, api_key, model, video_duration,
                    progress_callback=analyze_progress,
                )
            except Exception as e:
                logger.exception("LLM step failed for %s", project_id)
                raise PipelineError(f"AI step failed: {llm.friendly_error(e)}") from e

            if not suggestions:
                raise PipelineError("AI could not find clip moments. Try a different video or another model.")
            _write_json(suggestions_ckpt, suggestions)
            await _broadcast(project_id, "analyzing", 75, f"Found {len(suggestions)} clip suggestions")

        # ---- STEP 4: Cut, reframe and caption each clip ----
        await database.update_project_status(project_id, "processing")
        caption_style = await settings_mod.get_setting("caption_style")

        done_starts = {round(c["start_time"], 2) for c in (await database.get_project(project_id) or {}).get("clips", [])}
        failed: list[str] = []
        total = len(suggestions)

        for i, suggestion in enumerate(suggestions):
            label = f"clip {i+1} of {total}"
            if round(suggestion["start"], 2) in done_starts:
                continue  # made on an earlier run

            await _broadcast(project_id, "processing", 75 + (i / total * 20), f"Processing {label}...")
            try:
                clip = await reframer.process_clip(file_path, suggestion, clips_dir, project_id)
            except Exception as exc:
                logger.exception("Clip %d failed for %s", i + 1, project_id)
                failed.append(f"{i+1}")
                await _broadcast(project_id, "processing", 75 + ((i + 1) / total * 20),
                                 f"Warning: {label} failed and was skipped ({str(exc)[:120]})")
                continue

            # Captions are a bonus: if burning fails, keep the clip without them.
            captioned = False
            if caption_style and caption_style != "none":
                await _broadcast(project_id, "processing", 90 + (i / total * 8), f"Adding captions to {label}...")
                try:
                    captioned_clip = await captioner.burn_captions(
                        clip["file_path"], transcript_segments,
                        suggestion["start"], suggestion["end"], caption_style,
                    )
                    if captioned_clip != clip["file_path"]:
                        os.replace(captioned_clip, clip["file_path"])
                        captioned = True
                        clip["caption_style"] = caption_style
                except Exception as exc:
                    logger.exception("Captions failed for clip %d of %s", i + 1, project_id)
                    await _broadcast(project_id, "processing", 90 + (i / total * 8),
                                     f"Warning: captions failed for {label}, keeping it without captions")

            filename = os.path.basename(clip["file_path"])
            await database.save_clip(
                project_id=project_id,
                file_path=f"/files/{project_id}/clips/{filename}",
                start_time=clip["start_time"],
                end_time=clip["end_time"],
                title=clip.get("title"),
                reason=clip.get("reason"),
                viral_score=clip.get("viral_score"),
                face_count=clip.get("face_count"),
                layout_mode=clip.get("layout_mode"),
                caption_style=clip.get("caption_style"),
                needs_user_confirm=clip.get("needs_user_confirm", False),
                reframed=clip.get("reframed", True),
                captioned=captioned,
                hashtags=suggestion.get("hashtags", []),
                tags=suggestion.get("tags", []),
            )
            done_starts.add(round(suggestion["start"], 2))

        made = sum(1 for sgg in suggestions if round(sgg["start"], 2) in done_starts)
        if made == 0:
            raise PipelineError(f"None of the {total} clips could be made. Check the backend log, then click Retry.")

        note = None
        if failed:
            note = f"{made} of {total} clips were made; clip {', '.join(failed)} failed. Click Retry to try those again."
        await database.update_project_status(project_id, "done", note)
        await _broadcast(project_id, "done", 100, note or "Complete")

    except PipelineError as exc:
        await fail(str(exc))
    except Exception as exc:
        import traceback
        with open("error_trace.txt", "w") as f:
            f.write(traceback.format_exc())
        logger.exception("Pipeline failed for project %s", project_id)
        await fail(f"Pipeline error: {exc}")
    finally:
        _active_pipelines.discard(project_id)


# ---------------------------------------------------------------------------
# REST routes — Projects
# ---------------------------------------------------------------------------

@app.post("/api/projects", response_model=CreateProjectResponse, status_code=201)
async def create_project(
    body: CreateProjectRequest,
    background_tasks: BackgroundTasks,
):
    """
    Create a new project from a YouTube URL.

    The project row is inserted immediately and the pipeline is kicked
    off in the background.  The response is returned without waiting
    for the download/clip work to finish.
    """
    if not re.match(r"^(https?\:\/\/)?(www\.youtube\.com|youtu\.be)\/.+$", body.youtube_url):
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")

    result = await database.create_project(youtube_url=body.youtube_url)
    project_id = result["project_id"]

    # Fire-and-forget — runs after the response is sent
    background_tasks.add_task(_run_pipeline, project_id, body.youtube_url)

    return {"project_id": project_id, "status": "pending"}


@app.get("/api/projects", response_model=list[ProjectListItem])
async def list_projects():
    """Return all projects, newest first, with clip counts."""
    return await database.get_all_projects()


@app.get("/api/projects/{project_id}", response_model=ProjectDetailResponse)
async def get_project(project_id: str):
    """Get a single project by ID, including its clips."""
    project = await database.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str):
    """
    Delete a project and all of its clips (both DB rows and files).
    """
    project = await database.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    await database.delete_project(project_id)
    _last_progress.pop(project_id, None)

    # Clean up files on disk
    project_dir = os.path.join(TMP_DIR, project_id)
    if os.path.isdir(project_dir):
        shutil.rmtree(project_dir, ignore_errors=True)

    return {"success": True}


@app.post("/api/projects/{project_id}/retry", status_code=202)
async def retry_project(project_id: str, background_tasks: BackgroundTasks):
    """
    Run a failed or interrupted project again. Finished steps (download,
    transcript, clip moments, clips already made) are reused, so it picks up
    where it stopped.
    """
    project = await database.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project_id in _active_pipelines:
        raise HTTPException(status_code=409, detail="This project is already running")
    await database.update_project_status(project_id, "pending")
    _last_progress.pop(project_id, None)
    background_tasks.add_task(_run_pipeline, project_id, project["youtube_url"])
    return {"project_id": project_id, "status": "pending"}


# ---------------------------------------------------------------------------
# REST routes — System requirements (FFmpeg, yt-dlp, Python packages)
# ---------------------------------------------------------------------------

_LOCAL_ORIGIN = re.compile(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$")


@app.get("/api/health")
async def health():
    """Which system requirements are installed, plus any running install job."""
    status = await asyncio.to_thread(system_setup.check_status)
    return {**status, "install": system_setup.get_job()}


@app.post("/api/system/install", status_code=202)
async def install_requirements(request: Request):
    """
    Install every missing requirement in the background. Poll
    ``GET /api/system/install`` for progress.

    Only the local OpenClip UI may call this: the request must come from a
    localhost origin and carry the ``X-OpenClip-Install`` header (a custom
    header forces a CORS preflight, so other websites can't trigger it).
    """
    origin = request.headers.get("origin", "")
    if not _LOCAL_ORIGIN.match(origin) or request.headers.get("x-openclip-install") != "1":
        raise HTTPException(status_code=403, detail="Installs can only be started from the local OpenClip app")
    started, job = system_setup.start_install()
    return {"started": started, "install": job}


@app.get("/api/system/install")
async def install_progress():
    """Progress of the current (or last) install job."""
    return system_setup.get_job()


@app.get("/api/caption-styles")
async def list_caption_styles():
    def ass_to_hex(ass_color):
        if not ass_color: return None
        if len(ass_color) >= 10:
            return f"#{ass_color[8:10]}{ass_color[6:8]}{ass_color[4:6]}"
        return None

    styles = []
    for key, style in captioner.CAPTION_STYLES.items():
        styles.append({
            "key": key,
            "name": style["name"],
            "animation": style["animation"],
            "preview_colors": {
                "text": ass_to_hex(style.get("primary_color")),
                "highlight": ass_to_hex(style.get("highlight_color")),
                "background": ass_to_hex(style.get("bg_color")) if style.get("background") else None
            }
        })
    return styles

# ---------------------------------------------------------------------------
# REST routes — Settings
# ---------------------------------------------------------------------------

class UpdateSettingsRequest(BaseModel):
    """Payload for updating settings."""
    llm_provider: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None
    whisper_model: Optional[str] = None
    caption_style: Optional[str] = None


@app.get("/api/settings")
async def get_settings():
    """
    Return all settings.  API keys are **never** returned — only a
    boolean ``has_api_key`` flag.
    """
    return await settings_mod.get_all_settings()


@app.post("/api/settings")
async def update_settings(body: UpdateSettingsRequest):
    """
    Create or update one or more settings.
    """
    pairs = {
        "llm_provider": body.llm_provider,
        "llm_api_key": body.llm_api_key,
        "llm_model": body.llm_model,
        "whisper_model": body.whisper_model,
        "caption_style": body.caption_style,
    }
    for key, value in pairs.items():
        if value is not None:
            await settings_mod.set_setting(key, value)
    return {"success": True}


# ---------------------------------------------------------------------------
# WebSocket — real-time progress
# ---------------------------------------------------------------------------

@app.websocket("/ws/progress/{project_id}")
async def websocket_progress(websocket: WebSocket, project_id: str):
    """
    WebSocket endpoint that streams processing-progress updates to
    the frontend for a given project.

    Message format (JSON sent from server):
        {
          "stage":   "download" | "clipping" | "done" | "error",
          "percent": 0.0 – 100.0,
          "message": "human-readable status"
        }

    The connection stays open until the client disconnects.
    """
    await websocket.accept()

    # Register this socket
    if project_id not in _ws_connections:
        _ws_connections[project_id] = set()
    _ws_connections[project_id].add(websocket)

    try:
        if project_id in _last_progress:
            await websocket.send_json(_last_progress[project_id])
        # Stay alive — wait for the client to close or send pings
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _ws_connections.get(project_id, set()).discard(websocket)
        if project_id in _ws_connections and not _ws_connections[project_id]:
            _ws_connections.pop(project_id, None)


# ---------------------------------------------------------------------------
# Entrypoint (for development)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn  # type: ignore
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
