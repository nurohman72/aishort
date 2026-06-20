import os
import re
import sys
import pickle
import sqlite3
import traceback
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def get_base_dir():
    """Mengembalikan direktori aplikasi (tempat exe/config/data berada)"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

os.chdir(get_base_dir())

# Fix encoding untuk Windows (cp1252 tidak support Unicode emoji)
if sys.platform == "win32":
    try:
        # Coba set encoding UTF-8 untuk stdout di Windows
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        # Fallback untuk Python versi lama
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Fungsi print aman untuk Unicode
def safe_print(text):
    """Print text dengan handling encoding yang aman untuk Windows"""
    try:
        # Coba print dengan encoding default
        print(text)
    except UnicodeEncodeError:
        # Jika ada error encoding, encode dengan UTF-8 dan decode dengan replace
        try:
            # Untuk Python 3.7+ dengan reconfigure
            encoded_text = text.encode('utf-8', errors='replace').decode('utf-8')
            print(encoded_text)
        except:
            # Fallback ultimate: strip non-ASCII characters
            ascii_text = ''.join(char for char in text if ord(char) < 128)
            print(ascii_text)

# Tentukan hak akses (Scope) - Hanya untuk mengupload video
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

def dapatkan_layanan_youtube():
    """Mengautentikasi pengguna dan mengembalikan objek layanan YouTube API
    Dapat menggunakan token lama dari token.pickle atau login baru dengan browser.
    """
    credentials = None
    
    # Coba load token dari file pickle
    if os.path.exists('token.pickle'):
        try:
            with open('token.pickle', 'rb') as token:
                credentials = pickle.load(token)
            
            # Jika token ada dan valid, gunakan saja
            if credentials and credentials.valid:
                safe_print("[YouTube] Token ditemukan dan masih valid, menggunakan token lama.")
                return build('youtube', 'v3', credentials=credentials)
            
            # Jika token expired tapi ada refresh_token, refresh otomatis
            if credentials and credentials.expired and credentials.refresh_token:
                safe_print("[YouTube] Token expired, mencoba refresh token...")
                try:
                    import google.auth.transport.requests as req
                    credentials.refresh(req.Request())
                    # Simpan token baru
                    with open('token.pickle', 'wb') as token:
                        pickle.dump(credentials, token)
                    safe_print("[YouTube] Token berhasil di-refresh!")
                    return build('youtube', 'v3', credentials=credentials)
                except Exception as e:
                    safe_print(f"[YouTube] Refresh token gagal: {e}")
        except Exception as e:
            safe_print(f"[YouTube] Error load token: {e}")
    
    # Jika tidak ada token valid, minta login baru
    if not os.path.exists('client_secrets.json'):
        safe_print("[Error] File 'client_secrets.json' tidak ditemukan!")
        safe_print("        Silakan download dari Google Cloud Console Anda terlebih dahulu.")
        safe_print("")
        safe_print("        Langkah-langkah:")
        safe_print("        1. Buka https://console.cloud.google.com/")
        safe_print("        2. Buat project baru")
        safe_print("        3. Aktifkan YouTube Data API v3")
        safe_print("        4. Buat OAuth 2.0 Client ID (Desktop app)")
        safe_print("        5. Download file JSON dan simpan sebagai 'client_secrets.json'")
        sys.exit(1)
    
    safe_print("[YouTube] Memulai autentikasi OAuth...")
    safe_print("        Buka browser dan akses: http://localhost:8080")
    safe_print("        Login dengan Google account yang terhubung ke YouTube")
    safe_print("")
    
    flow = InstalledAppFlow.from_client_secrets_file('client_secrets.json', SCOPES)
    # Coba port mulai dari 8080, hindari 8000 (bentrok dengan FastAPI server)
    oauth_ports = [8080, 8081, 8082, 8083, 8084]
    credentials = None
    for port in oauth_ports:
        try:
            credentials = flow.run_local_server(port=port, open_browser=True)
            break
        except Exception:
            continue
    if credentials is None:
        safe_print("[Error] Tidak dapat menemukan port yang tersedia untuk OAuth (coba 8080-8084).")
        sys.exit(1)
    
    # Simpan kredensial secara atomik (tulis ke temp dulu, lalu rename) untuk hindari korupsi file
    temp_token = 'token.pickle.tmp'
    with open(temp_token, 'wb') as token:
        pickle.dump(credentials, token)
    os.replace(temp_token, 'token.pickle')  # Atomic on Windows (Python 3.3+)
    
    safe_print("[YouTube] Autentikasi berhasil! Token disimpan di 'token.pickle'.")
    return build('youtube', 'v3', credentials=credentials)

def ambil_data_momen_dari_db(video_id):
    """Mengambil metadata moment dari database berdasarkan ID Video untuk keperluan judul/deskripsi"""
    conn = sqlite3.connect("database_konten.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, judul_menarik, hashtag_terbaik, deskripsi_pendek
        FROM moments WHERE video_id = ? AND is_selected = 1
    """, (video_id,))
    rows = cursor.fetchall()
    conn.close()
    
    # Kembalikan dict {moment_id: {judul, hashtag, deskripsi}}
    return {
        str(row[0]): {
            "judul": row[1],
            "hashtag": row[2] or "#shorts #fyp #viral",
            "deskripsi": row[3] or ""
        }
        for row in rows
    }

