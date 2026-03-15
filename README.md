# OpenClip by AIONIX

![OpenClip Dashboard Preview](frontend\public\Screenshot 2026-03-15 205743.png)

> Open-source, local-first video clipping engine.
> Paste a YouTube URL → download → auto-clip → export.

[![GitHub Stars](https://img.shields.io/github/stars/aionix/openclip?style=social)](https://github.com/aionix/openclip)
[![License](https://img.shields.io/badge/license-TBD-blue)](LICENSE)
[![Built with AI](https://img.shields.io/badge/built%20with-AI-blueviolet)](https://github.com/aionix/openclip)
[![Age](https://img.shields.io/badge/founder%20age-17-ff6b6b)](https://github.com/aionix)

---

## 👋 About the Creator

Hey — I'm **AIONIX**, a **17-year-old** builder who is obsessed with AI and machine learning.

I'm on a mission to prove that powerful tools shouldn't cost money. OpenClip is my first major open-source project — built not by a team, not by a funded startup, but by a teenager with a laptop, a vision, and a lot of caffeine.

> **This project is just getting started.** The roadmap is ambitious and the best features are still being built. If you believe in open-source AI tooling, now is the time to get involved — star the repo, fork it, or just stick around. 🚀

---

## ⭐ Support the Project

If OpenClip saves you time (or money on paid tools), please consider leaving a **star** on GitHub — it genuinely helps more people discover this project and motivates continued development.

**[⭐ Star this repo](https://github.com/aionix/openclip)** — it takes 2 seconds and means a lot.

---

## What is OpenClip?

OpenClip is a **free, open-source, local-first** alternative to paid video clipping tools like OpusClip, Vidyo.ai, and Munch.

- No subscriptions. No watermarks. No cloud uploads.
- Everything runs **on your machine**.
- Powered by AI for smart clip detection.

---

## Tech Stack

| Layer            | Tool                           |
|------------------|--------------------------------|
| YouTube Download | yt-dlp (CLI)                   |
| Video Cutting    | FFmpeg (direct CLI subprocess) |
| Layout Detect    | Pillow / numpy                 |
| Face Tracking    | MediaPipe (Tasks API)          |
| Audio Tracking   | FFmpeg (astats RMS energy)     |
| Final Rendering  | FFmpeg (filter_complex)        |
| Backend          | Python (FastAPI)               |
| Frontend         | Next.js (React + TypeScript)   |
| Local Storage    | SQLite                         |

---

## Project Structure

```
openclip/
├── backend/
│   ├── api.py              ← FastAPI routes + WebSocket
│   ├── database.py         ← SQLite schema & CRUD
│   ├── downloader.py       ← yt-dlp integration
│   ├── clipper.py          ← FFmpeg clip generation
│   ├── reframer.py         ← 9:16 reframing via FFmpeg
│   ├── layout_detector.py  ← Smart screen & face layout detector
│   ├── speaker_detector.py ← Active speaker detection (Audio + Lips)
│   ├── transcriber.py      ← Caption generation (VTT/Whisper)
│   ├── llm.py              ← AI clip suggestions
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── page.tsx                ← Dashboard
│   │   ├── create/page.tsx         ← Create New
│   │   └── project/[id]/page.tsx   ← View Project
│   ├── components/
│   │   ├── ProjectCard.tsx
│   │   ├── ProgressBar.tsx
│   │   ├── ClipCard.tsx
│   │   └── VideoPlayer.tsx
│   ├── lib/
│   │   └── api.ts          ← Typed API client
│   └── package.json
├── data/
│   └── openclip.db         ← SQLite database (auto-created)
├── tmp/                    ← Downloaded/processed videos
└── README.md
```

---

## Quick Start

### Backend

```bash
cd backend
pip install -r requirements.txt
python api.py
# → http://localhost:8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

### Prerequisites

- **Python 3.10+**
- **Node.js 18+**
- **FFmpeg** installed and on PATH
- **yt-dlp** installed and on PATH

---

## API Endpoints

| Method | Path                            | Description                     |
|--------|---------------------------------|---------------------------------|
| GET    | `/api/projects`                 | List all projects               |
| POST   | `/api/projects`                 | Create new project + auto-start |
| GET    | `/api/projects/{id}`            | Get project details & clips     |
| DELETE | `/api/projects/{id}`            | Delete project & files          |
| POST   | `/api/clips/{id}/layout`        | Reprocess a clip's layout       |
| WS     | `/ws/progress/{id}`             | Real-time progress updates      |

---

## MVP Scope

✅ Paste YouTube URL → download via yt-dlp
✅ Extract captions (Manual → Auto → Whisper)
✅ AI-driven viral hook detection (LLM)
✅ Smart layout detection (Tutorial, Podcast, Panel, Single, None)
✅ Active speaker tracking via FFmpeg audio RMS
✅ Auto-cut and face-track into 9:16 clips (FFmpeg filter_complex + MediaPipe)
✅ Save project + rich clip metadata to SQLite
✅ Display clips in View Project screen
✅ Show history on Dashboard
✅ Real-time progress via WebSocket

---

## Roadmap

> OpenClip is actively being built. Here's what's coming next:

- [ ] Phase 3: Scene & silence-based auto clip detection
- [ ] Batch processing for multiple URLs
- [ ] Export presets (TikTok, Reels, Shorts)
- [ ] Custom branding / watermark overlay
- [ ] GUI installer for non-technical users

---

## Contributing

OpenClip is open to contributors of all levels. If you find a bug, have a feature idea, or want to help build the roadmap — open an issue or a PR. All contributions are welcome.

---

## License

Open-source. License TBD.

---

<p align="center">
  Built with 🤖 by <strong>AIONIX</strong> — age 17, just getting started.
</p>