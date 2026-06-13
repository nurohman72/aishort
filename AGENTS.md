# AGENTS.md — NurClipper (AI YouTube Shorts Automation)

## Project Overview

NurClipper is a web-based automation platform that transforms long YouTube videos/podcasts into YouTube Shorts (9:16 vertical, max 59s). Pipeline: **Input URL → Analisa AI (Gemini) → Download (yt-dlp) → Potong (FFmpeg) → Upload (YouTube API)**.

## Tech Stack

- **Backend:** Python 3.13, FastAPI, Uvicorn, SQLite, Pydantic, SSE-Starlette
- **Frontend:** Vanilla JS SPA, HTML5, CSS3 (CSS variables, glassmorphism, dark/light themes)
- **AI/Video:** Google Gemini 2.5 Flash, yt-dlp, FFmpeg, OpenAI Whisper (PyTorch)
- **Auth:** Google OAuth, YouTube Data API v3

## Development Commands

| Command | Description |
|---|---|
| `python web_server.py` | Start production server |
| `uvicorn web_server:app --reload --host 0.0.0.0 --port 8000` | Debug with auto-reload |
| `python analisa_youtube.py <URL>` | Run AI analysis standalone |
| `python download_youtube.py <URL>` | Download video standalone |
| `python potong_video.py <VIDEO_ID>` | Cut clips standalone |
| `python upload_youtube.py <VIDEO_ID>` | Upload clips standalone |

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
- **Table `videos`:** id, url, judul_video, channel_video, tanggal_analisis, status_analisis, status_download, status_potong, status_upload, error_message
- **Table `moments`:** id, video_id (FK), waktu_start, waktu_selesai, judul_menarik, hashtag_terbaik, deskripsi_pendek, is_uploaded, is_selected
- **Table `schedules`:** id, video_id (FK), stage, scheduled_at, repeat (once/daily/weekly), status, last_run, created_at
- Status values: `pending`, `processing`, `success`, `failed`

### Environment & Config
- API key in `environment.txt`: `GEMINI_API_KEY=...`
- YouTube OAuth: `client_secrets.json` + `token.pickle` (auto-refresh)
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
|---|---|
| `web_server.py` | Main entry point (822 lines) |
| `analisa_youtube.py` | AI analysis with Gemini |
| `download_youtube.py` | yt-dlp downloader |
| `potong_video.py` | FFmpeg cutting + captioning |
| `upload_youtube.py` | YouTube Data API uploader |
| `autocaption.py` | Whisper subtitle pipeline |
| `web_static/app.js` | Frontend SPA logic |
| `web_static/style.css` | Design system (1600 lines) |
| `web_static/index.html` | Main HTML page |
| `NurClipper.py` | Legacy Tkinter GUI (v1) |
