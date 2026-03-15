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
import asyncio
import shutil
import logging
from typing import Optional

from fastapi import (  # type: ignore
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    HTTPException,
    BackgroundTasks,
)
from fastapi.staticfiles import StaticFiles  # type: ignore
from fastapi.middleware.cors import CORSMiddleware  # type: ignore
from pydantic import BaseModel  # type: ignore
from dotenv import load_dotenv  # type: ignore

load_dotenv()

import os
# Ensure ffmpeg is available to all subprocesses (Linux/Replit paths)
_extra_paths = os.path.join(os.path.dirname(__file__), "bin")
os.environ["PATH"] = _extra_paths + ":" + os.environ.get("PATH", "")

# Internal modules
import database  # type: ignore
import downloader  # type: ignore
import clipper  # type: ignore
import transcriber  # type: ignore
import llm  # type: ignore
import reframer # type: ignore
import captioner # type: ignore
import settings as settings_mod  # type: ignore

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
    clips: list[ClipResponse] = []


# ---------------------------------------------------------------------------
# Background processing pipeline
# ---------------------------------------------------------------------------

async def _run_pipeline(project_id: str, youtube_url: str) -> None:
    """
    Execute the full AI-powered pipeline in the background.

    Steps:
        1. Download the video using yt-dlp.
        2. Extract transcript (YouTube captions → Whisper fallback).
        3. Send transcript to LLM for clip suggestions.
        4. Cut clips at LLM-suggested timestamps.
        5. Save clip records to the database.
    """
    project_dir = os.path.join(TMP_DIR, project_id)
    clips_dir = os.path.join(project_dir, "clips")
    os.makedirs(clips_dir, exist_ok=True)

    try:
        if await database.get_project(project_id) is None:
            return

        # Capture the running event loop for threadsafe callbacks
        loop = asyncio.get_running_loop()

        # ---- STEP 1: Download ----
        await database.update_project_status(project_id, "downloading")
        await _broadcast(project_id, "downloading", 5, "Starting download…")

        def download_progress(percent: float, msg: str):
            asyncio.run_coroutine_threadsafe(
                _broadcast(project_id, "downloading", min(percent * 0.2 + 5, 25), msg),
                loop,
            )

        result = await asyncio.to_thread(
            downloader.download_video,
            youtube_url,
            project_dir,
            download_progress,
        )

        file_path = result["file_path"]
        title = result["title"]
        video_duration = result["duration_seconds"]

        await database.update_project_title(project_id, title)
        await _broadcast(project_id, "downloading", 25, "Download complete")

        # ---- STEP 2: Extract Transcript ----
        await database.update_project_status(project_id, "transcribing")
        await _broadcast(project_id, "transcribing", 30, "Extracting transcript…")

        def transcript_progress(percent: float, msg: str):
            scaled = 30 + (percent / 100) * 20  # 30-50 range
            asyncio.run_coroutine_threadsafe(
                _broadcast(project_id, "transcribing", scaled, msg),
                loop,
            )

        transcript_segments = await transcriber.extract_captions(
            youtube_url,
            file_path,
            progress_callback=transcript_progress,
        )
        
        if not transcript_segments:
            await database.update_project_status(project_id, "error")
            await _broadcast(project_id, "error", 0, "Could not extract captions from this video.")
            return

        await _broadcast(project_id, "transcribing", 50, "Transcript ready")

        # ---- STEP 3: LLM Clip Suggestions ----
        await database.update_project_status(project_id, "analyzing")
        await _broadcast(project_id, "analyzing", 55, "AI analyzing video…")

        provider = await settings_mod.get_setting("llm_provider") or "openai"
        api_key = await settings_mod.get_setting("llm_api_key") or ""
        model = await settings_mod.get_setting("llm_model") or ""

        try:
            def analyze_progress(stage: str, percent: float, msg: str):
                asyncio.run_coroutine_threadsafe(
                    _broadcast(project_id, stage, percent, msg),
                    loop,
                )

            suggestions: list[dict] = await llm.get_clip_suggestions(
                transcript_segments, provider, api_key, model, video_duration,
                progress_callback=analyze_progress
            )

        except Exception as e:
            msg = str(e).lower()
            if "401" in msg or "403" in msg:
                err_msg = "Invalid API key. Check your settings."
            elif "429" in msg:
                err_msg = "Rate limit hit. Wait a moment and try again."
            else:
                err_msg = f"AI Error: {e}"
            await database.update_project_status(project_id, "error")
            await _broadcast(project_id, "error", 0, err_msg)
            return

        if not suggestions:
            await database.update_project_status(project_id, "error")
            await _broadcast(project_id, "error", 0, "AI could not find clip moments. Try a different video or check your API key.")
            return

        await _broadcast(
            project_id, "analyzing", 75,
            f"Found {len(suggestions)} clip suggestions",
        )

        # ---- STEP 4: Cut Clips & Reframe ----
        await database.update_project_status(project_id, "processing")

        for i, suggestion in enumerate(suggestions):
            progress_pct = 75 + (i / len(suggestions) * 20)
            await _broadcast(project_id, "processing", progress_pct, 
                             f"Processing clip {i+1} of {len(suggestions)}...")
            
            clip = await reframer.process_clip(
                file_path, suggestion, clips_dir, project_id
            )
            
            # STEP 5 — BURN CAPTIONS
            caption_style = await settings_mod.get_setting("caption_style")
            if caption_style and caption_style != "none":
                progress_pct = 90 + (i / len(suggestions) * 8)
                await _broadcast(project_id, "processing", progress_pct, 
                                 f"Adding captions to clip {i+1}...")
                captioned_clip = await captioner.burn_captions(
                    clip['file_path'],
                    transcript_segments,           # full transcript from Step 2
                    suggestion['start'],  # clip start time in original video
                    suggestion['end'],    # clip end time
                    caption_style
                )
                # Replace clip file with captioned version
                os.replace(captioned_clip, clip['file_path'])
                clip["caption_style"] = caption_style

            filename = os.path.basename(clip["file_path"])
            file_url = f"/files/{project_id}/clips/{filename}"

            await database.save_clip(
                project_id=project_id,
                file_path=file_url,
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
                hashtags=suggestion.get("hashtags", []),
                tags=suggestion.get("tags", []),
            )

        await database.update_project_status(project_id, "done")
        await _broadcast(project_id, "done", 100, "Complete")

    except Exception as exc:
        import traceback
        with open("error_trace.txt", "w") as f:
            f.write(traceback.format_exc())
            
        logger.exception("Pipeline failed for project %s", project_id)
        await database.update_project_status(project_id, "error")
        await _broadcast(
            project_id, "error", 0, f"Pipeline error: {exc}"
        )


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

    # Clean up files on disk
    project_dir = os.path.join(TMP_DIR, project_id)
    if os.path.isdir(project_dir):
        shutil.rmtree(project_dir, ignore_errors=True)

    return {"success": True}


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
