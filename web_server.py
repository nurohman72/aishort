import os
import sys
import json
import queue
import sqlite3
import threading
import subprocess
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import requests
import schedule
import time

app = FastAPI(title="Nurohman Clipper Web API", version="1.0.0")

# Aktifkan CORS agar frontend dapat berkomunikasi dengan lancar jika dikembangkan terpisah
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_FILE = "database_konten.db"

# ----------------- DATABASE MANAGEMENT & MIGRATION -----------------
def migrate_db():
    print("[DB] Menjalankan inisialisasi dan migrasi database...")
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    cursor = conn.cursor()
    
    # Buat tabel utama jika belum ada
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            url TEXT UNIQUE, 
            tanggal_analisis TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS moments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            video_id INTEGER, 
            waktu_start TEXT, 
            judul_menarik TEXT, 
            hashtag_terbaik TEXT, 
            deskripsi_pendek TEXT, 
            is_uploaded INTEGER DEFAULT 0, 
            FOREIGN KEY (video_id) REFERENCES videos (id) ON DELETE CASCADE
        )
    ''')
    
    # Ambil kolom yang sudah ada di tabel videos
    cursor.execute("PRAGMA table_info(videos)")
    cols = [col[1] for col in cursor.fetchall()]
    
    # Tambahkan kolom baru untuk status pelacakan jika belum ada
    new_cols_videos = {
        "judul_video": "TEXT",
        "channel_video": "TEXT",
        "status_analisis": "TEXT DEFAULT 'pending'",
        "status_download": "TEXT DEFAULT 'pending'",
        "status_potong": "TEXT DEFAULT 'pending'",
        "status_upload": "TEXT DEFAULT 'pending'",
        "status_facebook": "TEXT DEFAULT 'pending'",
        "status_telegram": "TEXT DEFAULT 'pending'",
        "error_message": "TEXT"
    }
    
    new_cols_videos["upload_tanggal"] = "TEXT"
    new_cols_videos["upload_tanggal_fb"] = "TEXT"

    for col_name, col_type in new_cols_videos.items():
        if col_name not in cols:
            print(f"[DB] Menambahkan kolom '{col_name}' ke tabel videos...")
            cursor.execute(f"ALTER TABLE videos ADD COLUMN {col_name} {col_type}")
            
    # Ambil kolom yang sudah ada di tabel moments
    cursor.execute("PRAGMA table_info(moments)")
    cols_moments = [col[1] for col in cursor.fetchall()]
    
    # Tambahkan kolom is_selected untuk custom seleksi
    if "is_selected" not in cols_moments:
        print("[DB] Menambahkan kolom 'is_selected' ke tabel moments...")
        cursor.execute("ALTER TABLE moments ADD COLUMN is_selected INTEGER DEFAULT 1")
    
    # Tambahkan kolom waktu_selesai untuk end time momen
    if "waktu_selesai" not in cols_moments:
        print("[DB] Menambahkan kolom 'waktu_selesai' ke tabel moments...")
        cursor.execute("ALTER TABLE moments ADD COLUMN waktu_selesai TEXT")

    if "is_uploaded_fb" not in cols_moments:
        print("[DB] Menambahkan kolom 'is_uploaded_fb' ke tabel moments...")
        cursor.execute("ALTER TABLE moments ADD COLUMN is_uploaded_fb INTEGER DEFAULT 0")

    if "is_uploaded_tg" not in cols_moments:
        print("[DB] Menambahkan kolom 'is_uploaded_tg' ke tabel moments...")
        cursor.execute("ALTER TABLE moments ADD COLUMN is_uploaded_tg INTEGER DEFAULT 0")

    if "upload_tanggal" not in cols_moments:
        print("[DB] Menambahkan kolom 'upload_tanggal' ke tabel moments...")
        cursor.execute("ALTER TABLE moments ADD COLUMN upload_tanggal TEXT")

    if "upload_tanggal_fb" not in cols_moments:
        print("[DB] Menambahkan kolom 'upload_tanggal_fb' ke tabel moments...")
        cursor.execute("ALTER TABLE moments ADD COLUMN upload_tanggal_fb TEXT")

    # Fix NULL values di kolom is_uploaded (bug lama: kolom bisa NULL padahal seharusnya 0)
    cursor.execute("UPDATE moments SET is_uploaded = 0 WHERE is_uploaded IS NULL")
    cursor.execute("UPDATE moments SET is_uploaded_fb = 0 WHERE is_uploaded_fb IS NULL")
    cursor.execute("UPDATE moments SET is_uploaded_tg = 0 WHERE is_uploaded_tg IS NULL")

    # Buat tabel schedules jika belum ada
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER,
            stage TEXT DEFAULT 'all',
            scheduled_at TEXT,
            repeat TEXT DEFAULT 'once',
            status TEXT DEFAULT 'pending',
            last_run TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (video_id) REFERENCES videos (id) ON DELETE CASCADE
        )
    ''')
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_moments_video_id ON moments(video_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_moments_selected ON moments(video_id, is_selected)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_schedules_pending ON schedules(status, scheduled_at)")
        
    conn.commit()
    conn.close()
    print("[DB] Migrasi database selesai dengan sukses.")

# ----------------- UTILS & METADATA FETCH -----------------
def fetch_youtube_metadata(url):
    """Mengambil judul dan channel video secara instan via YouTube oEmbed API"""
    try:
        oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
        res = requests.get(oembed_url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            return data.get("title", "YouTube Video"), data.get("author_name", "Unknown Channel")
    except Exception as e:
        print(f"[Warning] Gagal mengambil oembed metadata: {e}")
    return "YouTube Video", "Unknown Channel"

# ----------------- REAL-TIME LOG MANAGER -----------------
log_listeners = set()
log_history = []
log_lock = threading.Lock()
main_event_loop = None

def log_message(video_id: Optional[int], text: str):
    """Menambahkan pesan log ke memori dan membroadcast ke semua klien web aktif"""
    msg = {
        "video_id": video_id,
        "text": text,
        "timestamp": datetime.now().strftime("%H:%M:%S")
    }
    with log_lock:
        log_history.append(msg)
        if len(log_history) > 1000:
            log_history.pop(0)
        listeners = list(log_listeners)

    if main_event_loop and main_event_loop.is_running():
        for q in listeners:
            try:
                main_event_loop.call_soon_threadsafe(q.put_nowait, msg)
            except Exception:
                pass
    else:
        for q in listeners:
            try:
                q.put_nowait(msg)
            except Exception:
                pass

# ----------------- BACKGROUND MULTI-THREAD WORKER POOL -----------------
task_queue = queue.Queue()
active_processes = set()
active_processes_lock = threading.Lock()
queued_videos = set()
queued_videos_lock = threading.Lock()
MAX_WORKERS = 2  # default, bisa diubah via config
worker_threads = []
worker_running = threading.Event()
worker_running.set()  # aktif sejak awal

from contextlib import contextmanager

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def db_cursor():
    conn = get_db_connection()
    try:
        yield conn.cursor()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

VALID_COLUMNS = {"status_analisis", "status_download", "status_potong", "status_upload", "status_facebook", "status_telegram", "error_message", "judul_video", "channel_video"}

def update_video_status(video_id: int, **kwargs):
    """Mengupdate status kolom video di database secara cepat"""
    # Validasi column name untuk cegah SQL injection
    for col in kwargs.keys():
        if col not in VALID_COLUMNS:
            raise ValueError(f"Column '{col}' tidak diizinkan untuk update")
    
    with db_cursor() as cursor:
        set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values())
        values.append(video_id)
        cursor.execute(f"UPDATE videos SET {set_clause} WHERE id = ?", values)

TIMEOUT_PER_PROCESS = 1800  # 30 menit maks per subprocess (Whisper large bisa lama)

def execute_subprocess_live(video_id: int, stage: str, cmd: List[str]) -> bool:
    """Mengeksekusi perintah subprocess Python dan menangkap output log per baris secara real-time"""
    log_message(video_id, f"⚡ MEMULAI TAHAP: {stage.upper()}")
    log_message(video_id, f"Eksekusi perintah: {' '.join(cmd)}")
    
    process = None
    try:
        env_custom = os.environ.copy()
        env_custom["PYTHONUNBUFFERED"] = "1"
        env_custom["FONTCONFIG_FILE"] = "<nul>"
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            shell=False,
            bufsize=1,
            env=env_custom
        )
        
        # Baca output stdout live baris demi baris
        for line in process.stdout:
            clean_line = line.strip()
            if clean_line:
                log_message(video_id, clean_line)
        
        # Tunggu dengan timeout — jika hang, process akan di-kill
        try:
            process.wait(timeout=TIMEOUT_PER_PROCESS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            log_message(video_id, f"❌ [TIMEOUT] Tahap {stage.upper()} melebihi batas {TIMEOUT_PER_PROCESS//60} menit, terpaksa dihentikan.")
            return False
        
        success = (process.returncode == 0)
        log_message(video_id, f"🏁 TAHAP {stage.upper()} selesai dengan exit code: {process.returncode}")
        # Tutup pipe stdout setelah process selesai
        try:
            process.stdout.close()
        except Exception:
            pass
        return success
    except Exception as e:
        log_message(video_id, f"❌ [ERROR KRITIS] Gagal menjalankan tahap {stage}: {str(e)}")
        if process:
            try:
                process.kill()
            except Exception:
                pass
        return False

def worker_loop():
    """Loop setiap worker thread — mengambil task dari queue dan memproses secara parallel"""
    print(f"[Worker] Thread worker {threading.current_thread().name} siap.")
    while worker_running.is_set():
        try:
            task = task_queue.get()
            if task is None:
                task_queue.task_done()
                break
                
            video_id = task["video_id"]
            stage = task["stage"]
            
            # Hapus dari antrian karena sudah mulai diproses
            with queued_videos_lock:
                queued_videos.discard(video_id)
            
            try:
                # Hubungkan ke DB untuk membaca URL video
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT url, judul_video FROM videos WHERE id = ?", (video_id,))
                row = cursor.fetchone()
                conn.close()
                
                if not row:
                    log_message(video_id, f"❌ [Gagal] Video ID {video_id} tidak ditemukan di database.")
                    task_queue.task_done()
                    continue
                    
                video_url = row["url"]
                video_title = row["judul_video"]
                
                log_message(video_id, f"\n🚀 [Queue] Memproses Video: '{video_title}' (ID: {video_id}) — Worker: {threading.current_thread().name}")
                
                # --- JALANKAN PIPELINE TAHAP DEMI TAHAP ---
                stages_to_run = []
                if stage == "all":
                    stages_to_run = ["analisa", "download", "potong"]
                else:
                    stages_to_run = [stage]
                    
                # Mapping nama stage ke nama kolom DB yang benar
                STAGE_COL = {
                    "analisa":  "status_analisis",
                    "download": "status_download",
                    "potong":   "status_potong",
                    "upload":   "status_upload",
                    "facebook": "status_facebook",
                    "telegram": "status_telegram",
                }

                success = True
                for current_stage in stages_to_run:
                    # Update status menjadi 'processing'
                    status_key = STAGE_COL[current_stage]
                    update_video_status(video_id, **{status_key: "processing", "error_message": None})
                    
                    # Menentukan perintah command line
                    cmd = []
                    if current_stage == "analisa":
                        cmd = [sys.executable, "analisa_youtube.py", video_url]
                    elif current_stage == "download":
                        cmd = [sys.executable, "download_youtube.py", video_url]
                    elif current_stage == "potong":
                        cmd = [sys.executable, "potong_video.py", str(video_id)]
                    elif current_stage == "upload":
                        cmd = [sys.executable, "upload_youtube.py", str(video_id)]
                    elif current_stage == "facebook":
                        cmd = [sys.executable, "upload_facebook.py", str(video_id)]
                    elif current_stage == "telegram":
                        cmd = [sys.executable, "upload_telegram.py", str(video_id)]
                        
                    # Eksekusi — tandai video sebagai active agar cleanup thread tidak mereset statusnya
                    with active_processes_lock:
                        active_processes.add(video_id)
                    try:
                        stage_success = execute_subprocess_live(video_id, current_stage, cmd)
                    finally:
                        with active_processes_lock:
                            active_processes.discard(video_id)
                    
                    if stage_success:
                        update_video_status(video_id, **{status_key: "success"})
                    else:
                        update_video_status(video_id, **{status_key: "failed", "error_message": f"Gagal pada tahap {current_stage}"})
                        success = False
                        log_message(video_id, f"❌ Pipeline dihentikan karena kegagalan pada tahap: {current_stage}")
                        # Reset tahap lain yang masih 'processing' kembali ke 'pending'
                        remaining_stages = stages_to_run[stages_to_run.index(current_stage) + 1:]
                        if remaining_stages:
                            reset_kwargs = {}
                            for s in remaining_stages:
                                reset_kwargs[STAGE_COL[s]] = "pending"
                            update_video_status(video_id, **reset_kwargs)
                            log_message(video_id, f"🔄 Tahap {', '.join(remaining_stages)} dikembalikan ke status 'pending'")
                        break  # Stop pipeline jika ada yang gagal di tengah jalan
                        
                if success and stage == "all":
                    log_message(video_id, "🎉 [SUKSES] Pipeline prep selesai! Video siap diupload.")
                    
            except Exception as ex:
                error_msg = f"Terjadi kesalahan fatal: {str(ex)}"
                print(f"[Worker Error] Video ID {video_id}: {error_msg}")
                log_message(video_id, f"❌ [ERROR FATAL] {error_msg}")
                # Jika ada error crash, reset semua status 'processing' kembali ke 'failed'
                STAGE_COL = {"analisa": "status_analisis", "download": "status_download", "potong": "status_potong", "upload": "status_upload", "facebook": "status_facebook", "telegram": "status_telegram"}
                for s in ["analisa", "download", "potong", "upload", "facebook", "telegram"]:
                    try:
                        update_video_status(video_id, **{STAGE_COL[s]: "failed", "error_message": error_msg})
                    except Exception:
                        pass
            finally:
                task_queue.task_done()
        except Exception as ex:
            print(f"[Worker Error] Terjadi kendala: {ex}")
            log_message(None, f"[Worker Error] Kendala fatal: {ex}")

    print(f"[Worker] Thread {threading.current_thread().name} berhenti.")


def start_worker_pool(count=MAX_WORKERS):
    """Memulai N worker thread untuk parallel processing"""
    global worker_threads
    # Hentikan worker lama jika ada
    stop_worker_pool()
    worker_running.set()
    worker_threads = []
    for i in range(count):
        t = threading.Thread(target=worker_loop, daemon=True, name=f"Worker-{i+1}")
        t.start()
        worker_threads.append(t)
    print(f"[Worker] {count} worker thread dimulai. Siap memproses {count} video secara parallel.")


def stop_worker_pool():
    """Menghentikan semua worker thread"""
    worker_running.clear()
    # Kirim sentinel untuk membangunkan worker yang sedang blocking di queue.get()
    for _ in worker_threads:
        task_queue.put(None)
    for t in worker_threads:
        if t.is_alive():
            t.join(timeout=2)
    worker_threads.clear()

# Jalankan worker pool saat startup (mengambil max_workers dari config jika ada)
def init_worker_pool():
    try:
        cfg = load_app_config()
        w = cfg.get("auto_upload", {}).get("max_workers", MAX_WORKERS)
        start_worker_pool(max(1, min(5, w)))
    except Exception:
        start_worker_pool(MAX_WORKERS)

# Worker pool dimulai di startup_event (hindari duplikat saat reload=True)

# ----------------- PYDANTIC SCHEMAS -----------------
class VideoInput(BaseModel):
    url: str

class MomentUpdate(BaseModel):
    waktu_start: str
    judul_menarik: str
    hashtag_terbaik: str
    deskripsi_pendek: str
    is_selected: int

class ConfigUpdate(BaseModel):
    gemini_key: str
    enable_caption: bool
    font_name: str
    font_size: str
    whisper_model: str
    enable_facebook: bool = False
    fb_page_id: str = ""
    fb_page_token: str = ""
    fb_privacy: str = "PUBLIC"
    enable_telegram: bool = False
    tg_api_id: str = ""
    tg_api_hash: str = ""
    tg_phone: str = ""
    tg_session_name: str = "nurclipper_tg"
    auto_upload_enabled: bool = True
    upload_limit_per_day: int = 30
    max_workers: int = 2

class ScheduleInput(BaseModel):
    video_id: int
    stage: str
    scheduled_at: str  # Format: "YYYY-MM-DD HH:MM"
    repeat: str = "once"  # once | daily | weekly

# ----------------- API ENDPOINTS -----------------

@app.on_event("startup")
def startup_event():
    global main_event_loop
    try:
        main_event_loop = asyncio.get_running_loop()
    except RuntimeError:
        main_event_loop = None
    migrate_db()
    for folder in ["videos_podcast", "clips_output"]:
        if not os.path.exists(folder):
            os.makedirs(folder)
    init_worker_pool()

    # Reset status 'processing' yang tertinggal akibat crash/restart server
    # Ubah ke 'failed' agar user bisa trigger ulang tanpa tombol ter-disable
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE videos
            SET status_analisis = CASE WHEN status_analisis = 'processing' THEN 'failed' ELSE status_analisis END,
                status_download  = CASE WHEN status_download  = 'processing' THEN 'failed' ELSE status_download  END,
                status_potong    = CASE WHEN status_potong    = 'processing' THEN 'failed' ELSE status_potong    END,
                status_upload    = CASE WHEN status_upload    = 'processing' THEN 'failed' ELSE status_upload    END,
                status_facebook  = CASE WHEN status_facebook  = 'processing' THEN 'failed' ELSE status_facebook  END,
                status_telegram  = CASE WHEN status_telegram  = 'processing' THEN 'failed' ELSE status_telegram  END
            WHERE status_analisis = 'processing'
               OR status_download  = 'processing'
               OR status_potong    = 'processing'
               OR status_upload    = 'processing'
               OR status_facebook  = 'processing'
               OR status_telegram  = 'processing'
        """)
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        if affected > 0:
            print(f"[Startup] Reset {affected} video dari status 'processing' → 'failed' akibat restart.")
    except Exception as e:
        print(f"[Startup] Gagal reset status processing: {e}")

    # Jalankan scheduler thread
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    # Jalankan auto-upload scheduler
    auto_scheduler_thread = threading.Thread(target=auto_upload_scheduler, daemon=True)
    auto_scheduler_thread.start()
    # Trigger check pertama kali saat startup
    threading.Thread(target=auto_upload_check_once, daemon=True).start()

    # Cek versi yt-dlp terbaru saat aplikasi pertama kali berjalan
    threading.Thread(target=cek_update_ytdlp, daemon=True).start()

    # Periodic stale-status cleanup (setiap 5 menit) untuk jaga-jaga jika ada status 'processing' yang macet
    def stale_status_cleanup():
        while True:
            try:
                with active_processes_lock:
                    active_vids = list(active_processes)
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                # Reset processing → failed HANYA untuk video yang TIDAK sedang diproses
                for vid_col in ["status_analisis", "status_download", "status_potong", "status_upload", "status_facebook", "status_telegram"]:
                    if active_vids:
                        placeholders = ",".join("?" * len(active_vids))
                        cursor.execute(f"""
                            UPDATE videos
                            SET {vid_col} = 'failed'
                            WHERE {vid_col} = 'processing'
                              AND id NOT IN ({placeholders})
                        """, active_vids)
                    else:
                        cursor.execute(f"""
                            UPDATE videos
                            SET {vid_col} = 'failed'
                            WHERE {vid_col} = 'processing'
                        """)
                affected = cursor.rowcount
                conn.commit()
                conn.close()
                if affected > 0:
                    print(f"[Cleanup] Reset {affected} video dari status 'processing' → 'failed' (stale cleanup).")
            except Exception as e:
                print(f"[Cleanup] Error: {e}")
            time.sleep(300)  # 5 menit

    stale_thread = threading.Thread(target=stale_status_cleanup, daemon=True)
    stale_thread.start()

@app.get("/api/videos")
def get_videos():
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT v.*, 
                   COUNT(m.id) as total_moments, 
                   SUM(CASE WHEN m.is_uploaded = 1 THEN 1 ELSE 0 END) as uploaded_moments
            FROM videos v
            LEFT JOIN moments m ON m.video_id = v.id
            GROUP BY v.id
            ORDER BY v.id DESC
        """)
        rows = cursor.fetchall()
    
    videos = []
    for r in rows:
        v = dict(r)
        v["total_moments"] = v["total_moments"] if v["total_moments"] else 0
        v["uploaded_moments"] = v["uploaded_moments"] if v["uploaded_moments"] else 0
        videos.append(v)
        
    return videos

