# AGENTS.md — NurClipper (AI YouTube Shorts Automation)

## Project Overview

NurClipper is a web-based automation platform that transforms long YouTube videos/podcasts into YouTube Shorts (9:16 vertical, max 59s) and uploads them to YouTube and Facebook Reels. Pipeline: **Input URL → Analisa AI (Gemini) → Download (yt-dlp) → Potong (FFmpeg) → Upload (YouTube API) / Facebook Reels API**.

## Tech Stack

- **Backend:** Python 3.13, FastAPI, Uvicorn, SQLite, Pydantic, SSE-Starlette
- **Frontend:** Vanilla JS SPA, HTML5, CSS3 (CSS variables, glassmorphism, dark/light themes)
- **AI/Video:** Google Gemini 2.5 Flash, yt-dlp, FFmpeg, OpenAI Whisper (PyTorch)
- **Auth:** Google OAuth, YouTube Data API v3, Facebook Graph API v21.0 (Page Access Token)

## Development Commands

| Command | Description |
|---|---|
| `python web_server.py` | Start production server |
| `uvicorn web_server:app --reload --host 0.0.0.0 --port 8000` | Debug with auto-reload |
| `python analisa_youtube.py <URL>` | Run AI analysis standalone |
| `python download_youtube.py <URL>` | Download video standalone |
| `python potong_video.py <VIDEO_ID>` | Cut clips standalone |
| `python upload_youtube.py <VIDEO_ID>` | Upload clips standalone |
| `python upload_facebook.py <VIDEO_ID>` | Upload Reels to Facebook standalone |

## Key Conventions

### Code Style
- No comments in code unless necessary
- Indonesian language for UI text, prompts, variables
- Use `safe_print()` for Unicode-safe console output on Windows
- Windows cp1252 encoding fix: `sys.stdout.reconfigure(encoding='utf-8')`
- FFmpeg paths must be escaped for Windows

### Architecture
- Each pipeline stage is a standalone Python script (subprocess from web server)
- Background worker uses a single sequential thread (SQLite single-writer constraint)
- Real-time logs via SSE (not WebSockets)
- Database auto-migration on server startup (`migrate_db()`)

### Database
- **File:** `database_konten.db` (SQLite)
- **WAL mode** enabled for better concurrent read/write
- **Indexes:** `idx_moments_video_id`, `idx_moments_selected`, `idx_schedules_pending`
- **Table `videos`:** id, url, judul_video, channel_video, tanggal_analisis, status_analisis, status_download, status_potong, status_upload, status_facebook, error_message
- **Table `moments`:** id, video_id (FK), waktu_start, waktu_selesai, judul_menarik, hashtag_terbaik, deskripsi_pendek, is_uploaded, is_uploaded_fb, is_selected
- **Table `schedules`:** id, video_id (FK), stage, scheduled_at, repeat (once/daily/weekly), status, last_run, created_at
- Status values: `pending`, `processing`, `success`, `failed`

### Environment & Config
- API key in `environment.txt`: `GEMINI_API_KEY=...`
- App config in `config.json`: caption settings (model, font, size, etc.), Facebook settings (page_id, page_access_token, privacy)
- YouTube OAuth: `client_secrets.json` + `token.pickle` (auto-refresh)
- Facebook: Page Access Token from Graph API Explorer, no OAuth flow needed
- FFmpeg must be in PATH or in project root
- Output dirs: `videos_podcast/`, `clips_output/`

### Frontend
- Vanilla JS SPA with client-side routing
- SSE for real-time log streaming (`/api/logs/stream`)
- Theme toggle persisted in localStorage
- Inline editing for moment metadata
- No framework dependencies (no React/Vue/Svelte)

## Important Files

| File | Purpose |
|---|---|---|
| `web_server.py` | Main entry point (936 lines) |
| `config.json` | App config (caption + Facebook settings) |
| `analisa_youtube.py` | AI analysis with Gemini |
| `download_youtube.py` | yt-dlp downloader |
| `potong_video.py` | FFmpeg cutting + captioning |
| `upload_youtube.py` | YouTube Data API uploader (301 lines) |
| `upload_facebook.py` | Facebook Reels uploader (Resumable Upload API v21.0, 255 lines) |
| `autocaption.py` | Whisper subtitle pipeline |
| `web_static/app.js` | Frontend SPA logic (1114 lines) |
| `web_static/style.css` | Design system (1611 lines) |
| `web_static/index.html` | Main HTML page (607 lines) |

## Key Endpoints (v2.2.0 additions)
| Endpoint | Method | Description |
|---|---|---|
| `/api/reset/{video_id}` | POST | Reset semua status tahap ke `pending` |

## Pipeline Recovery
- If "all" stage pipeline fails mid-way, remaining stages are auto-reset to `pending`
- Worker loop has inner try/except that resets all statuses to `failed` on crash
- Periodic stale cleanup thread runs every 5 minutes
- Frontend has "Reset" button for manual recovery
- Startup resets any stale `processing` → `failed`
