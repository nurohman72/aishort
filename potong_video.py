import os
import re
import sys
import sqlite3
import subprocess
from datetime import datetime, timedelta

# Fix encoding untuk Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def safe_print(text):
    """Print text dengan handling encoding yang aman untuk Windows"""
    try:
        print(text)
    except UnicodeEncodeError:
        try:
            import sys as _sys
            encoded_bytes = text.encode(_sys.stdout.encoding or 'utf-8', errors='replace')
            print(encoded_bytes.decode(_sys.stdout.encoding or 'utf-8'))
        except Exception:
            print(text.encode('utf-8', errors='replace').decode('utf-8', errors='replace'))

def cek_ffmpeg():
    """Memastikan FFmpeg tersedia di PATH"""
    try:
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("[Error] FFmpeg tidak ditemukan! Pastikan FFmpeg terinstal dan tersedia di PATH.")
        sys.exit(1)

# --- Parameter Auto-Captioning ---
ENABLE_AUTOCAPTION = True
AUTOCAPTION_MODEL = "small"
AUTOCAPTION_FONT = "Cooper Black"
AUTOCAPTION_FONTSIZE = "6"
AUTOCAPTION_ALIGN = "2"
AUTOCAPTION_MARGIN_V = "100"
AUTOCAPTION_MARGIN_H = "0"

def dapatkan_data_momen(video_id):
    """Mengambil data URL video dan daftar momen berdasarkan ID Video dari SQLite"""
    conn = sqlite3.connect("database_konten.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT url FROM videos WHERE id = ?", (video_id,))
    video_row = cursor.fetchone()
    
    if not video_row:
        print(f"[Error] ID Video {video_id} tidak ditemukan di database!")
        conn.close()
        sys.exit(1)
        
    video_url = video_row[0]
    
    cursor.execute("""
        SELECT id, waktu_start, waktu_selesai, judul_menarik 
        FROM moments 
        WHERE video_id = ? AND is_selected = 1
        ORDER BY id ASC
    """, (video_id,))
    
    moments = cursor.fetchall()
    conn.close()
    
    return video_url, moments

def cari_file_video_asli(video_url, folder_input="videos_podcast"):
    if not os.path.exists(folder_input):
        print(f"[Error] Folder '{folder_input}' tidak ditemukan!")
        sys.exit(1)
        
    match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', video_url)
    yt_id = match.group(1) if match else None
    
    if yt_id:
        path_spesifik = os.path.join(folder_input, f"{yt_id}.mp4")
        if os.path.exists(path_spesifik):
            return path_spesifik
            
    # Fallback ke pencarian berkas mp4 pertama (untuk backward compatibility)
    files = [f for f in os.listdir(folder_input) if f.endswith('.mp4')]
    
    if not files:
        print(f"[Error] Tidak ada file .mp4 ditemukan di dalam folder '{folder_input}'!")
        sys.exit(1)
        
    return os.path.join(folder_input, files[0])

