import os
import sys

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

os.chdir(get_base_dir())

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
from yt_dlp import YoutubeDL

import re

def unduh_video_youtube(url_video, folder_tujuan="downloads"):
    if not os.path.exists(folder_tujuan):
        os.makedirs(folder_tujuan)
        print(f"Membuat folder baru: '{folder_tujuan}'")

    yt_id_match = re.search(r'(?:v=|\/shorts\/|\/embed\/|\/v\/|youtu\.be\/|\/videos\/)([a-zA-Z0-9_-]{11})', url_video)
    yt_id = yt_id_match.group(1) if yt_id_match else None
    if yt_id:
        existing = os.path.join(folder_tujuan, f"{yt_id}.mp4")
        if os.path.exists(existing):
            print(f"[Info] File sudah ada: {existing}. Skip download.", flush=True)
            print("PROGRESS_DOWNLOAD|100.0|—|—|—", flush=True)
            return

    def progress_hook(d):
        if d['status'] == 'downloading':
            # Emit format khusus yang mudah di-parse frontend
            pct_raw = d.get('_percent_str', '0%').strip().replace('%','').strip()
            speed   = d.get('_speed_str', '?').strip()
            eta     = d.get('_eta_str', '?').strip()
            total   = d.get('_total_bytes_str', d.get('_total_bytes_estimate_str', '?')).strip()
            try:
                pct = float(pct_raw)
            except ValueError:
                pct = 0.0
            # Format khusus: PROGRESS_DOWNLOAD|persen|speed|eta|total
            print(f"PROGRESS_DOWNLOAD|{pct:.1f}|{speed}|{eta}|{total}", flush=True)
        elif d['status'] == 'finished':
            print("PROGRESS_DOWNLOAD|100.0|—|—|—", flush=True)
            print(f"[Download] File selesai diunduh: {d.get('filename','')}", flush=True)
        elif d['status'] == 'error':
            print("[Download] Error saat mengunduh.", flush=True)

    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': os.path.join(folder_tujuan, '%(id)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'progress_hooks': [progress_hook],
        'quiet': True,       # Matikan output bawaan yt-dlp agar tidak berisik
        'no_warnings': True,
    }
    
    # Cek cookies.txt opsional
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'
    else:
        print("[Info] File cookies.txt tidak ditemukan. Download mungkin gagal untuk video age-restricted.", flush=True)

    print(f"Memulai proses pengunduhan untuk link: {url_video}", flush=True)
    print("PROGRESS_DOWNLOAD|0.0|—|—|—", flush=True)

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url_video, download=True)
            judul_video = info.get('title', 'Video')

        print(f"\n[Sukses] Berhasil mengunduh: '{judul_video}'", flush=True)
        print(f"File disimpan di folder: '{os.path.abspath(folder_tujuan)}'", flush=True)

    except Exception as e:
        print(f"\n[Gagal] Terjadi kesalahan saat mengunduh video: {e}", flush=True)

# --- Bagian Utama Program ---
if __name__ == "__main__":
    # Cek apakah user sudah memasukkan parameter link
    if len(sys.argv) < 2:
        print("\n[Error] Anda belum memasukkan link YouTube!")
        print("Cara menjalankan: python .\\download_youtube.py <LINK_YOUTUBE>")
        print("Contoh: python .\\download_youtube.py https://www.youtube.com/watch?v=3Ldsu0zukwo\n")
        sys.exit(1)
        
    # Mengambil link dari parameter pertama terminal
    link_target = sys.argv[1]
    
    # Menjalankan fungsi unduh
    unduh_video_youtube(link_target, folder_tujuan="videos_podcast")