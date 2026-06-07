import os
import sys
import json
import sqlite3
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from yt_dlp import YoutubeDL  # <-- Tambahkan ini untuk ambil transkrip

# 1. Muat file environment.txt
load_dotenv(dotenv_path="environment.txt")
gemini_key = os.getenv("GEMINI_API_KEY")

if not gemini_key:
    raise ValueError("Error: GEMINI_API_KEY tidak ditemukan di dalam file environment.txt!")

# 2. Ambil URL Video dari parameter terminal
if len(sys.argv) < 2:
    print("\n[Error] Anda belum memasukkan link YouTube!")
    print("Cara menjalankan: python .\\analisa_youtube.py <LINK_YOUTUBE>")
    sys.exit(1)

url_video = sys.argv[1]

# 3. Definisikan struktur JSON menggunakan Pydantic
class MomentTerbaik(BaseModel):
    waktu_start: str = Field(
        description="Waktu TEPAT awal momen dalam format hh:mm:ss (contoh: '00:08:04'). "
                    "Harus sesuai dengan awal kalimat di transkrip, bukan di tengah kalimat."
    )
    judul_menarik: str = Field(
        description="Judul video Shorts yang WAJIB menggunakan salah satu formula viral berikut: "
                    "(1) Pertanyaan mengejutkan: 'Kenapa [X] bisa [Y]?', "
                    "(2) Angka spesifik: '[N] Hal yang [X] Tidak Pernah Bilang', "
                    "(3) Konflik/Kontroversi: '[X] vs [Y]: Siapa yang Benar?', "
                    "(4) Rahasia/Bocoran: 'Akhirnya Terbongkar! [X]...', "
                    "(5) Emosi kuat: 'NGAKAK! / KAGET! / HARU! Saat [X]...'. "
                    "Maksimal 50 karakter. WAJIB dalam Bahasa Indonesia. "
                    "DILARANG judul generik seperti 'Momen Menarik' atau 'Highlight Video'."
    )
    hook_kalimat: str = Field(
        description="Kalimat pembuka (hook) 1-2 kalimat yang akan muncul di caption/deskripsi YouTube Shorts. "
                    "Harus langsung memancing rasa penasaran atau emosi penonton dalam 3 detik pertama. "
                    "Contoh: 'Dia bilang hal yang TIDAK PERNAH diucapkan siapapun sebelumnya...' "
                    "atau 'Momen ini bikin semua orang di studio terdiam seketika '. "
                    "WAJIB dalam Bahasa Indonesia."
    )
    hashtag_terbaik: str = Field(
        description="5-8 hashtag yang WAJIB mencakup: "
                    "(1) 1-2 hashtag MEGA viral umum: #shorts #fyp #viral #trending, "
                    "(2) 2-3 hashtag TOPIK SPESIFIK sesuai isi momen (bukan nama channel), "
                    "(3) 1-2 hashtag NICHE/KOMUNITAS yang relevan. "
                    "Format: '#hashtag1 #hashtag2 #hashtag3'. "
                    "DILARANG menggunakan nama channel sebagai hashtag utama."
    )
    deskripsi_pendek: str = Field(
        description="Deskripsi YouTube Shorts 2-3 kalimat yang: "
                    "(1) Dimulai dengan hook_kalimat yang sudah dibuat, "
                    "(2) Jelaskan KONTEKS momen secara singkat dan menarik, "
                    "(3) Akhiri dengan call-to-action: 'Follow untuk konten seru lainnya!' atau 'Tonton sampai habis!'. "
                    "Total maksimal 150 karakter. WAJIB dalam Bahasa Indonesia."
    )
    kategori_emosi: str = Field(
        description="Satu kata kategori emosi dominan momen ini untuk algoritma: "
                    "LUCU / MENGEJUTKAN / INSPIRATIF / KONTROVERSIAL / HARU / INFORMATIF / TEGANG"
    )

