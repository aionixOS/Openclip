# Starter issues

Issues ready to open on GitHub. Each one has a title, labels and a body to paste in.
Delete an entry from this file once its GitHub issue exists.

Labels used: `good first issue`, `bug`, `documentation`, `frontend`, `backend`, `enhancement`, `help wanted`.

---

## Beginner-friendly

### 1. Frontend runs on port 5000 but README and start.sh say 3000
**Labels:** `bug`, `good first issue`, `frontend`

`frontend/package.json` starts Next.js with `-p 5000`, but `README.md`, `start.sh` and `backend/.env.example` (`CORS_ORIGIN`) all point to `http://localhost:3000`. New users open the wrong URL.

**To do:** choose one port (3000 is the Next.js default), then make `package.json`, `start.sh`, `README.md` and `.env.example` agree. Check that CORS in `backend/api.py` still allows it.

---

### 2. README documents an API endpoint that doesn't exist
**Labels:** `documentation`, `good first issue`

The README's API table lists `POST /api/clips/{id}/layout`, which isn't in `backend/api.py`. The table is also missing `GET /api/caption-styles`, `GET /api/settings` and `POST /api/settings`.

**To do:** update the API table so it matches `api.py`. Check against http://localhost:8000/docs.

---

### 3. README project structure is out of date
**Labels:** `documentation`, `good first issue`

The README's file tree doesn't show `settings.py`, `captioner.py`, `tracker.py` or `ffbin.py`. Frontend components have moved into subfolders (`components/dashboard/`, `components/create/` and so on), and `app/settings/page.tsx` is missing.

**To do:** regenerate the tree from the current repo, with a one-line description of each file.

---

### 4. Fix the broken "Star this repo" link and outdated model names in the README
**Labels:** `documentation`, `good first issue`

- The "Star this repo" link points to `github.com/aionix/openclip`, but the repo is `github.com/aionixos/Openclip`.
- FAQ Q1 mentions "Gemini 1.5 Flash", which has been retired. The app now defaults to `gemini-3.5-flash`.
- FAQ Q7 mentions a "Bug Report" template and GitHub Discussions, which don't exist yet (see issue 5).

**To do:** fix the link and update the FAQ text.

---

### 5. Add issue and pull request templates
**Labels:** `documentation`, `good first issue`

Add `.github/ISSUE_TEMPLATE/bug_report.md` (OS, steps to reproduce, expected and actual behaviour, backend log), `.github/ISSUE_TEMPLATE/feature_request.md` and `.github/pull_request_template.md` (linked issue, what changed, how it was tested, screenshots). See `CONTRIBUTING.md` for what reviewers expect.

---

### 6. Move ad-hoc test scripts out of `backend/`
**Labels:** `backend`, `good first issue`

`backend/test_gemini.py`, `test_genai.py`, `test_llm.py` and `test_quota.py` are manual scripts that call real APIs with your saved key. They aren't automated tests, and some use retired Gemini models. `backend/package-lock.json` is an empty npm lockfile that doesn't belong in a Python folder.

**To do:** move the useful scripts to `scripts/` (and update their model names), delete the rest, and delete `backend/package-lock.json`.

---

## Intermediate

### 7. Add a native Windows start script
**Labels:** `enhancement`, `help wanted`

`setup.sh` and `start.sh` need Git Bash or WSL. Add `setup.ps1` and `start.ps1` that do the same steps in PowerShell: check dependencies, create the venv, install packages, and start both servers. Document them in the README.

---

### 8. Add an automated test suite and CI
**Labels:** `backend`, `enhancement`, `help wanted`

There are no automated tests yet. Set up `pytest` with tests that need no network or API key, for example:
- VTT parsing in `transcriber.py`
- `ffbin.py` path resolution (mock `shutil.which`)
- settings encrypt/decrypt round trip in `settings.py`

Then add a GitHub Actions workflow that runs `pytest` and `npm run lint` on every PR.

---

### 9. Show a clear error when FFmpeg or yt-dlp is missing
**Labels:** `backend`, `frontend`, `enhancement`

If FFmpeg isn't installed, `ffbin` falls back to the bare name, and the pipeline fails partway through with a raw subprocess error. Add a `GET /api/health` endpoint that reports whether `ffmpeg`, `ffprobe` and `yt-dlp` are available. Show a banner in the frontend (like `SettingsWarning.tsx`) with install instructions when one is missing.

---

### 10. Export presets for TikTok, Reels and Shorts
**Labels:** `enhancement`, `backend`, `frontend`

This is on the roadmap. Let users pick an export preset (resolution, max duration, bitrate) per project. Store the preset with the project and apply it in the FFmpeg render step. Open a design comment on this issue before you start.

---

### 11. Batch processing for multiple URLs
**Labels:** `enhancement`, `backend`, `frontend`

This is on the roadmap. Let users paste several YouTube URLs at once and queue them so only one runs at a time, to keep CPU usage reasonable. Show queue position on the dashboard.

---

### 12. Refresh `context.md`
**Labels:** `documentation`

`context.md` was last updated in March 2026 (Phase 4.0). Update it to cover the current architecture (captioner, settings encryption, `ffbin`) so new contributors can rely on it, or merge the useful parts into the README and remove it.