@app.post("/api/videos")
def add_video(payload: VideoInput):
    """Menambahkan link YouTube baru ke antrean database"""
    url = payload.url.strip()
    if not url or ("youtube.com" not in url and "youtu.be" not in url):
        raise HTTPException(status_code=400, detail="Link YouTube tidak valid.")
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Ambil info metadata secara instan
        title, channel = fetch_youtube_metadata(url)
        
        cursor.execute(
            "INSERT INTO videos (url, judul_video, channel_video, status_analisis, status_download, status_potong, status_upload) VALUES (?, ?, ?, 'pending', 'pending', 'pending', 'pending')",
            (url, title, channel)
        )
        video_id = cursor.lastrowid
        conn.commit()
        log_message(video_id, f"📝 Ditambahkan ke database: '{title}' ({url})")

        # Auto-trigger pipeline prep (analisa → download → potong)
        with queued_videos_lock:
            queued_videos.add(video_id)
        task_queue.put({"video_id": video_id, "stage": "all"})
        log_message(video_id, "📥 [Antrian] Pipeline prep (Analisa → Download → Potong) masuk antrian. Menunggu giliran...")

        return {"success": True, "video_id": video_id, "judul_video": title, "channel_video": channel}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Link URL YouTube ini sudah ada di antrean database!")
    finally:
        conn.close()