def potong_dan_format_916(file_input, video_id, moment_id, waktu_start, waktu_selesai, judul_momen, folder_output="clips_output", total_momen=1, urutan=1):
    """Memotong video ke 9:16 dengan font JUMBO (Size 70) Auto-Wrap hingga 4 BARIS dan logo brand 540px"""
    if not os.path.exists(folder_output):
        os.makedirs(folder_output)
        
    nama_file_output = f"{video_id}_{moment_id}.mp4"
    path_output = os.path.join(folder_output, nama_file_output)
    
    # Jika autocaption aktif, simpan hasil FFmpeg awal ke file sementara (_nocap.mp4)
    # Jika tidak aktif, langsung simpan ke path_output
    path_ffmpeg_output = os.path.join(folder_output, f"{video_id}_{moment_id}_nocap.mp4") if ENABLE_AUTOCAPTION else path_output
    
    path_font = "COOPBL.TTF"
    path_logo = "logo.png"
    
    if not os.path.exists(path_font) or not os.path.exists(path_logo):
        print(f"   [Error] Pastikan COOPBL.TTF dan logo.png ada di folder script!")
        return

    # 1. SANITASI TEKS (hapus karakter berbahaya untuk FFmpeg drawtext)
    judul_clean = judul_momen.replace("'", "").replace('"', '').replace("\\", "").replace("%", "").replace(":", "").replace("\n", " ").strip()
    
    # 2. LOGIKA AUTO-WRAP 4 BARIS JUMBO (Maks 16 karakter per baris)
    words = judul_clean.split()
    baris1, baris2, baris3, baris4 = "", "", "", ""
    
    for word in words:
        if len(baris1) + len(word) + 1 <= 16:
            baris1 = f"{baris1} {word}".strip()
        elif len(baris2) + len(word) + 1 <= 16:
            baris2 = f"{baris2} {word}".strip()
        elif len(baris3) + len(word) + 1 <= 16:
            baris3 = f"{baris3} {word}".strip()
        elif len(baris4) + len(word) + 1 <= 16:
            baris4 = f"{baris4} {word}".strip()
        else:
            # Jika terpaksa meluber dari 4 baris (sangat jarang), baru diberi ...
            if not baris4.endswith("..."):
                baris4 = (baris4 + " " + word)[:13].strip() + "..."
            break

    # 3. HITUNG DURASI DARI waktu_selesai - waktu_start, MAX 59 DETIK
    durasi_detik = hitung_durasi_dari_waktu(waktu_start, waktu_selesai)
    if durasi_detik <= 0:
        durasi_detik = 59  # Fallback ke durasi standar
    
    # BATASI DURASI MAX 59 DETIK (YouTube Shorts limit)
    if durasi_detik > 59:
        safe_print(f"   [Info] Durasi ({durasi_detik:.1f} detik) terlalu panjang, memotong ke 59 detik...")
        durasi_detik = 59
    
    # 4. STRUKTUR FILTER TEXT FFMPEG JUMBO
    base_text_filter = (
        f"fontfile={path_font}:fontcolor=white:fontsize=70:"
        f"box=1:boxcolor=black@0.4:boxborderw=14:"
        f"borderw=6:bordercolor=black:x=(w-text_w)/2"
    )
    
    # 5. LOGIKA FILTER GRAFIS + LOGO OVERLAY
    filter_base = (
        "[0:v]split=2[bg_src][fg_src];"
        "[bg_src]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=luma_radius=25:luma_power=3[bg];"
        "[fg_src]scale=1080:-1[fg];"
        "[bg][fg]overlay=0:(main_h-overlay_h)/2[vid_basemix];"
        "[1:v]scale=540:-1[logo_resized];"
        "[vid_basemix][logo_resized]overlay=(main_w-overlay_w)/2:1320[v_with_logo]"
    )
    
    # Koordinat Y diatur mulai dari y=90 agar jika mencapai 4 baris tidak menabrak video utama di tengah
    if baris4:
        filter_grafis = (
            f"{filter_base};"
            f"[v_with_logo]drawtext={base_text_filter}:text='{baris1}':y=90[txt1];"
            f"[txt1]drawtext={base_text_filter}:text='{baris2}':y=190[txt2];"
            f"[txt2]drawtext={base_text_filter}:text='{baris3}':y=290[txt3];"
            f"[txt3]drawtext={base_text_filter}:text='{baris4}':y=390"
        )
    elif baris3:
        filter_grafis = (
            f"{filter_base};"
            f"[v_with_logo]drawtext={base_text_filter}:text='{baris1}':y=140[txt1];"
            f"[txt1]drawtext={base_text_filter}:text='{baris2}':y=240[txt2];"
            f"[txt2]drawtext={base_text_filter}:text='{baris3}':y=340"
        )
    elif baris2:
        filter_grafis = (
            f"{filter_base};"
            f"[v_with_logo]drawtext={base_text_filter}:text='{baris1}':y=190[txt1];"
            f"[txt1]drawtext={base_text_filter}:text='{baris2}':y=290"
        )
    else:
        filter_grafis = (
            f"{filter_base};"
            f"[v_with_logo]drawtext={base_text_filter}:text='{baris1}':y=240"
        )
    
    perintah = [
        'ffmpeg', '-y',
        '-ss', waktu_start,
        '-i', file_input,
        '-i', path_logo,
        '-t', str(durasi_detik),
        '-filter_complex', filter_grafis,
        '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac',
        '-b:a', '192k',
        path_ffmpeg_output
    ]
    
    print(f"-> Memproses video Shorts ID {moment_id} ({waktu_start} - {waktu_selesai}) + 4 Baris Font Jumbo...", flush=True)
    # Emit progress awal untuk momen ini
    print(f"PROGRESS_POTONG|{urutan}|{total_momen}|0|{moment_id}|{judul_momen[:40]}", flush=True)
    try:
        env_kustom = os.environ.copy()
        env_kustom["FONTCONFIG_FILE"] = "<nul>"

        # Jalankan FFmpeg dengan stderr real-time untuk parse progress
        proses = subprocess.Popen(
            perintah,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            env=env_kustom
        )

        # Parse stderr FFmpeg untuk progress — FFmpeg menulis "time=HH:MM:SS.xx" ke stderr
        stderr_lines = []
        for line in proses.stderr:
            stderr_lines.append(line)
            m = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
            if m:
                h, mn, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
                elapsed = h * 3600 + mn * 60 + s
                pct = min(elapsed / durasi_detik * 100, 99.0)
                print(f"PROGRESS_POTONG|{urutan}|{total_momen}|{pct:.1f}|{moment_id}|{judul_momen[:40]}", flush=True)

        proses.wait()
        hasil_returncode = proses.returncode
        hasil_stderr = "".join(stderr_lines)
        
        if hasil_returncode == 0:
            print(f"PROGRESS_POTONG|{urutan}|{total_momen}|100.0|{moment_id}|{judul_momen[:40]}", flush=True)
            if ENABLE_AUTOCAPTION:
                print(f"   [Sukses] Video Shorts 4 Baris + Logo siap (tanpa caption): {path_ffmpeg_output}")
                
                temp_audio = os.path.join(folder_output, f"{video_id}_{moment_id}_temp_audio.wav")
                temp_srt = os.path.join(folder_output, f"{video_id}_{moment_id}_temp_audio.srt")
                
                try:
                    import autocaption
                    print("   -> Menjalankan proses Auto-Caption (Pengekstrakan Audio)...")
                    # 1. Ekstrak audio dari video hasil potongan
                    autocaption.extract_audio(path_ffmpeg_output, temp_audio)
                    
                    # 2. Transkripsi audio dengan Whisper
                    print("   -> Memulai transkripsi audio dengan Whisper...")
                    autocaption.transcribe_audio(temp_audio, temp_srt, model_name=AUTOCAPTION_MODEL)
                    
                    # 3. Burn/gabungkan subtitle ke video final
                    print("   -> Membakar subtitle ke video Shorts...")
                    autocaption.burn_subtitles(
                        video_path=path_ffmpeg_output,
                        srt_path=temp_srt,
                        output_path=path_output,
                        font_name=AUTOCAPTION_FONT,
                        font_size=AUTOCAPTION_FONTSIZE,
                        align=AUTOCAPTION_ALIGN,
                        margin_v=AUTOCAPTION_MARGIN_V,
                        margin_h=AUTOCAPTION_MARGIN_H
                    )
                    print(f"   [Sukses] Video Shorts Auto-Caption siap: {path_output}", flush=True)
                except Exception as e_cap:
                    print(f"   [Peringatan] Gagal memproses Auto-Caption: {e_cap}", flush=True)
                    print("   [Fallback] Menyimpan video Shorts tanpa caption...", flush=True)
                    if os.path.exists(path_output):
                        try:
                            os.remove(path_output)
                        except Exception:
                            pass
                    os.rename(path_ffmpeg_output, path_output)
                finally:
                    # Pembersihan file-file sementara
                    print("   -> Membersihkan berkas sementara...")
                    for temp_file in [path_ffmpeg_output, temp_audio, temp_srt]:
                        if os.path.exists(temp_file):
                            try:
                                os.remove(temp_file)
                            except Exception as e_del:
                                print(f"      [Gagal menghapus] {temp_file}: {e_del}")
            else:
                print(f"   [Sukses] Video Shorts 4 Baris + Logo siap: {path_output}", flush=True)
        else:
            print(f"   [Gagal] FFmpeg error pada momen {moment_id}!", flush=True)
            error_lines = hasil_stderr.strip().split('\n')
            print(f"   [Detail Error]: {error_lines[-4:] if len(error_lines) >= 4 else hasil_stderr}", flush=True)
            
    except Exception as e:
        print(f"   [Gagal] Terjadi kendala eksekusi: {e}")


