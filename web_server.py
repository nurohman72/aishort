import os
import sys
import json
import queue
import sqlite3
import threading
import subprocess
from datetime import datetime
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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_FILE = "database_konten.db"

# ----------------- DATABASE MANAGEMENT & MIGRATION -----------------
def migrate_db():
    print("[DB] Menjalankan inisialisasi dan migrasi database...")
    conn = sqlite3.connect(DB_FILE)
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
        "error_message": "TEXT"
    }
    
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
            
    # Broadcast log
    loop = None
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        pass
        
    for q in list(log_listeners):
        if loop and loop.is_running():
            loop.call_soon_threadsafe(q.put_nowait, msg)
        else:
            # Fallback jika di luar main loop async
            q.put_nowait(msg)

# ----------------- BACKGROUND SEQUENTIAL WORKER -----------------
task_queue = queue.Queue()

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def update_video_status(video_id: int, **kwargs):
    """Mengupdate status kolom video di database secara cepat"""
    conn = get_db_connection()
    cursor = conn.cursor()
    set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
    values = list(kwargs.values())
    values.append(video_id)
    cursor.execute(f"UPDATE videos SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()

def execute_subprocess_live(video_id: int, stage: str, cmd: List[str]) -> bool:
    """Mengeksekusi perintah subprocess Python dan menangkap output log per baris secara real-time"""
    log_message(video_id, f"⚡ MEMULAI TAHAP: {stage.upper()}")
    log_message(video_id, f"Eksekusi perintah: {' '.join(cmd)}")
    
    try:
        env_custom = os.environ.copy()
        env_custom["PYTHONUNBUFFERED"] = "1"
        env_custom["FONTCONFIG_FILE"] = "<nul>"
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=False,
            bufsize=1,
            env=env_custom
        )
        
        # Baca output stdout live baris demi baris
        for line in process.stdout:
            clean_line = line.strip()
            if clean_line:
                log_message(video_id, clean_line)
                
        process.wait()
        success = (process.returncode == 0)
        log_message(video_id, f"🏁 TAHAP {stage.upper()} selesai dengan exit code: {process.returncode}")
        return success
    except Exception as e:
        log_message(video_id, f"❌ [ERROR KRITIS] Gagal menjalankan tahap {stage}: {str(e)}")
        return False

