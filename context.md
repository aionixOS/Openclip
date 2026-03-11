# OpenClip by AIONIX — Context File

> **Last updated:** 2026-03-10  
> **Phase:** 4.0 — Smart Layouts & Speaker Detection
> **Status:** Backend v4.0 complete (Dynamic reframing: tutorial, podcast, panel via audio+video tracking)

---

## Project Overview

OpenClip is a local-first video clipping app that downloads YouTube videos
via yt-dlp, extracts transcripts, uses AI to identify the best clip
moments, and cuts them with FFmpeg. All data stays on the user's machine.

---

## How the App Works (End-to-End Pipeline)

```
User pastes YouTube URL
        │
        ▼
POST /api/projects  ←──── validates URL + checks yt-dlp/ffmpeg on PATH
        │
        ├──→ immediately returns { project_id, status: "pending" }
        │
        └──→ fires BackgroundTask: _run_pipeline()
                │
                ├── Step 1: DOWNLOAD (5-25%, status → "downloading")
                │     • yt-dlp subprocess downloads as MP4
                │     • progress parsed → WebSocket broadcast
                │     • title + duration extracted
                │
                ├── Step 2: TRANSCRIBE (30-50%, status → "transcribing")
                │     • Try YouTube auto-captions (yt-dlp --write-auto-sub)
                │     • Parse .vtt → segments [{start, end, text}]
                │     • Fallback: local Whisper (openai-whisper)
                │
                ├── Step 3: LLM ANALYZE (55-75%, status → "analyzing")
                │     • Send transcript + prompt to LLM
                │     • Supports: OpenAI, Anthropic, Gemini, Ollama
                │     • Returns 5-8 clip suggestions with titles
                │
                ├── Step 4: CUT CLIPS (80-95%, status → "processing")
                │     • Detect dominant layout (none, single, tutorial, podcast, panel)
                │     • FFmpeg extracts & tracks faces using MediaPipe
                │     • Map active speakers via audio RMS tracking
                │     • Assemble dynamic 9:16 vertical video via filter_complex
                │
                ├── Step 5: SAVE (100%, status → "done")
                │     • clips saved with title + reason
                │
                └── On error → status = "error", error broadcast
```

**WebSocket** clients connect to `/ws/progress/{project_id}` and receive
`{ stage, percent, message }` JSON at every step.

---

## Current Architecture

### Backend (Python / FastAPI) — `backend/`

| File                  | Purpose                               | Status        |
|-----------------------|---------------------------------------|---------------|
| `api.py`              | FastAPI routes + WebSocket + pipeline | ✅ Implemented |
| `database.py`         | Async SQLite (aiosqlite) CRUD         | ✅ Implemented |
| `downloader.py`       | yt-dlp video download + progress      | ✅ Implemented |
| `clipper.py`          | FFmpeg clip generation + ffprobe      | ✅ Implemented |
| `reframer.py`         | 9:16 vertical reframing orchestration | ✅ Implemented |
| `layout_detector.py`  | Pillow screen-region & count analyzer | ✅ Implemented |
| `speaker_detector.py` | Lip & FFmpeg audio speaker tracking   | ✅ Implemented |
| `transcriber.py`      | Priority captioning (VTT -> Whisper)  | ✅ Implemented |
| `llm.py`              | Multi-provider AI clip suggestion     | ✅ Implemented |
| `settings.py`         | Encrypted user settings (Fernet)      | ✅ Implemented |
| `requirements.txt`    | Python dependencies                   | ✅ Done        |

**Key wiring:**
- `api.py` imports `database`, `downloader`, `clipper`, `reframer`, `transcriber`, `llm`
- `database.py` uses async `aiosqlite` — all functions are `async def`
- `downloader.py` and `clipper.py` are synchronous, run via `asyncio.to_thread()` in `api.py`
- WebSocket connections stored in `_ws_connections: Dict[str, Set[WebSocket]]`
- Sync progress callbacks use `asyncio.run_coroutine_threadsafe()` to broadcast

### Frontend (Next.js + TypeScript) — `frontend/`

| File                          | Purpose                  | Status    |
|-------------------------------|--------------------------|-----------|
| `app/page.tsx`                | Dashboard                | Scaffold  |
| `app/create/page.tsx`         | Create New Project       | Scaffold  |
| `app/project/[id]/page.tsx`   | View Project             | Scaffold  |
| `components/ProjectCard.tsx`  | Project list card        | Scaffold  |
| `components/ProgressBar.tsx`  | Progress bar             | Scaffold  |
| `components/ClipCard.tsx`     | Clip metadata display    | Scaffold  |
| `components/VideoPlayer.tsx`  | YouTube iframe embed     | Scaffold  |
| `lib/api.ts`                  | Typed API client         | Scaffold  |

