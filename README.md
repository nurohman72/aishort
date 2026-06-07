# NurClipper - AI YouTube Shorts Automation Platform

![NurClipper Logo](logo.png)

**NurClipper** adalah aplikasi web-based yang mengotomatisasi proses pembuatan konten YouTube Shorts dari video podcast atau konten panjang. Menggunakan kecerdasan buatan (Gemini AI) untuk analisis konten, FFmpeg untuk pemotongan video, dan integrasi langsung dengan YouTube API untuk upload.

## 📊 Changelog Cepat

| Versi | Tanggal | Perubahan Utama |
|-------|---------|-----------------|
| **2.1.0** | June 2026 | Durasi max 59 detik, auto-refresh token, encoding fix, database schema update, start.bat, start_debug.bat |
| **2.0.0** | May 2026 | Web-based app, dark/light theme, real-time SSE, scheduler |

---

## 🎯 Fitur Utama

### 🤖 **AI-Powered Content Analysis**
- **Gemini 2.5 Flash** untuk analisis konten otomatis
- **Deteksi momen viral** dengan algoritma few-shot learning
- **Generasi judul menarik** dengan formula viral (pertanyaan mengejutkan, angka spesifik, konflik)
- **Hashtag berlapis** (mega-viral + topik spesifik + niche)
- **Deskripsi optimasi SEO** untuk engagement maksimal

### 🎬 **Video Processing Pipeline**
- **4-Tahap Otomatisasi**: Analisa → Download → Potong → Upload
- **Real-time progress tracking** dengan progress bar visual
- **Batch processing** untuk multiple video sekaligus
- **Auto-caption** dengan Whisper AI (opsional)
- **Format Shorts** (9:16) otomatis dengan FFmpeg
- **Durasi maksimal 59 detik** untuk YouTube Shorts

### 🌐 **Modern Web Interface**
- **SPA (Single Page Application)** dengan navigasi mulus
- **Dark/Light theme** dengan persistence localStorage
- **Real-time logs** dengan SSE (Server-Sent Events)
- **Glassmorphism design** dengan micro-animations
- **Responsive layout** untuk semua perangkat

### ⚡ **Advanced Features**
- **Scheduler** untuk upload terjadwal (once/daily/weekly)
- **Inline editing** judul & deskripsi momen
- **Video preview** langsung di browser
- **Toast notifications** untuk feedback sistem
- **Auto-refresh** momen setelah analisa selesai
- **Status recovery** setelah server restart
- **Auto-refresh YouTube token** tanpa login ulang
- **Quick Start Script** - `start.bat` untuk menjalankan aplikasi dengan mudah

## 🏗️ Arsitektur Sistem

### Backend Stack
- **FastAPI** - Web framework modern dengan async support
- **SQLite** - Database ringan dengan migrasi otomatis
- **Background Workers** - Thread-based processing queue
- **SSE** - Real-time log streaming
- **Schedule** - Task scheduler untuk upload terjadwal

### Frontend Stack
- **Vanilla JavaScript** - Tanpa framework dependency
- **CSS Variables** - Dynamic theming (dark/light)
- **Glassmorphism** - Modern UI design system
- **Font Awesome** - Icon library
- **Inter & JetBrains Mono** - Typography system

### AI & Processing Stack
- **Google Gemini API** - Content analysis & generation
- **yt-dlp** - YouTube video downloader
- **FFmpeg** - Video processing & editing
- **OpenAI Whisper** - Auto-caption generation
- **YouTube Data API v3** - Video upload & management

## 📊 Pipeline Kerja

```
1. INPUT URL → 2. ANALISA AI → 3. DOWNLOAD → 4. POTONG → 5. UPLOAD
```

### 1. **Input & Analisa**
- User memasukkan URL YouTube
- Gemini menganalisa konten, deteksi momen menarik
- Hasil: Judul viral, hashtag, deskripsi, kategori emosi

### 2. **Download & Processing**
- yt-dlp mendownload video master
- Progress tracking real-time (speed, ETA, size)
- Auto-caption dengan Whisper (opsional)

