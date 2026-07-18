import os
import sys
import json
import time
import sqlite3
import requests

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def safe_print(text):
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        try:
            import sys as _sys
            encoded_bytes = text.encode(_sys.stdout.encoding or 'utf-8', errors='replace')
            print(encoded_bytes.decode(_sys.stdout.encoding or 'utf-8', errors='replace'), flush=True)
        except Exception:
            print(text.encode('utf-8', errors='replace').decode('utf-8', errors='replace'), flush=True)

CONFIG_FILE = "config.json"
DB_FILE = "database_konten.db"
FB_API_VERSION = "v21.0"
FB_BASE_URL = f"https://graph.facebook.com/{FB_API_VERSION}"

def load_facebook_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
            return cfg.get("facebook", {})
        except Exception:
            pass
    return {}

def get_moments_from_db(video_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, judul_menarik, hashtag_terbaik, deskripsi_pendek
        FROM moments WHERE video_id = ? AND is_uploaded_fb = 0 AND is_selected = 1
    """, (video_id,))
    rows = cursor.fetchall()
    
    cursor.execute("SELECT channel_video FROM videos WHERE id = ?", (video_id,))
    channel_row = cursor.fetchone()
    conn.close()
    
    channel_name = channel_row[0] if channel_row and channel_row[0] else ""
    
    return {
        str(row[0]): {
            "judul": row[1],
            "hashtag": row[2] or "#shorts #fyp #viral",
            "deskripsi": row[3] or ""
        }
        for row in rows
    }, channel_name

def mark_uploaded_fb(moment_id):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE moments SET is_uploaded_fb = 1 WHERE id = ?", (moment_id,))
        conn.commit()
        conn.close()
    except Exception as ex:
        safe_print(f"   [Peringatan] Gagal menandai status FB upload: {ex}")

def verify_token(page_id, access_token):
    url = f"{FB_BASE_URL}/{page_id}"
    params = {"access_token": access_token, "fields": "id,name"}
    try:
        res = requests.get(url, params=params, timeout=10)
        if res.status_code == 200:
            data = res.json()
            return True, data.get("name", "Unknown Page")
        else:
            err = res.json().get("error", {})
            return False, err.get("message", "Token invalid")
    except Exception as e:
        return False, str(e)

def start_upload_session(page_id, file_name, file_length, access_token):
    url = f"{FB_BASE_URL}/{page_id}/video_reels"
    params = {
        "upload_phase": "start",
        "file_name": file_name,
        "file_length": str(file_length),
        "file_type": "video/mp4",
        "access_token": access_token
    }
    res = requests.post(url, params=params, timeout=30)
    data = res.json()
    if res.status_code == 200:
        upload_url = data.get("upload_url")
        video_id = data.get("video_id")
        if upload_url and video_id:
            return upload_url, video_id
    err = data.get("error", {})
    safe_print(f"   [Error] Gagal mulai upload session: HTTP {res.status_code} - {err.get('message', json.dumps(data))}")
    return None, None

def upload_file_chunk(upload_url, file_path, access_token):
    with open(file_path, "rb") as f:
        data = f.read()
    headers = {
        "Authorization": f"OAuth {access_token}",
        "offset": "0",
        "file_size": str(len(data))
    }
    res = requests.post(upload_url, headers=headers, data=data, timeout=300)
    if res.status_code in (200, 201, 202):
        return True
    err = res.json().get("error", {}) if res.text.strip().startswith("{") else {}
    safe_print(f"   [Error] Gagal upload file: HTTP {res.status_code} - {err.get('message', res.text[:200])}")
    return False

def publish_reels(page_id, video_id, title, description, privacy, access_token):
    url = f"{FB_BASE_URL}/{page_id}/video_reels"
    body = {
        "upload_phase": "finish",
        "video_id": video_id,
        "title": title[:100],
        "description": description[:1000],
        "video_state": "PUBLISHED",
        "access_token": access_token
    }
    if privacy and privacy != "PUBLIC":
        body["privacy"] = json.dumps({"value": privacy})
    res = requests.post(url, data=body, timeout=30)
    data = res.json()
    if res.status_code == 200:
        published_id = data.get("id") or data.get("video_id") or video_id
        return True, published_id
    err = data.get("error", {})
    return False, err.get("message", json.dumps(data))

def find_clip_files(video_id, folder="clips_output"):
    if not os.path.exists(folder):
        return []
    files = []
    for f in os.listdir(folder):
        if f.startswith(f"{video_id}_") and f.endswith(".mp4") and "_nocap" not in f and "_temp_" not in f:
            parts = f.replace(".mp4", "").split("_")
            if len(parts) >= 2:
                moment_id = parts[1]
                files.append((moment_id, os.path.join(folder, f)))
    return files

if __name__ == "__main__":
    if len(sys.argv) < 2:
        safe_print("\n[Error] Anda belum memasukkan ID Video!")
        safe_print("Cara menjalankan: python upload_facebook.py <ID_VIDEO>")
        sys.exit(1)

    target_video_id = sys.argv[1]
    fb_cfg = load_facebook_config()

    page_id = fb_cfg.get("page_id", "")
    access_token = fb_cfg.get("page_access_token", "")
    privacy = fb_cfg.get("privacy", "PUBLIC")

    if not page_id or not access_token:
        safe_print("[Error] Facebook Page ID atau Access Token belum dikonfigurasi!")
        safe_print("        Buka halaman Pengaturan > Facebook Reels untuk mengisi.")
        sys.exit(1)

    safe_print("[1/4] Memverifikasi token Facebook...")
    token_ok, page_name = verify_token(page_id, access_token)
    if not token_ok:
        safe_print(f"[Error] Token Facebook tidak valid: {page_name}")
        safe_print("        Buka halaman Pengaturan > Facebook Reels untuk update token.")
        sys.exit(1)
    safe_print(f"   Token valid. Page: {page_name}")

    safe_print("[2/4] Membaca data momen dari database...")
    dict_momen, channel_name = get_moments_from_db(target_video_id)
    if not dict_momen:
        safe_print(f"[Peringatan] Tidak ada momen yang perlu diupload ke Facebook untuk Video ID {target_video_id}.")
        sys.exit(0)

    safe_print("[3/4] Memindai file klip...")
    clip_files = find_clip_files(target_video_id)
    if not clip_files:
        safe_print(f"[Error] Tidak ada file klip ditemukan untuk Video ID {target_video_id}.")
        sys.exit(1)

    safe_print("[4/4] Memulai upload Reels ke Facebook...\n")

    counter_upload = 0
    counter_fail = 0

    for moment_id, file_path in clip_files:
        if moment_id not in dict_momen:
            continue

        data_momen = dict_momen[moment_id]
        judul = data_momen["judul"]
        deskripsi_bersih = data_momen["deskripsi"].strip()
        hashtag_str = data_momen["hashtag"]

        description = f"{deskripsi_bersih}\n\n{hashtag_str}".strip()
        if channel_name:
            description += f"\n\nSumber: {channel_name}"
        description = description[:1000]

        safe_print(f"-> [{counter_upload+counter_fail+1}/{len(clip_files)}] Mengupload Reels Momen ID {moment_id}: \"{judul}\"")

        try:
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)

            safe_print(f"   Memulai upload session ({file_size} bytes)...")
            upload_url, video_id = start_upload_session(page_id, file_name, file_size, access_token)
            if not upload_url:
                counter_fail += 1
                time.sleep(2)
                continue

            safe_print(f"   Mengirim file ke Facebook...")
            upload_ok = upload_file_chunk(upload_url, file_path, access_token)
            if not upload_ok:
                counter_fail += 1
                time.sleep(2)
                continue

            safe_print(f"   Mempublikasikan Reels...")
            pub_ok, pub_result = publish_reels(page_id, video_id, judul, description, privacy, access_token)

            if pub_ok:
                safe_print(f"   [Sukses] Reels berhasil diupload! Video ID: {pub_result}")
                mark_uploaded_fb(moment_id)
                counter_upload += 1
            else:
                safe_print(f"   [Gagal] Publish gagal: {pub_result}")
                if "expired" in str(pub_result).lower() or "190" in str(pub_result):
                    safe_print("   [PENTING] Token Facebook expired. Update token di Pengaturan.")
                counter_fail += 1

            time.sleep(3)

        except Exception as e:
            err_type = type(e).__name__
            safe_print(f"   [Gagal] {err_type}: {str(e)}")
            counter_fail += 1
            time.sleep(2)

    if counter_upload == 0 and counter_fail == 0:
        safe_print(f"[Peringatan] Tidak ada file cocok untuk ID {target_video_id}.")
    elif counter_upload > 0:
        safe_print(f"\n[Selesai] Total {counter_upload} Reels berhasil diupload ke Facebook!")
        if counter_fail > 0:
            safe_print(f"[Info] {counter_fail} momen gagal diupload.")
    else:
        safe_print(f"\n[Gagal] Semua upload gagal untuk Video ID {target_video_id}.")

    if counter_fail > 0:
        sys.exit(1)
