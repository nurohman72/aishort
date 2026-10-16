import os
import sys
import json
import sqlite3
import asyncio

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
            encoded_bytes = text.encode(sys.stdout.encoding or 'utf-8', errors='replace')
            print(encoded_bytes.decode(sys.stdout.encoding or 'utf-8', errors='replace'), flush=True)
        except Exception:
            print(text.encode('utf-8', errors='replace').decode('utf-8', errors='replace'), flush=True)

CONFIG_FILE = "config.json"
DB_FILE = "database_konten.db"

def load_telegram_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
            return cfg.get("telegram", {})
        except Exception:
            pass
    return {}

def get_moments_from_db(video_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, judul_menarik, hashtag_terbaik, deskripsi_pendek
        FROM moments WHERE video_id = ? AND (is_uploaded_tg = 0 OR is_uploaded_tg IS NULL) AND is_selected = 1
    """, (video_id,))
    rows = cursor.fetchall()
    cursor.execute("SELECT channel_video FROM videos WHERE id = ?", (video_id,))
    ch = cursor.fetchone()
    conn.close()
    channel = ch[0] if ch and ch[0] else ""
    return {str(r[0]): {"judul": r[1], "hashtag": r[2] or "#shorts", "deskripsi": r[3] or ""} for r in rows}, channel

def mark_uploaded_tg(moment_id):
    try:
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE moments SET is_uploaded_tg = 1, upload_tanggal_tg = ? WHERE id = ?", (today, moment_id))
        conn.commit()
        conn.close()
    except Exception as ex:
        safe_print(f"   [Peringatan] Gagal tandai TG: {ex}")

def find_clip_files(video_id, folder="clips_output"):
    if not os.path.exists(folder):
        return []
    files = []
    for f in os.listdir(folder):
        if f.startswith(f"{video_id}_") and f.endswith(".mp4") and "_nocap" not in f and "_temp_" not in f:
            parts = f.replace(".mp4", "").split("_")
            if len(parts) >= 2:
                files.append((parts[1], os.path.join(folder, f)))
    return files

if __name__ == "__main__":
    if len(sys.argv) < 2:
        safe_print("[Error] python upload_telegram.py <ID_VIDEO>")
        sys.exit(1)
    target_video_id = sys.argv[1]
    tg_cfg = load_telegram_config()
    api_id = tg_cfg.get("api_id", "")
    api_hash = tg_cfg.get("api_hash", "")
    session_name = tg_cfg.get("session_name", "nurclipper_tg")

    if not api_id or not api_hash:
        safe_print("[Error] Telegram API ID / API Hash belum dikonfigurasi di Pengaturan > Telegram.")
        sys.exit(1)

    safe_print("[1/3] Membaca momen dari database...")
    dict_momen, channel_name = get_moments_from_db(target_video_id)
    if not dict_momen:
        safe_print(f"[Info] Tidak ada momen perlu upload Telegram untuk Video ID {target_video_id}.")
        sys.exit(0)

    safe_print("[2/3] Memindai file klip...")
    clip_files = find_clip_files(target_video_id)
    if not clip_files:
        safe_print(f"[Error] Tidak ada file klip untuk Video ID {target_video_id}.")
        sys.exit(1)

    safe_print("[3/3] Upload ke Telegram (Telethon)...")

    async def run():
        from telethon import TelegramClient
        client = TelegramClient(session_name, int(api_id), api_hash)
        await client.start()
        me = await client.get_me()
        safe_print(f"   Login sebagai: {me.first_name} (@{me.username})")
        ok = 0
        fail = 0
        for moment_id, file_path in clip_files:
            if moment_id not in dict_momen:
                continue
            d = dict_momen[moment_id]
            caption = f"{d['judul']}\n\n{d['deskripsi']}\n\n{d['hashtag']}"
            if channel_name:
                caption += f"\n\nSumber: {channel_name}"
            caption = caption.strip()[:1000]
            safe_print(f"-> [{ok+fail+1}/{len(clip_files)}] Upload Momen {moment_id}: {d['judul'][:40]}")
            try:
                await client.send_file("me", file_path, caption=caption, supports_streaming=True)
                safe_print(f"   [Sukses] Terkirim ke Saved Messages")
                mark_uploaded_tg(moment_id)
                ok += 1
            except Exception as e:
                safe_print(f"   [Gagal] {type(e).__name__}: {e}")
                fail += 1
        await client.disconnect()
        return ok, fail

    try:
        ok, fail = asyncio.run(run())
        if ok:
            safe_print(f"[Selesai] {ok} klip terkirim ke Telegram (Saved Messages).")
            if fail:
                safe_print(f"[Info] {fail} gagal.")
        else:
            safe_print("[Gagal] Semua upload Telegram gagal.")
        if fail:
            sys.exit(1)
    except Exception as e:
        safe_print(f"[Gagal] {type(e).__name__}: {e}")
        import traceback
        safe_print(traceback.format_exc()[:800])
        sys.exit(1)
