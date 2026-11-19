# Contributing to OpenClip

Thanks for your interest in OpenClip! Contributors of every level are welcome, whether you write Python, TypeScript or docs, or you just found a bug.

## Ways to contribute

- **Report a bug:** open an issue with the steps to reproduce it, what you expected, what happened, your OS, and the backend terminal error.
- **Suggest a feature:** open an issue describing the problem it solves before writing code, so we can agree on the approach.
- **Pick up an issue:** look for the `good first issue`, `frontend`, `backend` and `documentation` labels.
- **Improve the docs:** typo fixes and clearer setup steps are always welcome.

## Before you start

1. Comment on the issue ("I'd like to work on this") and wait to be assigned. This stops two people from building the same thing.
2. If there's no issue for your change, open one first. Small fixes like typos don't need one.
3. Keep one PR to one change. Small PRs get reviewed and merged much faster.

## Local setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- FFmpeg on your `PATH` (`ffmpeg -version` must work). OpenClip does **not** ship FFmpeg binaries.
  - macOS: `brew install ffmpeg`
  - Ubuntu/Debian: `sudo apt install ffmpeg`
  - Windows: `winget install Gyan.FFmpeg`, then restart your terminal
- An API key for one LLM provider (Gemini, OpenAI or Anthropic), or [Ollama](https://ollama.com) running locally

### Install and run

```bash
git clone https://github.com/<your-username>/Openclip.git
cd Openclip
bash setup.sh   # checks dependencies, creates .env files, installs packages
bash start.sh   # starts backend (port 8000) and frontend
```

On Windows, run these from Git Bash or WSL.

The frontend dev server listens on the port printed by `npm run dev` (currently **5000**). API docs are at http://localhost:8000/docs.

Open **Settings** in the app, choose a provider and paste your API key. Keys are encrypted and stored locally in `data/`.

### Running the parts separately

```bash
# Backend
cd backend
source .venv/bin/activate        # Windows: source .venv/Scripts/activate
python -m uvicorn api:app --reload --port 8000

# Frontend
cd frontend
npm run dev
```

## Project layout

| Path | What lives there |
|------|------------------|
| `backend/api.py` | FastAPI routes, WebSocket, the processing pipeline |
| `backend/downloader.py` | yt-dlp download |
| `backend/transcriber.py` | Captions (YouTube VTT, then Whisper fallback) |
| `backend/llm.py` | Clip suggestions from OpenAI / Anthropic / Gemini / Ollama |
| `backend/clipper.py`, `reframer.py`, `captioner.py` | FFmpeg cutting, 9:16 reframing, caption burn-in |
| `backend/layout_detector.py`, `speaker_detector.py`, `tracker.py` | Layout, face and active-speaker detection |
| `backend/ffbin.py` | Finds `ffmpeg` / `ffprobe`. Always use this instead of hardcoding paths |
| `backend/settings.py`, `database.py` | Encrypted settings and SQLite storage |
| `frontend/app/` | Next.js pages (dashboard, create, project, settings) |
| `frontend/components/` | UI components grouped by page |
| `frontend/lib/` | API client, WebSocket client, shared types |

## Coding guidelines

- **Cross-platform first.** The app must run on Windows, macOS and Linux. Never hardcode OS-specific paths; use `os.path.join` and `ffbin.ffmpeg()` / `ffbin.ffprobe()`.
- **Python:** follow PEP 8, add type hints to new functions, and use `logging` rather than `print`.
- **TypeScript:** keep shared types in `frontend/lib/types.ts`. Run `npm run lint` before pushing.
- **No secrets or large files.** Never commit API keys, `.env` files, videos, the `data/` or `tmp/` folders, `__pycache__`, or binaries.
- **No new heavy dependencies** without discussing them in the issue first.

## Commits and pull requests

1. Fork the repo and create a branch from `main`, for example `fix/ffmpeg-path-linux` or `feat/export-presets`.
2. Write clear commit messages that say what changed and why.
3. Before opening the PR, check that:
   - the backend starts and you processed at least one short video end to end (for pipeline changes)
   - `npm run lint` passes (for frontend changes)
   - you updated the README if setup or behaviour changed
4. Open a PR against `main` that links the issue (`Closes #12`), describes what you changed and how you tested it, and includes screenshots for UI changes.

### Review

- Every PR gets a response (merge, comment or change request) within **72 hours**. Exam periods may be slower.
- Expect review comments. They're about the code, not you.
- Once approved, the maintainer merges your PR.

## Licensing

OpenClip is MIT-licensed. By contributing, you agree your contribution is released under the same license. Don't add code or assets whose license isn't compatible with MIT (for example, GPL binaries).

## Questions?

Open a GitHub issue, or ask in the club Discord.