class HasilAnalisisVideo(BaseModel):
    daftar_moment: list[MomentTerbaik] = Field(
        description="8 hingga 15 momen TERBAIK dari video, dipilih berdasarkan potensi viral tertinggi. "
                    "Prioritaskan momen dengan emosi kuat, konflik, kejutan, atau insight berharga. "
                    "JANGAN pilih momen yang membosankan, terlalu panjang konteksnya, atau tidak berdiri sendiri."
    )


# 4. FUNGSI BARU: Mengambil teks transkrip/subtitle otomatis dari YouTube
def ambil_transkrip_youtube(video_url):
    import re
    import requests
    from youtube_transcript_api import YouTubeTranscriptApi
    
    print("[Info] Mencoba mengambil informasi video...")
    
    # Ambil data dasar via oEmbed
    title = "Judul Tidak Diketahui"
    author = "Author Tidak Diketahui"
    try:
        oembed_url = f"https://www.youtube.com/oembed?url={video_url}&format=json"
        response = requests.get(oembed_url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            title = data.get("title", "Judul Tidak Diketahui")
            author = data.get("author_name", "Author Tidak Diketahui")
            print(f"[Info] Informasi oEmbed ditemukan: '{title}' oleh {author}")
    except Exception as e:
        print(f"[Peringatan] Gagal mengambil oEmbed: {e}")

    # Ekstrak YouTube Video ID menggunakan regex yang robust
    yt_id_match = re.search(r'(?:v=|\/shorts\/|\/embed\/|\/v\/|youtu\.be\/|\/videos\/)([a-zA-Z0-9_-]{11})', video_url)
    video_id = yt_id_match.group(1) if yt_id_match else None
    
    transcript_str = ""
    if video_id:
        print(f"[Info] Mencoba mengambil transkrip asli untuk ID Video: {video_id}...")
        try:
            # Mencoba menarik transkrip dalam Bahasa Indonesia ('id') atau fallback Bahasa Inggris ('en')
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['id', 'en'])
            
            # Format transkrip menjadi teks terstruktur dengan timestamp
            lines = []
            for entry in transcript_list:
                start_seconds = int(entry['start'])
                h = start_seconds // 3600
                m = (start_seconds % 3600) // 60
                s = start_seconds % 60
                time_str = f"{h:02d}:{m:02d}:{s:02d}"
                lines.append(f"[{time_str}] {entry['text']}")
            
            transcript_str = "\n".join(lines)
            print(f"[Sukses] Transkrip asli berhasil ditarik! Total baris: {len(lines)}")
        except Exception as e:
            print(f"[Peringatan] Gagal menarik transkrip asli (mungkin tidak ada/dinonaktifkan): {e}")
            print("[Fallback] Menggunakan data oEmbed untuk analisis.")
            
    # Kembalikan teks terstruktur lengkap
    konteks_analisis = f"Judul Video: {title}\nChannel: {author}\n"
    if transcript_str:
        konteks_analisis += f"\n--- TRANSKRIP VIDEO PERCAKAPAN DENGAN TIMESTAMP ---\n{transcript_str}"
    else:
        konteks_analisis += "\n(Peringatan: Transkrip percakapan video tidak tersedia untuk video ini. Silakan analisis momen berdasarkan tebakan logis dari Judul.)"
        
    return konteks_analisis