# Fungsi Bantu: Hitung durasi dari waktu_start dan waktu_selesai
def hitung_durasi_dari_waktu(waktu_start, waktu_selesai):
    """Menghitung durasi dalam detik dari waktu_start ke waktu_selesai"""
    # Handle NULL/None dari database (record lama sebelum migrasi)
    if waktu_selesai is None:
        safe_print("   [Info] waktu_selesai tidak tersedia (NULL), menggunakan durasi default 59 detik")
        return 59
    try:
        # Parse waktu format HH:MM:SS
        parts_start = waktu_start.split(':')
        parts_end = waktu_selesai.split(':')
        
        if len(parts_start) == 3 and len(parts_end) == 3:
            h1, m1, s1 = int(parts_start[0]), int(parts_start[1]), float(parts_start[2])
            h2, m2, s2 = int(parts_end[0]), int(parts_end[1]), float(parts_end[2])
            
            start_detik = h1 * 3600 + m1 * 60 + s1
            end_detik = h2 * 3600 + m2 * 60 + s2
            
            durasi = end_detik - start_detik
            return max(durasi, 1)  # Minimal 1 detik
        else:
            safe_print("   [Info] Format waktu tidak valid, menggunakan durasi default 59 detik")
            return 59  # Fallback
    except Exception as e:
        safe_print(f"   [Info] Gagal hitung durasi ({e}), menggunakan default 59 detik")
        return 59  # Fallback


