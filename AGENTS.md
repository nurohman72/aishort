# AGENTS.md — NurClipper (AI YouTube Shorts Automation)

## Project Overview

NurClipper is a web-based automation platform that transforms long YouTube videos/podcasts into YouTube Shorts (9:16 vertical, max 59s). Pipeline: **Input URL → Analisa AI (Gemini) → Download (yt-dlp) → Potong (FFmpeg) → Upload (YouTube API)**.

## Tech Stack

- **Backend:** Python 3.14, FastAPI, Uvicorn, SQLite, Pydantic, SSE-Starlette
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
| `build_exe.bat` | Build all executables with PyInstaller |

## Build (PyInstaller Executable)

### Prerequisites
- `pip install pyinstaller`
- FFmpeg (`ffmpeg.exe`) di PATH atau di folder output
- `client_secrets.json` (YouTube OAuth)
- `environment.txt` berisi `GEMINI_API_KEY=...`

### Build Script
`build_exe.bat` meng-compile 5 script jadi executable:

| Stage | Mode | Output |
|---|---|---|
| `web_server.py` | `--onedir` | `NurClipper.exe` + `_internal/` |
| `analisa_youtube.py` | `--onefile` | `analisa_youtube.exe` |
| `download_youtube.py` | `--onefile` | `download_youtube.exe` |
| `potong_video.py` | `--onefile` | `potong_video.exe` |
| `upload_youtube.py` | `--onefile` | `upload_youtube.exe` |

Hasil build: `dist/NurClipper/`

### Output Structure
```
dist/NurClipper/
├── NurClipper.exe          (main server, ~11 MB)
├── _internal/              (DLLs, Python runtime, modules)
│   ├── web_static/         (frontend HTML/CSS/JS)
│   └── ...
├── analisa_youtube.exe     (~36 MB)
├── download_youtube.exe    (~27 MB)
├── potong_video.exe        (~213 MB, includes PyTorch + Whisper CPU)
├── upload_youtube.exe      (~35 MB)
└── environment.txt         (template, isi GEMINI_API_KEY=...)
```

### Known Issues & Fixes

| Issue | Fix |
|---|---|
| `clips_output` dir not found | Auto-create sebelum mount static files di `web_server.py` |
| `on_event` deprecation warning | Migrasi ke lifespan context manager (`@asynccontextmanager`) |
| `Could not import module "web_server"` | Frozen mode: `uvicorn.run(app, ...)` langsung, bukan string |
| `web_static` tidak ditemukan | Fallback ke `get_app_dir()/_internal/web_static` di frozen/onedir mode |
| `StaticFiles html=True` 404 | Sekarang root `/` serve index.html dengan benar |
| cp1252 encoding crash subprocess | `sys.stdout.reconfigure(encoding='utf-8')` di setiap script |
| Subprocess decode error | `errors='replace'` di `subprocess.Popen`/`subprocess.run` |
| Gemini 503 not error | `sys.exit(1)` di `analisa_youtube.py` after except |
| Pipeline gagal di tengah | Reset stage lain dari "processing" ke "pending" |
| Upload gagal exit code 0 | `sys.exit(1)` di `upload_youtube.py` saat `counter_upload == 0` |
| ResumableUploadError empty message | Log `e.resp.status` + `e.content`; deteksi quota via status 403 |
| Locked `dist/NurClipper` | Hapus manual dengan `rmdir /s /q` atau gunakan folder baru |

## PyInstaller Path Helpers

Setiap script punya `get_base_dir()` / `get_app_dir()` yang mendeteksi frozen mode via `getattr(sys, 'frozen', False)`:

```python
def get_app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))
```

Semua path absolut (DB, config, output dirs, static files) menggunakan helper ini agar konsisten antara dev dan bundled mode.

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

| File | Lines | Purpose |
|---|---|---|
| `web_server.py` | ~900 | Main entry point + API + PyInstaller helpers |
| `analisa_youtube.py` | ~350 | AI analysis with Gemini |
| `download_youtube.py` | ~150 | yt-dlp downloader |
| `potong_video.py` | ~350 | FFmpeg cutting + captioning |
| `upload_youtube.py` | ~280 | YouTube Data API uploader |
| `autocaption.py` | ~110 | Whisper subtitle pipeline |
| `web_static/app.js` | ~1000 | Frontend SPA logic |
| `web_static/style.css` | ~1600 | Design system |
| `web_static/index.html` | ~700 | Main HTML page |
| `build_exe.bat` | ~150 | PyInstaller build script |
| `NurClipper.py` | legacy | Legacy Tkinter GUI (v1) |