def tandai_momen_terupload_di_db(moment_id):
    """Memperbarui status upload momen di SQLite"""
    try:
        conn = sqlite3.connect("database_konten.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE moments SET is_uploaded = 1 WHERE id = ?", (moment_id,))
        conn.commit()
        conn.close()
        safe_print("   [Database] Status upload diperbarui di database SQLite.")
    except Exception as ex:
        safe_print(f"   [Peringatan] Gagal menandai status terupload: {ex}")

def upload_ke_youtube(youtube, path_video, judul, deskripsi, tags_list=None):
    """Proses upload file video ke YouTube via API"""
    if tags_list is None:
        tags_list = ['shorts', 'viral', 'trending']
    body = {
        'snippet': {
            'title': judul[:100],
            'description': deskripsi,
            'tags': tags_list[:30],  # YouTube max 30 tags
            'categoryId': '22'
        },
        'status': {
            'privacyStatus': 'private',
            'selfDeclaredMadeForKids': False
        }
    }
    
    # Menyiapkan media upload
    media = MediaFileUpload(path_video, chunksize=-1, resumable=True, mimetype='video/mp4')
    
    request = youtube.videos().insert(
        part='snippet,status',
        body=body,
        media_body=media
    )
    
    safe_print(f"   [Proses] Mengunggah {os.path.basename(path_video)}...")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            safe_print(f"            Terkirim: {int(status.progress() * 100)}%")
            
    safe_print(f"   [Sukses] Video berhasil diupload! Video ID: {response['id']}")