### Data directories

- `data/` — SQLite database (`openclip.db`, auto-created on startup)
- `tmp/` — Downloaded videos + clips, served via `/files` static mount
- `tmp/{project_id}/` — Full video file
- `tmp/{project_id}/clips/` — Clip segments (clip_001.mp4, clip_002.mp4, …)

---

## API Endpoints (Final)

| Method | Path                         | Description                           |
|--------|------------------------------|---------------------------------------|
| POST   | `/api/projects`              | Create project + start pipeline       |
| GET    | `/api/projects`              | List all projects (with clip_count)   |
| GET    | `/api/projects/{id}`         | Get project detail + clips array      |
| DELETE | `/api/projects/{id}`         | Delete project + files + clips        |
| GET    | `/api/settings`              | Get user LLM/Whisper settings         |
| POST   | `/api/settings`              | Update user settings (encrypt keys)   |
| POST   | `/api/clips/{id}/layout`     | Reprocess clip with forced layout mode|
| WS     | `/ws/progress/{id}`          | Real-time progress updates            |
| STATIC | `/files/{path}`              | Serve downloaded/clipped video files  |

---

## Data Models (SQLite)

**clips:** id, project_id, file_path, start_time, end_time, duration, reframed, captioned, title, reason, viral_score, face_count, `layout_mode` (e.g. tutorial/podcast/panel), `needs_user_confirm` (boolean), created_at
**settings:** key, value, updated_at

---

## Backend Packages (`requirements.txt`)

| Package            | Version      | Purpose                              |
|--------------------|-------------|---------------------------------------|
| `fastapi`          | 0.115.0     | Web framework (REST + WebSocket)      |
| `uvicorn[standard]`| 0.30.0      | ASGI server                           |
| `yt-dlp`           | 2024.8.6    | YouTube video downloading             |
| `aiosqlite`        | 0.20.0      | Async SQLite database access          |
| `Pillow`           | 11.1.0      | Image I/O and manipulation            |
| `numpy`            | 2.2.3       | Array and variance operations         |
| `mediapipe`        | 0.10.20     | Face/subject tracking                 |
| `pydantic`         | 2.9.0       | Request/response data validation      |
| `python-multipart` | 0.0.9       | Multipart form data parsing           |
| `websockets`       | 13.0        | WebSocket protocol support            |
| `python-dotenv`    | 1.0.1       | .env file loading                     |

> **System deps (not in requirements.txt):** FFmpeg, yt-dlp (must be on PATH)

---

## Environment Variables (via .env / python-dotenv)

| Variable  | Default                          | Description            |
|-----------|----------------------------------|------------------------|
| `DB_PATH` | `../data/openclip.db`            | SQLite database file   |
| `TMP_DIR` | `../tmp`                         | Video/clip storage dir |

---

## MVP Scope

✅ Paste YouTube URL → download via yt-dlp  
✅ Priority caption extraction (Manual → Auto → Whisper)
✅ LLM-based viral video moment detection (OpenAI/Anthropic/Gemini/Ollama)
✅ Detect dynamic layouts (Tutorial, Podcast, Panel, Single) via Pillow + MediaPipe
✅ Screen region extraction & active speaker tracking via FFmpeg RMS audio
✅ Auto-cut and dynamically reframe into 9:16 clips (FFmpeg filter_complex)
✅ Save project + rich clips (viral_score, layout_mode, face counts) to SQLite
✅ List projects with clip counts on Dashboard  
✅ View project detail with clips array  
✅ Delete project + cleanup files  
✅ Real-time progress via WebSocket  
✅ Static file serving for clips  

---

## Changelog

| Date       | Change |
|------------|--------|
| 2026-03-09 | Initial scaffold created |
| 2026-03-09 | **Phase 2:** Full backend implementation — `database.py` (async aiosqlite), `downloader.py` (yt-dlp subprocess + progress parsing), `clipper.py` (ffprobe + FFmpeg stream-copy), `api.py` (4 REST routes + WebSocket + background pipeline). Added `python-dotenv`, `StaticFiles` mount, URL validation, tool availability checks. |
| 2026-03-10 | **Phase 3:** Smart Pipeline Redesign — Replaced equal-segment fallback with multi-provider LLM clip suggestion (`llm.py`). Added intelligent 9:16 face-tracking using MediaPipe (`reframer.py`). Added prioritized fallback for extracting captions (`transcriber.py`). Database now stores `viral_score` and `face_count`. |
| 2026-03-10 | **Phase 4:** Smart Layouts — Added `layout_detector.py` and `speaker_detector.py` for advanced multi-face tracking and screen detection. Switched `opencv-python` dependency out for `Pillow` + Native `ffmpeg filter_complex` concatenations. |