# 5. Fungsi Hapus Data Lama
def hapus_data_lama_jika_ada(video_url):
    conn = sqlite3.connect("database_konten.db")
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS videos (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE, tanggal_analisis TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS moments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            video_id INTEGER, 
            waktu_start TEXT, 
            judul_menarik TEXT, 
            hashtag_terbaik TEXT, 
            deskripsi_pendek TEXT, 
            is_uploaded INTEGER DEFAULT 0, 
            is_selected INTEGER DEFAULT 1,
            FOREIGN KEY (video_id) REFERENCES videos (id) ON DELETE CASCADE
        )
    ''')
    
    cursor.execute("SELECT id FROM videos WHERE url = ?", (video_url,))
    row = cursor.fetchone()
    if row:
        video_id = row[0]
        print(f"\n[Info] Menemukan data video terdaftar (ID: {video_id}). Membersihkan momen lama...")
        cursor.execute("DELETE FROM moments WHERE video_id = ?", (video_id,))
        conn.commit()
    conn.close()


# 6. Fungsi Simpan ke SQLite
def simpan_ke_sqlite(video_url, json_data_string):
    conn = sqlite3.connect("database_konten.db")
    cursor = conn.cursor()
    try:
        # Cek apakah video sudah ada
        cursor.execute("SELECT id FROM videos WHERE url = ?", (video_url,))
        row = cursor.fetchone()
        if row:
            video_id = row[0]
            # Update tanggal analisis
            cursor.execute("UPDATE videos SET tanggal_analisis = CURRENT_TIMESTAMP WHERE id = ?", (video_id,))
        else:
            cursor.execute("INSERT INTO videos (url) VALUES (?)", (video_url,))
            video_id = cursor.lastrowid
            
        data_dict = json.loads(json_data_string)
        
        for i, moment in enumerate(data_dict.get("daftar_moment", [])):
            # Gabungkan hook + deskripsi menjadi deskripsi lengkap yang siap pakai
            hook = moment.get("hook_kalimat", "")
            desc = moment.get("deskripsi_pendek", "")
            kategori = moment.get("kategori_emosi", "")
            
            # Format deskripsi final: hook sebagai pembuka, lalu deskripsi, lalu kategori
            deskripsi_final = desc if desc else hook
            if kategori:
                deskripsi_final = f"[{kategori}] {deskripsi_final}"
            
            waktu_start = moment.get("waktu_start", "00:00:00")
            
            # Hitung waktu_selesai: waktu_start + 59 detik (durasi Shorts standar)
            waktu_selesai = hitung_waktu_selesai(waktu_start, durasi_detik=59)
            
            cursor.execute('''
                INSERT INTO moments (video_id, waktu_start, waktu_selesai, judul_menarik, hashtag_terbaik, deskripsi_pendek, is_selected)
                VALUES (?, ?, ?, ?, ?, ?, 1)
            ''', (
                video_id,
                waktu_start,
                waktu_selesai,
                moment.get("judul_menarik"),
                moment.get("hashtag_terbaik"),
                deskripsi_final
            ))
        conn.commit()
        print(f"[Sukses] Data analisis asli berhasil disimpan ke SQLite!")
    except Exception as e:
        conn.rollback()
        print(f"[Gagal] Gagal menyimpan ke SQLite: {e}")
    finally:
        conn.close()


# Fungsi Bantu: Hitung waktu_selesai dari waktu_start + durasi
def hitung_waktu_selesai(waktu_start, durasi_detik=59):
    """Menghitung waktu_selesai dari waktu_start + durasi detik"""
    try:
        from datetime import datetime, timedelta
        
        # Parse waktu_start format HH:MM:SS
        parts = waktu_start.split(':')
        if len(parts) == 3:
            hours, minutes, seconds = int(parts[0]), int(parts[1]), float(parts[2])
            
            # Buat datetime dummy (tanggal arbitrary)
            dummy_start = datetime(2000, 1, 1, hours, minutes, int(seconds))
            
            # Tambah durasi
            dummy_end = dummy_start + timedelta(seconds=durasi_detik)
            
            # Format kembali ke HH:MM:SS
            waktu_selesai = dummy_end.strftime("%H:%M:%S")
            return waktu_selesai
        else:
            return "00:00:59"  # Fallback
    except Exception:
        return "00:00:59"  # Fallback jika ada error

# ================= Alur Utama =================

# Langkah 1: Bersihkan database
hapus_data_lama_jika_ada(url_video)

# Langkah 2: Ambil informasi kontekstual asli dari YouTube
info_video = ambil_transkrip_youtube(url_video)

# Langkah 3: Kontak Gemini AI dengan menyertakan detail video asli
client = genai.Client(api_key=gemini_key)

prompt_text = f"""
Anda adalah VIRAL CONTENT STRATEGIST kelas dunia yang telah membantu ratusan channel YouTube Indonesia mencapai jutaan views melalui klip Shorts. Anda memahami psikologi penonton Indonesia, algoritma YouTube Shorts, dan formula konten yang terbukti viral.

=== DATA VIDEO YANG AKAN DIANALISIS ===
{info_video}
Link: {url_video}

=== MISI ANDA ===
Analisis transkrip di atas dan temukan 8-15 momen PALING BERPOTENSI VIRAL untuk dijadikan YouTube Shorts berdurasi 30-59 detik.

=== KRITERIA SELEKSI MOMEN (WAJIB DIPENUHI) ===
Pilih HANYA momen yang memenuhi minimal 2 kriteria berikut:
✅ KEJUTAN — Pernyataan/fakta yang tidak terduga atau mengejutkan
✅ KONFLIK — Perdebatan, bantahan, atau ketegangan antar pihak
✅ EMOSI KUAT — Tawa keras, tangis, marah, atau ekspresi ekstrem
✅ INSIGHT BERHARGA — Informasi/tips yang langsung bisa dipakai penonton
✅ MOMEN KLIMAKS — Puncak cerita atau pengungkapan penting
✅ RELATABLE — Situasi yang sangat familiar bagi penonton Indonesia

HINDARI momen yang:
❌ Hanya basa-basi atau perkenalan
❌ Membutuhkan konteks panjang untuk dipahami
❌ Terlalu teknis tanpa nilai hiburan
❌ Terpotong di tengah kalimat penting

=== FORMULA JUDUL VIRAL (PILIH YANG PALING COCOK) ===
Gunakan salah satu formula ini untuk setiap judul:
• [EMOSI]! Saat [Siapa] [Melakukan Apa] → "NGAKAK! Saat Arief Didu Ketahuan Bohong"
• Kenapa [X] Bisa [Y]? → "Kenapa Dia Tiba-Tiba Nangis di Depan Kamera?"
• [Angka] Detik yang Bikin [Emosi] → "30 Detik yang Bikin Studio Hening Total"
• Akhirnya [X] Ngaku... → "Akhirnya Dia Ngaku Soal Rahasia Ini!"
• [X] vs [Y]: Siapa yang Benar? → "Arief vs Host: Siapa yang Benar?"
• POV: [Situasi Relatable] → "POV: Ketahuan Bohong di Depan Semua Orang"

=== ATURAN HASHTAG ===
Setiap momen WAJIB punya kombinasi:
1. Hashtag mega-viral: #shorts #fyp #viral (selalu ada)
2. Hashtag topik spesifik dari ISI momen (bukan nama channel)
3. Hashtag komunitas/niche yang relevan

=== CONTOH OUTPUT BERKUALITAS TINGGI ===
Judul BURUK: "Momen Lucu di Acara TV" ← terlalu generik
Judul BAIK: "NGAKAK! Arief Didu Panik Diinterogasi Soal Ini"

Hashtag BURUK: "#laporpak #ariefdidu #tv" ← terlalu sempit
Hashtag BAIK: "#shorts #fyp #viral #ngakak #interogasi #reaksilucu #komedi"

Deskripsi BURUK: "Momen seru dari acara Lapor Pak"
Deskripsi BAIK: "Ekspresi panik Arief Didu ini bikin semua orang ngakak Dia sama sekali nggak nyangka bakal diinterogasi soal ini! Tonton sampai habis, dijamin ngakak!"

=== INSTRUKSI TEKNIS ===
- Semua teks WAJIB dalam Bahasa Indonesia yang natural dan gaul (bukan formal)
- Waktu start HARUS tepat di awal kalimat berdasarkan timestamp transkrip
- Jangan gunakan emoji di judul dan deskripsi
- Pastikan setiap momen bisa berdiri sendiri tanpa konteks tambahan
"""

print(f"\nMengirimkan data asli ke Gemini AI... Mohon tunggu...")

try:
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt_text,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=HasilAnalisisVideo,
            temperature=0.75,  # Lebih kreatif untuk judul viral
            thinking_config=types.ThinkingConfig(thinking_budget=8000),  # Beri ruang berpikir lebih dalam
        ),
    )

    print("Hasil Analisis kontekstual dari Gemini berhasil didapatkan.")
    simpan_ke_sqlite(url_video, response.text)

except Exception as e:
    print(f"\nTerjadi kesalahan saat memproses API: {e}")