# --- Alur Utama Program ---
if __name__ == "__main__":
    if len(sys.argv) < 2:
        safe_print("\n[Error] Anda belum memasukkan ID Video yang ingin diupload!")
        safe_print("Cara menjalankan: python .\\upload_youtube.py <ID_VIDEO>")
        sys.exit(1)
        
    target_video_id = sys.argv[1]
    folder_clips = "clips_output"
    
    if not os.path.exists(folder_clips):
        safe_print(f"[Error] Folder '{folder_clips}' tidak ditemukan! Silakan potong video dulu.")
        sys.exit(1)
        
    # 1. Ambil data teks dari database
    safe_print("[1/3] Membaca data momen dari database...")
    dict_momen = ambil_data_momen_dari_db(target_video_id)
    
    if not dict_momen:
        safe_print(f"[Error] Tidak ada data momen di database untuk Video ID {target_video_id}!")
        sys.exit(1)
        
    # 2. Inisialisasi API YouTube
    safe_print("[2/3] Menginisialisasi koneksi YouTube API...")
    layanan_youtube = dapatkan_layanan_youtube()
    
    # 3. Scan folder dan upload video yang sesuai dengan format ID_VIDEO_MOMENTID.mp4
    safe_print("[3/3] Memulai pemindaian file video di folder output...\n")
    
    counter_upload = 0
    files = [f for f in os.listdir(folder_clips) if f.endswith('.mp4')]
    
    for file_name in files:
        # Cek apakah file diawali dengan "IDVideo_" (Contoh: "12_1.mp4")
        if file_name.startswith(f"{target_video_id}_"):
            parts = file_name.replace(".mp4", "").split("_")
            if len(parts) >= 2:
                moment_id = parts[1]
                
                # Pastikan moment_id tersebut terdaftar di database
                if moment_id in dict_momen:
                    path_lengkap_video = os.path.join(folder_clips, file_name)
                    data_momen = dict_momen[moment_id]
                    judul_asli  = data_momen["judul"]
                    hashtag_str = data_momen["hashtag"]
                    deskripsi   = data_momen["deskripsi"]

                    # Bersihkan prefix kategori emosi dari deskripsi jika ada
                    deskripsi_bersih = re.sub(r'^\[.*?\]\s*', '', deskripsi).strip()

                    # Ekstrak hashtag dari string untuk tags API
                    tags_list = [h.lstrip('#') for h in hashtag_str.split() if h.startswith('#')]
                    tags_list = list(dict.fromkeys(tags_list))  # deduplicate

                    # Format judul: judul asli + #shorts (maks 100 karakter)
                    judul_shorts = f"{judul_asli} #shorts"
                    if len(judul_shorts) > 100:
                        judul_shorts = judul_asli[:96] + "..."

                    # Format deskripsi lengkap untuk YouTube
                    deskripsi_shorts = (
                        f"{deskripsi_bersih}\n\n"
                        f"{hashtag_str}"
                    ).strip()[:5000]

                    safe_print(f"-> Mengupload Momen ID {moment_id}: \"{judul_asli}\"")
                    try:
                        upload_ke_youtube(layanan_youtube, path_lengkap_video, judul_shorts, deskripsi_shorts, tags_list)
                        tandai_momen_terupload_di_db(moment_id)
                        counter_upload += 1
                    except Exception as e:
                        safe_print(f"   [Gagal] Terjadi error saat upload video ini: {repr(e)}")
                        safe_print(f"   [Debug] Tipe error: {type(e).__name__}")
                        safe_print(f"   [Debug] Pesan: {str(e)}")
                        safe_print(f"   [Debug] Traceback:\n{traceback.format_exc()}")
                        # Google API errors (ResumableUploadError, HttpError) simpan detail di .resp dan .content
                        if hasattr(e, 'resp'):
                            safe_print(f"   [Debug] HTTP Status: {e.resp.status}")
                            content_str = e.content if isinstance(e.content, str) else e.content.decode('utf-8', errors='replace')
                            safe_print(f"   [Debug] Response: {content_str[:500]}")
                            error_str = content_str[:2000]
                        else:
                            error_str = str(e)
                        if "quotaExceeded" in error_str or "uploadLimitExceeded" in error_str or "403" in error_str or (hasattr(e, 'resp') and e.resp.status in (400, 403)):
                            if "uploadLimitExceeded" in error_str:
                                safe_print("\n   [PENTING] Akun YouTube ini telah mencapai batas maksimal upload harian!")
                                safe_print("   YouTube membatasi jumlah upload per hari untuk mencegah spam.")
                                safe_print("   Solusi: Tunggu 24 jam atau gunakan akun YouTube lain.\n")
                            else:
                                safe_print("\n   [PENTING] Kemungkinan besar Kuota Harian YouTube API gratis Anda telah habis!")
                                safe_print("   Detail: Secara default, Google Cloud memberikan kuota harian 10.000 unit per hari.")
                                safe_print("   Setiap 1x upload video memerlukan biaya kuota sebesar 1.600 unit, sehingga batas maksimalnya")
                                safe_print("   adalah sekitar 6 video saja per hari untuk satu API Key/Project.")
                                safe_print("   Solusi: Anda dapat mengajukan permohonan penambahan kuota di Google Cloud Console,")
                                safe_print("   atau menggunakan API Key/client_secrets.json dari akun developer Google yang lain,")
                                safe_print("   atau melanjutkan proses upload sisa videonya besok.\n")
                        
    if counter_upload == 0:
        safe_print(f"[Gagal] Tidak ada file kecocokan video ditemukan untuk ID {target_video_id} di folder '{folder_clips}'.")
        sys.exit(1)
    else:
        safe_print(f"\n[Selesai] Total {counter_upload} video Shorts berhasil diunggah ke YouTube!")