# --- Alur Utama Program ---
if __name__ == "__main__":
    cek_ffmpeg()
    if len(sys.argv) < 2:
        print("\n[Error] Anda belum memasukkan ID Video!")
        print("Cara menjalankan: python .\\potong_video.py <ID_VIDEO>")
        sys.exit(1)
        
    target_video_id = sys.argv[1]
    url_video, daftar_momen = dapatkan_data_momen(target_video_id)
    
    if not daftar_momen:
        print(f"[Peringatan] Tidak ada data momen yang ditemukan.")
        sys.exit(1)
        
    print(f"\n[Mulai] Memproses Ukuran 9:16 + Font Jumbo (70) Maks 4 Baris + Logo Besar untuk Video ID: {target_video_id}")
    file_master = cari_file_video_asli(url_video, folder_input="videos_podcast")
    #print(f"[Info] Menggunakan file master: {file_master}\n")
    #print(f"[Info] Menggunakan file master: {file_master.encode('utf-8', 'ignore').decode('utf-8')}\n")
    print(f"[Info] Menggunakan file master: {file_master.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding)}\n")
    
    for idx, info_momen in enumerate(daftar_momen, start=1):
        m_id, m_waktu_start, m_waktu_selesai, m_judul = info_momen
        potong_dan_format_916(
            file_input=file_master,
            video_id=target_video_id,
            moment_id=m_id,
            waktu_start=m_waktu_start,
            waktu_selesai=m_waktu_selesai,
            judul_momen=m_judul,
            folder_output="clips_output",
            total_momen=len(daftar_momen),
            urutan=idx
        )
        
    print("\n[Selesai] Pemotongan batch dengan sistem cerdas 4 Baris selesai!")