### 3. **Potong & Edit**
- FFmpeg memotong video berdasarkan momen terpilih
- Format conversion ke 9:16 (Shorts)
- Progress tracking per momen

### 4. **Upload & Scheduling**
- Upload otomatis ke YouTube channel
- Metadata optimization (judul, deskripsi, tags)
- Scheduler untuk upload terjadwal

## 🚀 Instalasi & Setup

### Prerequisites
- **Python 3.8+**
- **FFmpeg** (tersedia di PATH)
- **Google Gemini API Key**
- **YouTube OAuth Credentials**

### 1. Clone & Setup Environment
```bash
# Clone repository
git clone <repository-url>
cd aishort

# Buat virtual environment
python -m venv venv

# Aktifkan virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Update ke Versi Baru
Jika sudah pernah menginstal NurClipper sebelumnya dan ingin update ke versi terbaru:
```bash
# Stop server jika sedang berjalan (Ctrl+C di terminal)

# Update dependencies
pip install -r requirements.txt --upgrade

# Restart server
python web_server.py
```

**Catatan**: Server akan otomatis menjalankan database migration jika ada perubahan schema.
```

### 2. Konfigurasi API Keys
Edit file `environment.txt`:
```txt
GEMINI_API_KEY=your_gemini_api_key_here
```