def background_worker():
    """Background thread worker yang memproses tugas satu per satu"""
    print("[Worker] Background Thread Worker aktif dan siap memproses antrean.")
    while True:
        try:
            task = task_queue.get()
            if task is None:
                break
                
            video_id = task["video_id"]
            stage = task["stage"]
            
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
            
            log_message(video_id, f"\n🚀 [Queue] Memproses Video: '{video_title}' (ID: {video_id})")
            
            # --- JALANKAN PIPELINE TAHAP DEMI TAHAP ---
            stages_to_run = []
            if stage == "all":
                stages_to_run = ["analisa", "download", "potong", "upload"]
            else:
                stages_to_run = [stage]
                
            # Mapping nama stage ke nama kolom DB yang benar
            STAGE_COL = {
                "analisa":  "status_analisis",
                "download": "status_download",
                "potong":   "status_potong",
                "upload":   "status_upload",
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
                    
                # Eksekusi
                stage_success = execute_subprocess_live(video_id, current_stage, cmd)
                
                if stage_success:
                    update_video_status(video_id, **{status_key: "success"})
                else:
                    update_video_status(video_id, **{status_key: "failed", "error_message": f"Gagal pada tahap {current_stage}"})
                    success = False
                    log_message(video_id, f"❌ Pipeline dihentikan karena kegagalan pada tahap: {current_stage}")
                    break  # Stop pipeline jika ada yang gagal di tengah jalan
                    
            if success and stage == "all":
                log_message(video_id, "🎉 [SUKSES TOTAL] Pipeline otomatis All-in-One selesai dengan sukses!")
                
            task_queue.task_done()
        except Exception as ex:
            print(f"[Worker Error] Terjadi kendala: {ex}")
            log_message(None, f"[Worker Error] Kendala fatal: {ex}")

# Jalankan background thread saat startup
worker_thread = threading.Thread(target=background_worker, daemon=True)
worker_thread.start()

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

class ScheduleInput(BaseModel):
    video_id: int
    stage: str
    scheduled_at: str  # Format: "YYYY-MM-DD HH:MM"
    repeat: str = "once"  # once | daily | weekly

# ----------------- API ENDPOINTS -----------------

@app.on_event("startup")
def startup_event():
    migrate_db()
    # Pastikan folder esensial ada
    for folder in ["videos_podcast", "clips_output"]:
        if not os.path.exists(folder):
            os.makedirs(folder)

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
                status_upload    = CASE WHEN status_upload    = 'processing' THEN 'failed' ELSE status_upload    END
            WHERE status_analisis = 'processing'
               OR status_download  = 'processing'
               OR status_potong    = 'processing'
               OR status_upload    = 'processing'
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

@app.get("/api/videos")
def get_videos():
    """Mengambil daftar video di database diurutkan berdasarkan tanggal terbaru dengan SQLite JOIN tunggal"""
    conn = get_db_connection()
    cursor = conn.cursor()
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
    conn.close()
    
    videos = []
    for r in rows:
        v = dict(r)
        # Tangani nilai null dari aggregation
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
    """Mengambil daftar momen hasil analisa Gemini untuk video tertentu"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM moments WHERE video_id = ? ORDER BY id ASC", (video_id,))
    rows = cursor.fetchall()
    conn.close()
    
    moments = []
    for r in rows:
        m = dict(r)
        # Tambahkan path video hasil potong jika sudah ada di folder clips_output
        file_clip_name = f"{video_id}_{m['id']}.mp4"
        path_clip = os.path.join("clips_output", file_clip_name)
        m["has_clip"] = os.path.exists(path_clip)
        m["clip_url"] = f"/clips/{file_clip_name}" if m["has_clip"] else None
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
    if stage not in ["analisa", "download", "potong", "upload", "all"]:
        raise HTTPException(status_code=400, detail="Tahapan proses tidak dikenal.")
        
    # Tambahkan tugas ke antrean latar belakang
    task_queue.put({"video_id": video_id, "stage": stage})
    log_message(video_id, f"📥 Masuk Antrean Latar Belakang: Tahap '{stage.upper()}'")
    
    # Update status ke pending/waiting di DB agar UI langsung merespon visual
    STAGE_COL = {
        "analisa":  "status_analisis",
        "download": "status_download",
        "potong":   "status_potong",
        "upload":   "status_upload",
    }
    if stage != "all":
        update_video_status(video_id, **{STAGE_COL[stage]: "processing"})
    else:
        update_video_status(video_id,
            status_analisis="processing",
            status_download="processing",
            status_potong="processing",
            status_upload="processing"
        )
        
    return {"success": True, "message": f"Tugas {stage} berhasil didaftarkan ke antrean."}

# ----------------- CONFIGURATION MANAGEMENT -----------------
ENV_FILE = "environment.txt"

@app.get("/api/config")
def get_config():
    """Membaca pengaturan/konfigurasi aplikasi dari environment.txt dan script default"""
    gemini_key = ""
    if os.path.exists(ENV_FILE):
        try:
            with open(ENV_FILE, "r") as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY="):
                        gemini_key = line.replace("GEMINI_API_KEY=", "").strip()
        except Exception as e:
            print(f"Gagal baca config: {e}")
            
    # Baca setingan caption dari potong_video.py secara dinamis jika memungkinkan
    # Kita berikan nilai fallback default yang sesuai dengan file potong_video.py Anda
    enable_caption = True
    font_name = "Cooper Black"
    font_size = "6"
    whisper_model = "base"
    
    # Cek file potong_video.py untuk membaca variabel terkininya
    if os.path.exists("potong_video.py"):
        try:
            with open("potong_video.py", "r") as f:
                for line in f:
                    if "ENABLE_AUTOCAPTION =" in line:
                        enable_caption = ("True" in line)
                    elif "AUTOCAPTION_FONT =" in line:
                        font_name = line.split("=")[1].replace('"', '').replace("'", "").strip()
                    elif "AUTOCAPTION_FONTSIZE =" in line:
                        font_size = line.split("=")[1].replace('"', '').replace("'", "").strip()
                    elif "AUTOCAPTION_MODEL =" in line:
                        whisper_model = line.split("=")[1].replace('"', '').replace("'", "").strip()
        except Exception as e:
            print(f"Peringatan membaca config dari potong_video.py: {e}")
            
    # Cek YouTube OAuth token.pickle status
    has_youtube_auth = os.path.exists("token.pickle")
    
    return {
        "gemini_key": gemini_key,
        "enable_caption": enable_caption,
        "font_name": font_name,
        "font_size": font_size,
        "whisper_model": whisper_model,
        "has_youtube_auth": has_youtube_auth
    }

@app.post("/api/config")
def update_config(payload: ConfigUpdate):
    """Menyimpan Gemini API key ke environment.txt dan memperbarui setingan di potong_video.py"""
    # 1. Simpan Gemini API Key
    try:
        with open(ENV_FILE, "w") as f:
            f.write(f"GEMINI_API_KEY={payload.gemini_key.strip()}\n")
        log_message(None, "⚙️ Gemini API Key berhasil diperbarui di environment.txt.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal menulis environment.txt: {e}")
        
    # 2. Perbarui variabel di potong_video.py
    if os.path.exists("potong_video.py"):
        try:
            with open("potong_video.py", "r") as f:
                lines = f.readlines()
                
            new_lines = []
            for line in lines:
                if line.startswith("ENABLE_AUTOCAPTION ="):
                    new_lines.append(f"ENABLE_AUTOCAPTION = {payload.enable_caption}\n")
                elif line.startswith("AUTOCAPTION_FONT ="):
                    new_lines.append(f"AUTOCAPTION_FONT = \"{payload.font_name}\"\n")
                elif line.startswith("AUTOCAPTION_FONTSIZE ="):
                    new_lines.append(f"AUTOCAPTION_FONTSIZE = \"{payload.font_size}\"\n")
                elif line.startswith("AUTOCAPTION_MODEL ="):
                    new_lines.append(f"AUTOCAPTION_MODEL = \"{payload.whisper_model}\"\n")
                else:
                    new_lines.append(line)
                    
            with open("potong_video.py", "w") as f:
                f.writelines(new_lines)
            log_message(None, "⚙️ Pengaturan video caption diperbarui di potong_video.py.")
        except Exception as e:
            log_message(None, f"[Warning] Gagal mengupdate potong_video.py: {e}")
            
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
                
        threading.Thread(target=login_task, daemon=True).start()
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
                    from datetime import timedelta
                    next_run = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
                    c2.execute("UPDATE schedules SET scheduled_at=?, last_run=? WHERE id=?", (next_run, now_str, sched_id))
                elif repeat == "weekly":
                    from datetime import timedelta
                    next_run = (datetime.now() + timedelta(weeks=1)).strftime("%Y-%m-%d %H:%M")
                    c2.execute("UPDATE schedules SET scheduled_at=?, last_run=? WHERE id=?", (next_run, now_str, sched_id))
                conn2.commit()
                conn2.close()
        except Exception as ex:
            print(f"[Scheduler Error] {ex}")
        time.sleep(30)  # Cek setiap 30 detik


@app.get("/api/schedules")
def get_schedules():
    """Mengambil semua jadwal yang ada"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.*, v.judul_video, v.channel_video
        FROM schedules s
        LEFT JOIN videos v ON v.id = s.video_id
        ORDER BY s.scheduled_at ASC
    """)
    rows = cursor.fetchall()
    conn.close()
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


# ----------------- REAL-TIME LOG STREAM -----------------
@app.get("/api/logs/stream")
async def stream_logs(request: Request):
    """Endpoint Server-Sent Events (SSE) untuk streaming log real-time ke browser"""
    async def event_generator():
        q = asyncio.Queue()
        log_listeners.add(q)
        try:
            # Kirim log history awal agar konsol web terisi riwayat
            with log_lock:
                for msg in log_history:
                    yield f"data: {json.dumps(msg)}\n\n"
                    
            while True:
                # Periksa apakah klien memutuskan koneksi
                if await request.is_disconnected():
                    break
                try:
                    # Ambil log baru yang masuk
                    msg = await asyncio.wait_for(q.get(), timeout=1.0)
                    yield f"data: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    # Kirim heartbeat tipis agar koneksi tetap hidup
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            log_listeners.remove(q)
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

# ----------------- SERVING STATIC FILES & FRONTEND -----------------

# Sajikan file video hasil pemotongan agar video player di browser dapat membacanya langsung
app.mount("/clips", StaticFiles(directory="clips_output"), name="clips")

# Sajikan folder statis frontend web_static
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)

app.mount("/", StaticFiles(directory="web_static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    # Migrasi database saat startup script dijalankan secara langsung
    migrate_db()
    
    print("\n" + "="*60)
    print("[SERVER] SERVER NUROHMAN CLIPPER AKTIF!")
    print("Silakan buka browser Anda dan akses:")
    print("-> http://localhost:8000")
    print("="*60 + "\n")
    
    uvicorn.run("web_server:app", host="127.0.0.1", port=8000, reload=True)
