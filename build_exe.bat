@echo off
title Building NurClipper - Windows Executable
chcp 65001 >nul

REM ---- Aktifkan virtual environment ----
call "%~dp0venv\Scripts\activate.bat"

echo =============================================
echo      Membangun NurClipper Executable
echo =============================================
echo.

REM ---- Cek PyInstaller ----
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Menginstall PyInstaller...
    pip install pyinstaller
)

REM ---- Bersihkan build sebelumnya ----
echo [CLEAN] Membersihkan folder build & dist...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM ---- Base PyInstaller flags ----
set PFLAGS=--noconfirm --clean

REM ---- 1. Bangun analisa_youtube.exe ----
echo.
echo [1/5] Membangun analisa_youtube.exe ...
pyinstaller %PFLAGS% --onefile --name analisa_youtube ^
    --distpath dist\tools ^
    --hidden-import google.genai ^
    --hidden-import google.genai.types ^
    --hidden-import youtube_transcript_api ^
    analisa_youtube.py
if %errorlevel% neq 0 (
    echo [ERROR] Gagal membangun analisa_youtube.exe
    pause
    exit /b 1
)
echo [OK] analisa_youtube.exe selesai.

REM ---- 2. Bangun download_youtube.exe ----
echo.
echo [2/5] Membangun download_youtube.exe ...
pyinstaller %PFLAGS% --onefile --name download_youtube ^
    --distpath dist\tools ^
    --hidden-import yt_dlp ^
    --hidden-import yt_dlp.utils ^
    download_youtube.py
if %errorlevel% neq 0 (
    echo [ERROR] Gagal membangun download_youtube.exe
    pause
    exit /b 1
)
echo [OK] download_youtube.exe selesai.

REM ---- 3. Bangun potong_video.exe ----
echo.
echo [3/5] Membangun potong_video.exe ...
pyinstaller %PFLAGS% --onefile --name potong_video ^
    --distpath dist\tools ^
    --collect-data whisper ^
    --hidden-import autocaption ^
    --hidden-import torch ^
    --hidden-import torch.nn ^
    --exclude-module torch.cuda ^
    --exclude-module torchvision ^
    --exclude-module IPython ^
    --exclude-module matplotlib ^
    potong_video.py
if %errorlevel% neq 0 (
    echo [ERROR] Gagal membangun potong_video.exe
    pause
    exit /b 1
)
echo [OK] potong_video.exe selesai.

REM ---- 4. Bangun upload_youtube.exe ----
echo.
echo [4/5] Membangun upload_youtube.exe ...
pyinstaller %PFLAGS% --onefile --name upload_youtube ^
    --distpath dist\tools ^
    --hidden-import googleapiclient ^
    --hidden-import googleapiclient.discovery ^
    --hidden-import googleapiclient.http ^
    --hidden-import google.auth ^
    --hidden-import google_auth_oauthlib ^
    --hidden-import google.oauth2 ^
    upload_youtube.py
if %errorlevel% neq 0 (
    echo [ERROR] Gagal membangun upload_youtube.exe
    pause
    exit /b 1
)
echo [OK] upload_youtube.exe selesai.

REM ---- 5. Bangun NurClipper.exe (main server) ----
echo.
echo [5/5] Membangun NurClipper.exe ...
pyinstaller %PFLAGS% --onedir --name NurClipper ^
    --distpath dist ^
    --add-data "web_static;web_static" ^
    --hidden-import uvicorn ^
    --hidden-import uvicorn.logging ^
    --hidden-import uvicorn.loops.auto ^
    --hidden-import uvicorn.protocols.http.auto ^
    --hidden-import sse_starlette ^
    --hidden-import sqlite3 ^
    --hidden-import schedule ^
    web_server.py
if %errorlevel% neq 0 (
    echo [ERROR] Gagal membangun NurClipper.exe
    pause
    exit /b 1
)
echo [OK] NurClipper.exe selesai.

REM ---- 6. Salin tools ke folder output utama ----
echo.
echo [COPY] Menyalin tools ke direktori output...
copy dist\tools\*.exe dist\NurClipper\ >nul
echo [OK] Tools disalin.

REM ---- 7. Buat environment.txt template ----
echo.
echo [TEMPLATE] Membuat environment.txt template...
echo GEMINI_API_KEY= > dist\NurClipper\environment.txt
echo.
echo =============================================
echo         BUILD SELESAI!
echo =============================================
echo.
echo Output: dist\NurClipper\
echo.
echo File penting di folder output:
echo   - NurClipper.exe          (jalankan ini)
echo   - analisa_youtube.exe
echo   - download_youtube.exe
echo   - potong_video.exe
echo   - upload_youtube.exe
echo   - web_static\             (frontend)
echo   - environment.txt         (isi GEMINI_API_KEY)
echo.
echo Catatan:
echo - client_secrets.json      (YouTube OAuth - letakkan di folder yg sama)
echo - ffmpeg.exe               (harus ada di PATH atau di folder yang sama)
echo - video dan klip disimpan di videos_podcast\ dan clips_output\
echo.
pause