### 3. Setup YouTube OAuth
1. Buka [Google Cloud Console](https://console.cloud.google.com/)
2. Buat project baru atau pilih existing project
3. Aktifkan **YouTube Data API v3**
4. Buat **OAuth 2.0 Client ID** (Desktop app)
5. Download `client_secrets.json` dan simpan di root folder

**Cara Kerja Auto-Refresh Token (V2.1.0+):**
- **Login pertama kali**: Buka aplikasi → Klik "Hubungkan YouTube" → Login dengan Google
- **Token disimpan**: Di file `token.pickle` secara otomatis
- **Auto-refresh**: Jika token expired, server otomatis refresh tanpa perlu buka browser
- **Login ulang hanya jika**: Token + refresh token habis (jarang terjadi)

### 4. Jalankan Aplikasi

**Opsi A: Menggunakan Start Script (Recommended)**
```bash
# Klik dua kali file start.bat
# Atau jalankan dari command line:
start.bat
```

**Opsi B: Manual dengan Virtual Environment**
```bash
# Aktifkan virtual environment
venv\Scripts\activate

# Jalankan web server
python web_server.py

# Buka browser dan akses:
# http://localhost:8000

# Untuk stop server, tekan Ctrl+C
```

**Opsi C: Debug Mode (Development)**
```bash
# Jalankan dengan auto-reload (for development)
start_debug.bat

# Ini akan otomatis restart server saat ada perubahan file
```

## 📁 Struktur Project

```
aishort/
├── start.bat                  # Quick start script ( Recommended )
├── start_debug.bat            # Debug start script (with auto-reload)
├── web_server.py              # FastAPI backend server
├── analisa_youtube.py         # Gemini AI analysis module
├── download_youtube.py        # yt-dlp downloader with progress
├── potong_video.py            # FFmpeg video cutter with progress
├── upload_youtube.py          # YouTube uploader with metadata
├── autocaption.py             # Whisper auto-caption module
├── requirements.txt           # Python dependencies
├── environment.txt            # API keys configuration
├── client_secrets.json        # YouTube OAuth credentials
├── token.pickle               # YouTube auth token cache
├── database_konten.db         # SQLite database
├── README.md                  # This documentation
│
├── web_static/                # Frontend assets
│   ├── index.html            # Main HTML SPA
│   ├── style.css           # CSS with dark/light themes
│   └── app.js              # JavaScript application logic
│
├── videos_podcast/          # Downloaded master videos
├── clips_output/           # Processed Shorts clips
└── yt_moments/            # Temporary processing files
```

## 🔧 Konfigurasi

### Environment Variables
File `environment.txt`:
```txt
GEMINI_API_KEY=GEMINI_API_KEY_ANDA
```

### Auto-Caption Settings (Opsional)
Di halaman Settings, konfigurasi:
- **Enable/Disable Auto-Caption**
- **Whisper Model** (tiny, base, small, medium, large)
- **Font Name** untuk subtitle (default: Cooper Black)
- **Font Size** untuk ASS format

### Database Schema
Tabel `moments` memiliki kolom berikut:
| Kolom | Tipe | Keterangan |
|-------|------|------------|
| `id` | INTEGER | Primary key |
| `video_id` | INTEGER | Foreign key ke tabel videos |
| `waktu_start` | TEXT | Waktu awal momen (HH:MM:SS) |
| `waktu_selesai` | TEXT | Waktu akhir momen (HH:MM:SS) |
| `judul_menarik` | TEXT | Judul viral yang dihasilkan Gemini |
| `hashtag_terbaik` | TEXT | Hashtag berlapis untuk SEO |
| `deskripsi_pendek` | TEXT | Deskripsi SEO dengan kategori emosi |
| `is_uploaded` | INTEGER | Status upload (0=belum, 1=sudah) |
| `is_selected` | INTEGER | Dipilih untuk dipotong (0=tidak, 1=ya) |

**Perubahan di versi 2.1.0**: Tambah kolom `waktu_selesai` untuk durasi potongan akurat.

### Theme Customization
- **Dark Theme** (default) - Glassmorphism dengan warna gelap
- **Light Theme** - Tema terang dengan kontras tinggi
- Pilihan disimpan di `localStorage` browser

## 🎮 Cara Penggunaan

### 1. Tambahkan Video
1. Buka aplikasi di `http://localhost:8000`
2. Navigasi ke Dashboard
3. Tempel URL YouTube di textarea
4. Klik "Masukkan ke Antrean"

### 2. Analisa Konten
1. Pilih video dari antrean
2. Klik tombol **🔍 Analisa** di pipeline
3. Tunggu Gemini menganalisa konten (1-2 menit)
4. Lihat hasil: momen menarik, judul viral, hashtag

### 3. Seleksi & Potong
1. Centang momen yang ingin dipotong
2. Klik tombol **✂️ Potong** di pipeline
3. Pantau progress bar real-time
4. Pratinjau klip langsung di browser

### 4. Upload ke YouTube
1. Pastikan sudah login YouTube (tombol "Hubungkan YouTube")
2. Klik tombol **📤 Upload** di pipeline
3. Video akan diupload dengan metadata optimal
4. Atau jadwalkan upload di halaman Schedule

**Catatan Video Duration (V2.1.0+):**
- Durasi video Shorts dibatasi maksimal **59 detik**
- Jika hasil analisa menghasilkan durasi > 59 detik, sistem otomatis memotong ke 59 detik
- Timestamp `waktu_selesai` dihitung otomatis dari `waktu_start` + 59 detik

### 5. Monitoring & Management
- **Dashboard**: Statistik real-time
- **Antrean**: Kelola semua video
- **Jadwal**: Upload terjadwal
- **Pengaturan**: Konfigurasi sistem

## 🔄 Workflow Otomatis

### All-in-One Mode
Klik tombol **⚡ All-in-One** untuk menjalankan semua tahap sekaligus:
1. Analisa AI → 2. Download → 3. Potong → 4. Upload

### Scheduled Automation
1. Buat jadwal di halaman Schedule
2. Pilih video dan tahap yang dijadwalkan
3. Set tanggal/waktu & pengulangan
4. Sistem akan eksekusi otomatis

## 🛠️ Troubleshooting

### Common Issues

#### 1. "ModuleNotFoundError: No module named 'fastapi'"
```bash
# Pastikan virtual environment aktif
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

#### 2. "FFmpeg not found"
- Download FFmpeg dari [ffmpeg.org](https://ffmpeg.org/)
- Tambahkan ke PATH system
- Atau simpan `ffmpeg.exe` di folder project

#### 3. "YouTube OAuth Error"
- Pastikan `client_secrets.json` ada di root folder
- Hapus `token.pickle` dan coba login ulang
- Verifikasi OAuth consent screen di Google Cloud Console

#### 4. "Gemini API Key Invalid"
- Update `GEMINI_API_KEY` di `environment.txt`
- Pastikan API key aktif di [Google AI Studio](https://makersuite.google.com/)

### Logs & Debugging
- **Real-time logs** di bagian bawah aplikasi
- **Filter logs** (semua, sukses, error, info)
- **Auto-scroll** untuk monitoring terus-menerus

## 📈 Performance & Optimization

### Database Optimization
- **SQLite dengan indexing** untuk query cepat
- **Automatic migration** untuk schema updates
- **Connection pooling** untuk concurrent access

### Video Processing
- **Parallel processing** untuk multiple moments
- **Progress tracking** real-time
- **Memory optimization** dengan streaming

### Frontend Performance
- **Lazy loading** untuk momen list
- **SSE** untuk real-time updates tanpa polling
- **LocalStorage caching** untuk tema & preferences

## 🔒 Security Considerations

### API Keys Protection
- **Environment variables** untuk sensitive data
- **Never commit** `environment.txt` ke version control
- **Gitignore** untuk credential files

### YouTube OAuth
- **Token caching** di `token.pickle`
- **Auto-refresh** untuk expired tokens
- **Scope minimal** (youtube.upload only)

### Data Privacy
- **Local processing** - video tidak diupload ke server eksternal
- **Temporary files** dihapus setelah processing
- **Database encryption** (opsional)

# 📝 Perubahan & Update Terbaru

## Version 2.1.0 (June 2026)

### 🎯 Fitur Baru

#### Durasi Video Maksimal 59 Detik
- **Fitur**: Semua potongan video otomatis dibatasi maksimal 59 detik
- **Implementasi**: 
  - `potong_video.py`: Hitung durasi dari `waktu_start` & `waktu_selesai`, batas maksimal 59 detik
  - `analisa_youtube.py`: Gemini prompt sudah menyebutkan durasi 30-59 detik
  - Log info saat durasi dibatasi

#### Auto-Refresh Token YouTube
- **Fitur**: Login YouTube hanya pertama kali, token otomatis di-refresh saat expired
- **Implementasi**:
  - Token disimpan di `token.pickle`
  - Jika token expired tapi ada `refresh_token`, otomatis refresh tanpa browser
  - User hanya perlu login manual jika tidak ada refresh token

#### Database Schema Update
- **Fitur**: Tambah kolom `waktu_selesai` ke tabel `moments`
- **Implementasi**:
  - `web_server.py`: Migration otomatis menambah kolom `waktu_selesai`
  - `analisa_youtube.py`: Simpan `waktu_selesai` = `waktu_start` + 59 detik
  - `potong_video.py`: Gunakan `waktu_selesai` untuk hitung durasi actual

#### Encoding Fix untuk Windows
- **Fitur**: Handle Unicode/Emoji characters di output console Windows
- **Implementasi**:
  - `upload_youtube.py`: `safe_print()` dengan UTF-8 encoding
  - `analisa_youtube.py`: UTF-8 encoding fix
  - `potong_video.py`: UTF-8 encoding fix
  - Semua `print()` diganti dengan `safe_print()`

### 🔧 Perbaikan Bug

#### Bug #1: Upload Gagal karena Unicode Error
- **Gejala**: `UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f631'`
- **Penyebab**: Windows menggunakan encoding cp1252 yang tidak support Unicode emoji
- **Solusi**: Tambah encoding fix dan `safe_print()` di semua modul YouTube

#### Bug #2: Durasi Potongan Tidak Sesuai
- **Gejala**: Potongan video selalu 59 detik meskipun Gemini memberikan waktu selesai berbeda
- **Penyebab**: Hardcoded durasi `-t 59` di FFmpeg command
- **Solusi**: Hitung durasi dari `waktu_start` & `waktu_selesai`, max 59 detik

### 📄 File yang Dimodifikasi

| File | Perubahan |
|------|-----------|
| `web_server.py` | Migration database: tambah kolom `waktu_selesai` |
| `analisa_youtube.py` | Tambah fungsi `hitung_waktu_selesai()`, simpan `waktu_selesai` ke DB |
| `potong_video.py` | Tambah encoding fix, gunakan `waktu_selesai`, durasi max 59 detik |

### 📄 File Baru

| File | Keterangan |
|------|-----------|
| `start.bat` | Script batch untuk menjalankan aplikasi dengan virtual environment |
| `start_debug.bat` | Script batch untuk development dengan auto-reload |
| `upload_youtube.py` | Tambah encoding fix, auto-refresh token, `safe_print()` |

### 📊 Cara Menggunakan Fitur Baru

#### Durasi Video Maksimal 59 Detik
1. Jalankan analisa → Gemini akan menghasilkan `waktu_start` & `waktu_selesai`
2. Jalankan potong → Durasi akan dibatasi maksimal 59 detik
3. Jika durasi > 59 detik, akan ada log: `[Info] Durasi (X detik) terlalu panjang, memotong ke 59 detik...`

#### Auto-Refresh Token YouTube
1. **Login pertama kali**: Klik "Hubungkan YouTube" → login dengan Google
2. **Upload selanjutnya**: Server otomatis refresh token jika expired
3. **Login tidak perlu** lagi kecuali token + refresh token habis

### ⚠️ Catatan Penting

1. **Durasi YouTube Shorts**: YouTube membatasi durasi Shorts maksimal 60 detik. Kita menggunakan 59 detik untuk memberikan buffer.
2. **Token YouTube**: Jika login ulang diperlukan, hapus `token.pickle` lalu login lagi.
3. **Database Migration**: Server otomatis menambah kolom `waktu_selesai` saat startup.
4. **Encoding Windows**: Jika ada error encoding, pastikan Python versi 3.7+ digunakan.

---

## 🚀 Deployment

### Local Development
```bash
python web_server.py
# Access: http://localhost:8000
```

### Production Deployment
1. **Use production server** (uvicorn dengan workers)
2. **Environment variables** untuk API keys
3. **Reverse proxy** (nginx/Apache)
4. **SSL certificate** untuk HTTPS
5. **Database backup** routine

### Docker (Coming Soon)
```dockerfile
# Dockerfile example
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "web_server.py"]
```

## 📚 API Documentation

### Endpoints Utama

#### Video Management
- `GET /api/videos` - List semua video
- `POST /api/videos` - Tambah video baru
- `DELETE /api/videos/{id}` - Hapus video

#### Processing Pipeline
- `POST /api/process/{video_id}/{stage}` - Trigger stage processing
- `GET /api/moments/{video_id}` - Get momen untuk video

#### Real-time Features
- `GET /api/logs/stream` - SSE log streaming
- `GET /api/config` - Get system configuration
- `POST /api/config` - Update configuration

#### YouTube Integration
- `POST /api/youtube-auth` - Initiate OAuth flow
- `GET /api/youtube-status` - Check auth status

## 🤝 Contributing

### Development Setup
1. Fork repository
2. Create feature branch
3. Install dev dependencies
4. Make changes with tests
5. Submit pull request

### Code Style
- **Black** untuk Python formatting
- **ESLint** untuk JavaScript (planned)
- **PEP 8** compliance untuk Python code

### Testing
- **Unit tests** untuk core modules
- **Integration tests** untuk API endpoints
- **E2E tests** untuk user workflows

## 📄 License

MIT License - lihat [LICENSE](LICENSE) file untuk detail.

## 🙏 Credits

- **Google Gemini AI** untuk content analysis
- **FastAPI** untuk web framework
- **FFmpeg** untuk video processing
- **yt-dlp** untuk YouTube downloading
- **OpenAI Whisper** untuk auto-caption
- **Font Awesome** untuk icon system

## 📞 Support & Contact

- **Issues**: [GitHub Issues](https://github.com/your-repo/issues)
- **Documentation**: [Wiki](https://github.com/your-repo/wiki)
- **Email**: support@example.com

---

**NurClipper** - Automate Your YouTube Shorts Creation 🚀

*Terakhir diperbarui: June 2026*
*Version: 2.1.0*