@app.delete("/api/videos/{video_id}")
def delete_video(video_id: int):
    """Menghapus video dan semua data momen terkait serta membersihkan file video fisik jika ada"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Dapatkan URL dan data momen untuk pembersihan file
    cursor.execute("SELECT url, judul_video FROM videos WHERE id = ?", (video_id,))
    video_row = cursor.fetchone()
    
    if not video_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Video tidak ditemukan.")
        
    # Hapus dari database (CASCADE akan otomatis menghapus moments yang ber-foreign key ke video ini)
    cursor.execute("DELETE FROM videos WHERE id = ?", (video_id,))
    conn.commit()
    conn.close()
    
    log_message(video_id, f"🗑️ Menghapus video dari database: '{video_row['judul_video']}'")
    
    # Hapus file hasil potongan di clips_output (misal: "videoID_momentID.mp4")
    clips_folder = "clips_output"
    if os.path.exists(clips_folder):
        deleted_files = 0
        for f in os.listdir(clips_folder):
            if f.startswith(f"{video_id}_"):
                try:
                    os.remove(os.path.join(clips_folder, f))
                    deleted_files += 1
                except Exception as ex:
                    print(f"Error menghapus {f}: {ex}")
        if deleted_files > 0:
            log_message(video_id, f"🧹 Berhasil membersihkan {deleted_files} file hasil potongan terkait di clips_output.")
            
    return {"success": True, "message": "Video dan klip terkait berhasil dihapus total."}

@app.get("/api/moments/{video_id}")
def get_moments(video_id: int):
    with db_cursor() as cursor:
        cursor.execute("SELECT * FROM moments WHERE video_id = ? ORDER BY id ASC", (video_id,))
        rows = cursor.fetchall()
    
    moments = []
    for r in rows:
        m = dict(r)
        file_clip_name = f"{video_id}_{m['id']}.mp4"
        path_clip = os.path.join("clips_output", file_clip_name)
        m["has_clip"] = os.path.exists(path_clip)
        m["clip_url"] = f"/clips/{file_clip_name}" if m["has_clip"] else None
        m["is_uploaded_fb"] = m.get("is_uploaded_fb", 0)
        m["is_uploaded_tg"] = m.get("is_uploaded_tg", 0)
        moments.append(m)
        
    return moments

@app.put("/api/moments/{moment_id}")
def update_moment(moment_id: int, payload: MomentUpdate):
    """Memperbarui informasi momen kustom (judul, hashtag, durasi, seleksi)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE moments 
        SET waktu_start = ?, judul_menarik = ?, hashtag_terbaik = ?, deskripsi_pendek = ?, is_selected = ?
        WHERE id = ?
    """, (payload.waktu_start, payload.judul_menarik, payload.hashtag_terbaik, payload.deskripsi_pendek, payload.is_selected, moment_id))
    
    conn.commit()
    conn.close()
    return {"success": True, "message": "Metadata momen berhasil disimpan."}

@app.post("/api/process/{video_id}/{stage}")
def trigger_stage(video_id: int, stage: str):
    """Memicu proses manual per tahap (analisa, download, potong, upload)"""
    if stage not in ["analisa", "download", "potong", "upload", "facebook", "telegram", "all"]:
        raise HTTPException(status_code=400, detail="Tahapan proses tidak dikenal.")
        
    # Tambahkan tugas ke antrean latar belakang
    with queued_videos_lock:
        queued_videos.add(video_id)
    task_queue.put({"video_id": video_id, "stage": stage})
    log_message(video_id, f"📥 Masuk Antrean Latar Belakang: Tahap '{stage.upper()}'")
        
    return {"success": True, "message": f"Tugas {stage} berhasil didaftarkan ke antrean."}

# ----------------- CONFIGURATION MANAGEMENT -----------------
ENV_FILE = "environment.txt"
CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "auto_upload": {
        "enabled": True,
        "limit_per_day": 30,
        "max_workers": 2
    },
    "caption": {
        "enabled": True,
        "model": "small",
        "font_name": "Cooper Black",
        "font_size": "6",
        "align": "2",
        "margin_v": "100",
        "margin_h": "0"
    },
    "facebook": {
        "enabled": False,
        "page_id": "",
        "page_access_token": "",
        "privacy": "PUBLIC"
    },
    "telegram": {
        "enabled": False,
        "api_id": "",
        "api_hash": "",
        "phone": "",
        "session_name": "nurclipper_tg"
    }
}

def _deep_merge_dict(base: dict, override: dict) -> dict:
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge_dict(base[k], v)
        else:
            base[k] = v
    return base

def load_app_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                _deep_merge_dict(cfg, loaded)
                return cfg
        except Exception as e:
            print(f"[Config] Gagal baca config.json: {e}")
    return cfg

@app.get("/api/config")
def get_config():
    gemini_key = ""
    if os.path.exists(ENV_FILE):
        try:
            with open(ENV_FILE, "r") as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY="):
                        gemini_key = line.replace("GEMINI_API_KEY=", "").strip()
        except Exception as e:
            print(f"Gagal baca config: {e}")

    app_cfg = load_app_config()
    caption = app_cfg.get("caption", DEFAULT_CONFIG["caption"])
    facebook = app_cfg.get("facebook", DEFAULT_CONFIG["facebook"])
    telegram = app_cfg.get("telegram", DEFAULT_CONFIG["telegram"])
    has_youtube_auth = os.path.exists("token.pickle")

    masked_key = ""
    if len(gemini_key) > 10:
        masked_key = gemini_key[:6] + "****" + gemini_key[-4:]

    fb_token = facebook.get("page_access_token", "")
    masked_fb_token = ""
    if len(fb_token) > 10:
        masked_fb_token = fb_token[:6] + "****" + fb_token[-4:]

    tg_api_hash = telegram.get("api_hash", "")
    masked_tg_hash = ""
    if len(tg_api_hash) > 10:
        masked_tg_hash = tg_api_hash[:6] + "****" + tg_api_hash[-4:]

    return {
        "gemini_key": masked_key,
        "enable_caption": caption.get("enabled", True),
        "font_name": caption.get("font_name", "Cooper Black"),
        "font_size": caption.get("font_size", "6"),
        "whisper_model": caption.get("model", "small"),
        "has_youtube_auth": has_youtube_auth,
        "enable_facebook": facebook.get("enabled", False),
        "fb_page_id": facebook.get("page_id", ""),
        "fb_page_token": masked_fb_token,
        "fb_privacy": facebook.get("privacy", "PUBLIC"),
        "enable_telegram": telegram.get("enabled", False),
        "tg_api_id": telegram.get("api_id", ""),
        "tg_api_hash": masked_tg_hash,
        "tg_phone": telegram.get("phone", ""),
        "tg_session_name": telegram.get("session_name", "nurclipper_tg"),
        "auto_upload_enabled": app_cfg.get("auto_upload", DEFAULT_CONFIG["auto_upload"]).get("enabled", True),
        "upload_limit_per_day": app_cfg.get("auto_upload", DEFAULT_CONFIG["auto_upload"]).get("limit_per_day", 30),
        "max_workers": app_cfg.get("auto_upload", DEFAULT_CONFIG["auto_upload"]).get("max_workers", 2)
    }

@app.post("/api/config")
def update_config(payload: ConfigUpdate):
    try:
        old_gemini_key = ""
        if os.path.exists(ENV_FILE):
            with open(ENV_FILE, "r") as ef:
                for line in ef:
                    if line.startswith("GEMINI_API_KEY="):
                        old_gemini_key = line.replace("GEMINI_API_KEY=", "").strip()
        new_gemini_key = payload.gemini_key.strip()
        if "****" in new_gemini_key or not new_gemini_key:
            new_gemini_key = old_gemini_key
        with open(ENV_FILE, "w") as f:
            f.write(f"GEMINI_API_KEY={new_gemini_key}\n")
        log_message(None, "Gemini API Key berhasil diperbarui di environment.txt.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal menulis environment.txt: {e}")

    try:
        app_cfg = load_app_config()
        app_cfg["caption"] = {
            "enabled": payload.enable_caption,
            "model": payload.whisper_model,
            "font_name": payload.font_name,
            "font_size": payload.font_size,
            "align": app_cfg.get("caption", {}).get("align", "2"),
            "margin_v": app_cfg.get("caption", {}).get("margin_v", "100"),
            "margin_h": app_cfg.get("caption", {}).get("margin_h", "0")
        }
        old_fb = app_cfg.get("facebook", {})
        new_token = payload.fb_page_token.strip()
        if "****" in new_token or not new_token:
            new_token = old_fb.get("page_access_token", "")
        app_cfg["facebook"] = {
            "enabled": payload.enable_facebook,
            "page_id": payload.fb_page_id.strip(),
            "page_access_token": new_token,
            "privacy": payload.fb_privacy
        }
        old_tg = app_cfg.get("telegram", {})
        new_tg_hash = payload.tg_api_hash.strip()
        if "****" in new_tg_hash or not new_tg_hash:
            new_tg_hash = old_tg.get("api_hash", "")
        app_cfg["telegram"] = {
            "enabled": payload.enable_telegram,
            "api_id": payload.tg_api_id.strip(),
            "api_hash": new_tg_hash,
            "phone": payload.tg_phone.strip(),
            "session_name": payload.tg_session_name.strip() or "nurclipper_tg"
        }
        new_max_workers = max(1, min(5, payload.max_workers))
        app_cfg["auto_upload"] = {
            "enabled": payload.auto_upload_enabled,
            "limit_per_day": payload.upload_limit_per_day,
            "max_workers": new_max_workers
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(app_cfg, f, indent=2)

        # Jika jumlah worker berubah, restart pool dengan jumlah baru
        if new_max_workers != len(worker_threads):
            log_message(None, f"⚙️ Jumlah worker diubah: {len(worker_threads)} → {new_max_workers}. Merestart pool...")
            start_worker_pool(new_max_workers)
        log_message(None, "Pengaturan diperbarui di config.json.")
    except Exception as e:
        log_message(None, f"[Warning] Gagal mengupdate config.json: {e}")

    return {"success": True}

@app.post("/api/youtube-auth")
def trigger_youtube_auth():
    """Memicu inisialisasi login Google OAuth untuk YouTube"""
    log_message(None, "🔑 Memulai proses otentikasi YouTube API...")
    try:
        # Kita jalankan skrip upload secara parsial untuk memicu login browser jika pickle belum ada
        # Buat dummy/uji coba singkat dengan me-run import auth
        cmd = [sys.executable, "-c", "import upload_youtube; upload_youtube.dapatkan_layanan_youtube()"]
        
        # Jalankan secara terpisah tanpa block utama web agar user bisa login browser
        # Karena InstalledAppFlow.run_local_server membuka browser lokal, backend akan terblokir sampai login selesai
        def login_task():
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            if proc.returncode == 0:
                log_message(None, "✅ [Sukses] Kredensial YouTube berhasil disimpan (token.pickle)!")
            else:
                log_message(None, f"❌ [Gagal] Otentikasi dibatalkan atau client_secrets.json salah: {proc.stdout}")
                
        threading.Thread(target=login_task, daemon=False).start()
        return {"success": True, "message": "Proses login telah dipicu. Silakan periksa jendela browser baru di komputer server untuk masuk ke Akun Google Anda."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cleanup")
def cleanup_all():
    """Membersihkan database dan semua file video dari videos_podcast & clips_output"""
    log_message(None, "🧹 Memulai pembersihan total sesi lama...")
    
    try:
        # 1. Kosongkan Database
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM moments;")
        cursor.execute("DELETE FROM videos;")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='videos' OR name='moments';")
        conn.commit()
        conn.close()
        log_message(None, "🧹 [Database] Semua riwayat dan momen berhasil dikosongkan.")
        
        # 2. Bersihkan file podcast
        for folder in ["videos_podcast", "clips_output"]:
            deleted_count = 0
            if os.path.exists(folder):
                for f in os.listdir(folder):
                    file_path = os.path.join(folder, f)
                    if os.path.isfile(file_path):
                        try:
                            os.remove(file_path)
                            deleted_count += 1
                        except Exception as ex:
                            print(f"Error hapus {file_path}: {ex}")
            log_message(None, f"🧹 [File] Dihapus {deleted_count} file di dalam folder '{folder}'.")
            
        return {"success": True, "message": "Database dan seluruh file sesi berhasil dibersihkan total."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/reset/{video_id}")
def reset_video_status(video_id: int):
    """Mereset semua status tahap video yang 'stuck' kembali ke 'pending' agar tombol bisa digunakan lagi"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, judul_video FROM videos WHERE id = ?", (video_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Video tidak ditemukan.")
    try:
        update_video_status(video_id,
            status_analisis="pending",
            status_download="pending",
            status_potong="pending",
            status_upload="pending",
            status_facebook="pending",
            status_telegram="pending",
            error_message=None
        )
        log_message(video_id, f"🔄 Semua status tahap video di-reset ke 'pending'")
        return {"success": True, "message": f"Status video '{row['judul_video']}' berhasil di-reset."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ----------------- YT-DLP VERSION CHECKER -----------------
ytdlp_status = {
    "installed": None,
    "latest": None,
    "update_available": False,
    "checking": False,
    "updating": False,
    "last_check": None,
    "last_error": None
}
ytdlp_lock = threading.Lock()

def get_ytdlp_version_terpasang():
    try:
        from importlib.metadata import version as pkg_version
        return pkg_version("yt-dlp")
    except Exception:
        return None

def versi_lebih_baru(v_baru, v_lama):
    def parse(v):
        try:
            return tuple(int(p) for p in str(v).split("."))
        except Exception:
            return None
    a, b = parse(v_baru), parse(v_lama)
    if a and b:
        return a > b
    return str(v_baru) != str(v_lama)

def cek_update_ytdlp():
    """Cek versi yt-dlp terbaru dari PyPI dan bandingkan dengan versi terpasang"""
    with ytdlp_lock:
        if ytdlp_status["checking"] or ytdlp_status["updating"]:
            return dict(ytdlp_status)
        ytdlp_status["checking"] = True
    try:
        res = requests.get("https://pypi.org/pypi/yt-dlp/json", timeout=10)
        res.raise_for_status()
        latest = res.json()["info"]["version"]
        installed = get_ytdlp_version_terpasang()
        with ytdlp_lock:
            ytdlp_status["installed"] = installed
            ytdlp_status["latest"] = latest
            ytdlp_status["update_available"] = bool(installed and versi_lebih_baru(latest, installed))
            ytdlp_status["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ytdlp_status["last_error"] = None
            tersedia = ytdlp_status["update_available"]
        if tersedia:
            log_message(None, f"⬆️ [Update] yt-dlp versi baru tersedia: {installed} → {latest}")
    except Exception as e:
        with ytdlp_lock:
            ytdlp_status["last_error"] = str(e)
            ytdlp_status["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[YtDlpCheck] Gagal cek versi: {e}")
    finally:
        with ytdlp_lock:
            ytdlp_status["checking"] = False
    return dict(ytdlp_status)

def proses_update_ytdlp():
    """Jalankan pip install --upgrade yt-dlp dan laporkan hasilnya ke log sistem"""
    with ytdlp_lock:
        if ytdlp_status["updating"]:
            return
        ytdlp_status["updating"] = True
    versi_lama = ytdlp_status.get("installed") or get_ytdlp_version_terpasang()
    log_message(None, f"⬆️ [Update] Memperbarui yt-dlp via pip...")
    sukses = False
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300
        )
        versi_baru = get_ytdlp_version_terpasang()
        output_tail = "\n".join((proc.stdout or "").strip().splitlines()[-3:])
        if proc.returncode == 0 and versi_baru and versi_baru != versi_lama:
            log_message(None, f"✅ [Update] yt-dlp berhasil diperbarui: {versi_lama} → {versi_baru}")
            log_message(None, "[Info] Versi baru langsung dipakai pada proses download berikutnya tanpa restart server.")
            sukses = True
        elif proc.returncode == 0:
            log_message(None, f"[Info] yt-dlp sudah berada di versi terbaru ({versi_baru}).")
            sukses = True
        else:
            log_message(None, f"❌ [Update] Gagal memperbarui yt-dlp (exit code {proc.returncode}): {output_tail}")
    except Exception as e:
        log_message(None, f"❌ [Update] Error saat memperbarui yt-dlp: {e}")
    finally:
        with ytdlp_lock:
            ytdlp_status["updating"] = False
    if sukses:
        cek_update_ytdlp()

@app.get("/api/ytdlp/status")
def get_ytdlp_status(force: bool = False):
    """Ambil status versi yt-dlp terpasang vs terbaru di PyPI"""
    if force:
        return cek_update_ytdlp()
    if not ytdlp_status["last_check"] and not ytdlp_status["checking"]:
        threading.Thread(target=cek_update_ytdlp, daemon=True).start()
    with ytdlp_lock:
        return dict(ytdlp_status)

@app.post("/api/ytdlp/update")
def trigger_update_ytdlp():
    """Memicu update yt-dlp via pip di background thread"""
    with ytdlp_lock:
        if ytdlp_status["updating"]:
            raise HTTPException(status_code=409, detail="Proses update sedang berjalan.")
    threading.Thread(target=proses_update_ytdlp, daemon=True).start()
    log_message(None, "⬆️ [Update] Proses update yt-dlp dimulai di latar belakang.")
    return {"success": True, "message": "Update yt-dlp dimulai. Pantau progres di konsol log."}

# ----------------- SCHEDULED UPLOAD MANAGER -----------------

def run_scheduler():
    """Thread yang berjalan terus menerus untuk memeriksa jadwal yang sudah waktunya"""
    print("[Scheduler] Thread penjadwal aktif.")
    while True:
        try:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, video_id, stage, repeat FROM schedules
                WHERE status = 'pending' AND scheduled_at = ?
            """, (now_str,))
            due_tasks = cursor.fetchall()
            conn.close()

            for task in due_tasks:
                sched_id, video_id, stage, repeat = task["id"], task["video_id"], task["stage"], task["repeat"]
                log_message(video_id, f"⏰ [Scheduler] Jadwal ID {sched_id} terpicu! Memulai tahap '{stage}' untuk Video ID {video_id}...")
                task_queue.put({"video_id": video_id, "stage": stage})

                # Update status jadwal
                conn2 = get_db_connection()
                c2 = conn2.cursor()
                if repeat == "once":
                    c2.execute("UPDATE schedules SET status='done', last_run=? WHERE id=?", (now_str, sched_id))
                elif repeat == "daily":
                    next_run = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
                    c2.execute("UPDATE schedules SET scheduled_at=?, last_run=? WHERE id=?", (next_run, now_str, sched_id))
                elif repeat == "weekly":
                    next_run = (datetime.now() + timedelta(weeks=1)).strftime("%Y-%m-%d %H:%M")
                    c2.execute("UPDATE schedules SET scheduled_at=?, last_run=? WHERE id=?", (next_run, now_str, sched_id))
                conn2.commit()
                conn2.close()
        except Exception as ex:
            print(f"[Scheduler Error] {ex}")
        time.sleep(30)  # Cek setiap 30 detik


# ----------------- AUTO-UPLOAD SCHEDULER -----------------

def auto_upload_check_once():
    """Cek dan enqueue video untuk auto-upload (dipanggil sekali)"""
    try:
        app_cfg = load_app_config()
        auto_cfg = app_cfg.get("auto_upload", {"enabled": True, "limit_per_day": 30})
        if not auto_cfg.get("enabled", True):
            return

        limit = auto_cfg.get("limit_per_day", 30)
        today = datetime.now().strftime("%Y-%m-%d")

        conn = get_db_connection()
        cursor = conn.cursor()

        # Hitung jumlah klip (moment) yang sudah diupload ke YouTube hari ini
        cursor.execute("""
            SELECT COUNT(*) FROM moments
            WHERE is_uploaded = 1 AND is_selected = 1 AND upload_tanggal = ?
        """, (today,))
        yt_count = cursor.fetchone()[0]

        # Hitung jumlah klip (moment) yang sudah diupload ke Facebook hari ini
        cursor.execute("""
            SELECT COUNT(*) FROM moments
            WHERE is_uploaded_fb = 1 AND is_selected = 1 AND upload_tanggal_fb = ?
        """, (today,))
        fb_count = cursor.fetchone()[0]

        # YouTube: cari video berikutnya yang perlu diupload
        if yt_count < limit:
            with queued_videos_lock:
                skip_ids = queued_videos | active_processes
            if skip_ids:
                placeholders = ",".join("?" * len(skip_ids))
                query_args = list(skip_ids)
                skip_clause = f"AND v.id NOT IN ({placeholders})"
            else:
                skip_clause = ""
                query_args = []
            cursor.execute(f"""
                SELECT v.id FROM videos v
                WHERE v.status_potong = 'success'
                AND v.id NOT IN (
                    SELECT DISTINCT video_id FROM moments
                    WHERE is_uploaded = 1 AND is_selected = 1
                )
                {skip_clause}
                ORDER BY v.id ASC LIMIT 1
            """, query_args)
            row = cursor.fetchone()
            if row:
                vid = row[0]
                with queued_videos_lock:
                    queued_videos.add(vid)
                log_message(vid, f"[Auto-Upload] Enqueue YouTube (sisa kuota: {limit - yt_count})")
                task_queue.put({"video_id": vid, "stage": "upload"})

        # Facebook: cari video berikutnya yang perlu diupload
        if fb_count < limit:
            with queued_videos_lock:
                skip_ids = queued_videos | active_processes
            if skip_ids:
                placeholders = ",".join("?" * len(skip_ids))
                query_args = list(skip_ids)
                skip_clause = f"AND v.id NOT IN ({placeholders})"
            else:
                skip_clause = ""
                query_args = []
            cursor.execute(f"""
                SELECT v.id FROM videos v
                WHERE v.status_potong = 'success'
                AND v.id NOT IN (
                    SELECT DISTINCT video_id FROM moments
                    WHERE is_uploaded_fb = 1 AND is_selected = 1
                )
                {skip_clause}
                ORDER BY v.id ASC LIMIT 1
            """, query_args)
            row = cursor.fetchone()
            if row:
                vid = row[0]
                with queued_videos_lock:
                    queued_videos.add(vid)
                log_message(vid, f"[Auto-Upload] Enqueue Facebook (sisa kuota: {limit - fb_count})")
                task_queue.put({"video_id": vid, "stage": "facebook"})

        conn.close()
    except Exception as ex:
        print(f"[Auto-Upload Error] {ex}")


def auto_upload_scheduler():
    """Thread yang berjalan terus menerus untuk auto-upload"""
    print("[Auto-Upload] Scheduler aktif.")
    while True:
        try:
            auto_upload_check_once()
        except Exception as ex:
            print(f"[Auto-Upload Error] {ex}")
        time.sleep(300)  # Cek setiap 5 menit


@app.get("/api/schedules")
def get_schedules():
    """Mengambil semua jadwal yang ada"""
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT s.*, v.judul_video, v.channel_video
            FROM schedules s
            LEFT JOIN videos v ON v.id = s.video_id
            ORDER BY s.scheduled_at ASC
        """)
        rows = cursor.fetchall()
    return [dict(r) for r in rows]


@app.post("/api/schedules")
def create_schedule(payload: ScheduleInput):
    """Membuat jadwal baru untuk proses otomatis"""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Validasi video ada
    cursor.execute("SELECT id FROM videos WHERE id = ?", (payload.video_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Video tidak ditemukan.")
    cursor.execute("""
        INSERT INTO schedules (video_id, stage, scheduled_at, repeat, status)
        VALUES (?, ?, ?, ?, 'pending')
    """, (payload.video_id, payload.stage, payload.scheduled_at, payload.repeat))
    sched_id = cursor.lastrowid
    conn.commit()
    conn.close()
    log_message(payload.video_id, f"📅 Jadwal baru dibuat: ID {sched_id} — '{payload.stage}' pada {payload.scheduled_at} (repeat: {payload.repeat})")
    return {"success": True, "schedule_id": sched_id}


@app.delete("/api/schedules/{schedule_id}")
def delete_schedule(schedule_id: int):
    """Menghapus jadwal berdasarkan ID"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
    conn.commit()
    conn.close()
    return {"success": True}


@app.get("/api/auto-upload/status")
def get_auto_upload_status():
    """Mengambil status auto-upload: kuota terpakai dan sisa hari ini"""
    today = datetime.now().strftime("%Y-%m-%d")
    app_cfg = load_app_config()
    auto_cfg = app_cfg.get("auto_upload", DEFAULT_CONFIG["auto_upload"])
    limit = auto_cfg.get("limit_per_day", 30)

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) FROM moments
        WHERE is_uploaded = 1 AND is_selected = 1 AND upload_tanggal = ?
    """, (today,))
    yt_uploaded = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM moments
        WHERE is_uploaded_fb = 1 AND is_selected = 1 AND upload_tanggal_fb = ?
    """, (today,))
    fb_uploaded = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(DISTINCT v.id) FROM videos v
        JOIN moments m ON m.video_id = v.id
        WHERE v.status_potong = 'success' AND m.is_selected = 1
        AND v.id NOT IN (
            SELECT DISTINCT video_id FROM moments WHERE is_uploaded = 1
        )
    """)
    pending_queue = cursor.fetchone()[0]

    conn.close()

    return {
        "enabled": auto_cfg.get("enabled", True),
        "limit_per_day": limit,
        "youtube_uploaded_today": yt_uploaded,
        "youtube_remaining": max(0, limit - yt_uploaded),
        "facebook_uploaded_today": fb_uploaded,
        "facebook_remaining": max(0, limit - fb_uploaded),
        "pending_queue": pending_queue
    }
@app.post("/api/auto-upload/trigger")
def trigger_auto_upload():
    """Memicu auto-upload langsung untuk semua video yang siap hari ini"""
    try:
        count = 0
        app_cfg = load_app_config()
        auto_cfg = app_cfg.get("auto_upload", {"enabled": True, "limit_per_day": 30})
        if not auto_cfg.get("enabled", True):
            return {"success": False, "message": "Auto-upload sedang nonaktif", "enqueued": 0}

        limit = auto_cfg.get("limit_per_day", 30)
        today = datetime.now().strftime("%Y-%m-%d")

        conn = get_db_connection()
        cursor = conn.cursor()

        # Hitung YT upload count today
        cursor.execute("""
            SELECT COUNT(*) FROM moments
            WHERE is_uploaded = 1 AND is_selected = 1 AND upload_tanggal = ?
        """, (today,))
        yt_count = cursor.fetchone()[0]

        # Hitung FB upload count today
        cursor.execute("""
            SELECT COUNT(*) FROM moments
            WHERE is_uploaded_fb = 1 AND is_selected = 1 AND upload_tanggal_fb = ?
        """, (today,))
        fb_count = cursor.fetchone()[0]

        with queued_videos_lock:
            skip_ids = queued_videos | active_processes

        def skip_clause_fn(skip):
            if skip:
                placeholders = ",".join("?" * len(skip))
                return f"AND v.id NOT IN ({placeholders})", list(skip)
            return "", []

        # YouTube
        if yt_count < limit:
            skips = skip_ids.copy()
            skips.update(queued_videos)
            sc, qa = skip_clause_fn(skips)
            cursor.execute(f"""
                SELECT v.id, v.judul_video FROM videos v
                WHERE v.status_potong = 'success'
                AND v.id NOT IN (
                    SELECT DISTINCT video_id FROM moments
                    WHERE is_uploaded = 1 AND is_selected = 1
                )
                {sc}
                ORDER BY v.id ASC LIMIT 5
            """, qa)
            rows = cursor.fetchall()
            for row in rows:
                vid = row[0]
                with queued_videos_lock:
                    if vid in (queued_videos | active_processes):
                        continue
                    queued_videos.add(vid)
                log_message(vid, f"[Auto-Upload Trigger] Enqueue YouTube (sisa: {limit - yt_count - count})")
                task_queue.put({"video_id": vid, "stage": "upload"})
                count += 1
                yt_count += 1
                if yt_count >= limit:
                    break

        # Facebook
        if fb_count < limit:
            skips = skip_ids.copy()
            skips.update(queued_videos)
            sc, qa = skip_clause_fn(skips)
            cursor.execute(f"""
                SELECT v.id, v.judul_video FROM videos v
                WHERE v.status_potong = 'success'
                AND v.id NOT IN (
                    SELECT DISTINCT video_id FROM moments
                    WHERE is_uploaded_fb = 1 AND is_selected = 1
                )
                {sc}
                ORDER BY v.id ASC LIMIT 5
            """, qa)
            rows = cursor.fetchall()
            for row in rows:
                vid = row[0]
                with queued_videos_lock:
                    if vid in (queued_videos | active_processes):
                        continue
                    queued_videos.add(vid)
                log_message(vid, f"[Auto-Upload Trigger] Enqueue Facebook (sisa: {limit - fb_count})")
                task_queue.put({"video_id": vid, "stage": "facebook"})
                count += 1
                fb_count += 1
                if fb_count >= limit:
                    break

        conn.close()

        if count > 0:
            log_message(None, f"[Auto-Upload Trigger] {count} video ditambahkan ke antrean upload")
        else:
            log_message(None, "[Auto-Upload Trigger] Tidak ada video yang perlu diupload")
        return {"success": True, "message": f"{count} video diantrekan untuk upload", "enqueued": count}
    except Exception as ex:
        log_message(None, f"[Auto-Upload Trigger Error] {ex}")
        return {"success": False, "message": str(ex), "enqueued": 0}


@app.get("/api/logs/stream")
async def stream_logs(request: Request):
    """Endpoint Server-Sent Events (SSE) untuk streaming log real-time ke browser"""
    async def event_generator():
        q = asyncio.Queue()
        with log_lock:
            log_listeners.add(q)
        try:
            with log_lock:
                hist = list(log_history)
            for msg in hist:
                yield f"data: {json.dumps(msg)}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=1.0)
                    yield f"data: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    yield "event: heartbeat\ndata: ping\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            with log_lock:
                log_listeners.discard(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# ----------------- SERVING STATIC FILES & FRONTEND -----------------

os.makedirs("clips_output", exist_ok=True)
os.makedirs("videos_podcast", exist_ok=True)
app.mount("/clips", StaticFiles(directory="clips_output"), name="clips")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/", StaticFiles(directory="web_static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    migrate_db()

    print("\n" + "="*60)
    print("[SERVER] SERVER NUROHMAN CLIPPER AKTIF!")
    print("Silakan buka browser Anda dan akses:")
    print("-> http://localhost:8000")
    print("="*60 + "\n")

    uvicorn.run("web_server:app", host="127.0.0.1", port=8000, reload=True)
