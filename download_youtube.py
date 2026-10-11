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
import shutil

COOKIE_LOGIN_NAMES = ('SID', 'HSID', 'SSID', 'LOGIN_INFO')


def cookies_punya_login(path='cookies.txt'):
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for baris in f:
                baris = baris.strip()
                if not baris or baris.startswith('#'):
                    continue
                kolom = baris.split('\t')
                if len(kolom) >= 6 and kolom[5] in COOKIE_LOGIN_NAMES:
                    return True
    except OSError:
        pass
    return False


def buat_opts(folder_tujuan, hook, pakai_cookies):
    opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best',
        'outtmpl': os.path.join(folder_tujuan, '%(id)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'progress_hooks': [hook],
        'quiet': True,       # Matikan output bawaan yt-dlp agar tidak berisik
        'no_warnings': True,
        'retries': 3,
        'fragment_retries': 3,
        'extractor_args': {'youtube': {'player_client': ['web', 'android']}},
    }
    if not shutil.which('deno') and shutil.which('node'):
        opts['js_runtimes'] = {'node': {}}
    if pakai_cookies:
        opts['cookiefile'] = 'cookies.txt'
    return opts


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

    ada_cookies = os.path.exists('cookies.txt')
    cookies_valid = ada_cookies and cookies_punya_login()
    if ada_cookies and not cookies_valid:
        print("[Peringatan] cookies.txt tidak berisi cookie login YouTube (basi) — diabaikan agar tidak error 403.", flush=True)
        print("[Info] Export ulang cookies.txt dari browser yang login YouTube bila butuh video age-restricted.", flush=True)
    elif not ada_cookies:
        print("[Info] File cookies.txt tidak ditemukan. Download mungkin gagal untuk video age-restricted.", flush=True)

    strategi = [True, False] if cookies_valid else [False]

    print(f"Memulai proses pengunduhan untuk link: {url_video}", flush=True)
    print("PROGRESS_DOWNLOAD|0.0|—|—|—", flush=True)

    error_terakhir = None
    for pakai_cookies in strategi:
        if pakai_cookies:
            print("[Info] Mencoba download memakai cookies.txt ...", flush=True)
        try:
            with YoutubeDL(buat_opts(folder_tujuan, progress_hook, pakai_cookies)) as ydl:
                info = ydl.extract_info(url_video, download=True)
                judul_video = info.get('title', 'Video')

            print(f"\n[Sukses] Berhasil mengunduh: '{judul_video}'", flush=True)
            print(f"File disimpan di folder: '{os.path.abspath(folder_tujuan)}'", flush=True)
            return
        except Exception as e:
            error_terakhir = e
            pesan_error = str(e).lower()
            cookies_bermasalah = '403' in pesan_error or 'cookie' in pesan_error
            if pakai_cookies and cookies_bermasalah:
                print("[Peringatan] Download dengan cookies gagal. Coba ulang tanpa cookies ...", flush=True)
                continue
            break

    print(f"\n[Gagal] Terjadi kesalahan saat mengunduh video: {error_terakhir}", flush=True)
    sys.exit(1)

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
