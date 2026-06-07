import os
import sys
import json
import sqlite3
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

class ClipperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Nurohman Clipper - AI Video Shorts Automation")
        self.root.geometry("750x680") # Sedikit ditinggikan ukurannya untuk ruang tombol baru
        self.root.configure(bg="#1e1e1e")
        
        # Simpan reference file environment dan database
        self.env_file = "environment.txt"
        self.db_file = "database_konten.db"
        
        # Konfigurasi gaya widget (Style UI)
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('TLabel', background='#1e1e1e', foreground='#ffffff', font=('Arial', 10))
        self.style.configure('TButton', font=('Arial', 10, 'bold'), borderwidth=1)
        self.style.configure('Step.TButton', background='#3a3a3a', foreground='white')
        self.style.configure('Danger.TButton', background='#d63031', foreground='white')
        
        # Buat Komponen UI
        self.buat_komponen_input()
        self.buat_komponen_log()
        self.buat_komponen_tombol_individual()
        
        # Load API Key saat aplikasi pertama dibuka
        self.load_api_key()

    def buat_komponen_input(self):
        # Frame Atas (Input & Setting)
        frame_top = tk.Frame(self.root, bg="#1e1e1e", padx=15, pady=15)
        frame_top.pack(fill=tk.X)
        
        # --- INPUT LINK YOUTUBE ---
        lbl_url = ttk.Label(frame_top, text="Link URL YouTube:")
        lbl_url.pack(anchor=tk.W, pady=(0,5))
        
        self.ent_url = tk.Entry(frame_top, bg="#2d2d2d", fg="white", insertbackground="white", font=('Arial', 11), bd=1, relief=tk.SOLID)
        self.ent_url.pack(fill=tk.X, pady=(0,15))
        self.ent_url.insert(0, "https://www.youtube.com/watch?v=...")

        # --- SETTING GEMINI API KEY ---
        lbl_api = ttk.Label(frame_top, text="Gemini API Key:")
        lbl_api.pack(anchor=tk.W, pady=(0,5))
        
        frame_api = tk.Frame(frame_top, bg="#1e1e1e")
        frame_api.pack(fill=tk.X, pady=(0,15))
        
        self.ent_api = tk.Entry(frame_api, bg="#2d2d2d", fg="white", insertbackground="white", font=('Arial', 10), bd=1, relief=tk.SOLID, show="*")
        self.ent_api.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,10))
        
        btn_save_api = ttk.Button(frame_api, text="Simpan / Ubah API Key", command=self.save_api_key)
        btn_save_api.pack(side=tk.RIGHT)
        
        # --- TOMBOL AUTOMATIS (ALL-IN-ONE) ---
        self.btn_auto = tk.Button(
            frame_top, text="⚡ PROSES OTOMATIS (All-in-One)", 
            font=('Arial', 12, 'bold'), bg="#ff9f43", fg="black",
            activebackground="#f39c12", bd=0, pady=10, cursor="hand2",
            command=self.mulai_proses_otomatis
        )
        self.btn_auto.pack(fill=tk.X, pady=5)

    def buat_komponen_log(self):
        # Frame Tengah (Console Log Terminal)
        frame_mid = tk.Frame(self.root, bg="#1e1e1e", padx=15)
        frame_mid.pack(fill=tk.BOTH, expand=True)
        
        lbl_log = ttk.Label(frame_mid, text="Output Log Terminal:")
        lbl_log.pack(anchor=tk.W, pady=(0,5))
        
        self.txt_log = scrolledtext.ScrolledText(frame_mid, bg="#0c0c0c", fg="#00ff00", font=('Consolas', 10), bd=0)
        self.txt_log.pack(fill=tk.BOTH, expand=True)
        self.append_log("[Sistem] Aplikasi siap digunakan. Silakan masukkan parameter.")

    def buat_komponen_tombol_individual(self):
        # Frame Bawah (Tombol Individual Berjajar)
        frame_bot = tk.Frame(self.root, bg="#2d2d2d", padx=15, pady=12)
        frame_bot.pack(fill=tk.X, side=tk.BOTTOM)
        
        # Baris Judul & Tombol Cleanup diletakkan bersebelahan
        frame_header_bot = tk.Frame(frame_bot, bg="#2d2d2d")
        frame_header_bot.pack(fill=tk.X, pady=(0,8))
        
        lbl_indiv = tk.Label(frame_header_bot, text="Eksekusi Manual Per Tahap:", bg="#2d2d2d", fg="#aaaaaa", font=('Arial', 9, 'italic'))
        lbl_indiv.pack(side=tk.LEFT, anchor=tk.W)
        
        # --- TOMBOL CLEAN OLD SESSIO ---
        self.btn_cleanup = ttk.Button(frame_header_bot, text="🧹 clean old sessio", style='Danger.TButton', command=self.cleanup_database)
        self.btn_cleanup.pack(side=tk.RIGHT)
        
        frame_buttons = tk.Frame(frame_bot, bg="#2d2d2d")
        frame_buttons.pack(fill=tk.X)
        
        # Menggunakan grid pembagi rata 4 kolom
        frame_buttons.grid_columnconfigure(0, weight=1, minsize=100)
        frame_buttons.grid_columnconfigure(1, weight=1, minsize=100)
        frame_buttons.grid_columnconfigure(2, weight=1, minsize=100)
        frame_buttons.grid_columnconfigure(3, weight=1, minsize=100)
        
        self.btn_analisa = ttk.Button(frame_buttons, text="1. Analisa Gemini", style='Step.TButton', command=lambda: self.jalankan_tahap_tunggal("analisa"))
        self.btn_analisa.grid(row=0, column=0, padx=4, sticky="ew")
        
        self.btn_download = ttk.Button(frame_buttons, text="2. Download Video", style='Step.TButton', command=lambda: self.jalankan_tahap_tunggal("download"))
        self.btn_download.grid(row=0, column=1, padx=4, sticky="ew")
        
        self.btn_potong = ttk.Button(frame_buttons, text="3. Potong Video", style='Step.TButton', command=lambda: self.jalankan_tahap_tunggal("potong"))
        self.btn_potong.grid(row=0, column=2, padx=4, sticky="ew")
        
        self.btn_upload = ttk.Button(frame_buttons, text="4. Upload YouTube", style='Step.TButton', command=lambda: self.jalankan_tahap_tunggal("upload"))
        self.btn_upload.grid(row=0, column=3, padx=4, sticky="ew")

    # --- LOGIKA MANAJEMEN API KEY ---
    def load_api_key(self):
        if os.path.exists(self.env_file):
            try:
                with open(self.env_file, "r") as f:
                    baris = f.read().strip()
                    if baris.startswith("GEMINI_API_KEY="):
                        key = baris.replace("GEMINI_API_KEY=", "").strip()
                        self.ent_api.delete(0, tk.END)
                        self.ent_api.insert(0, key)
                        self.append_log("[Sistem] Berhasil memuat Gemini API Key dari environment.txt")
            except Exception as e:
                self.append_log(f"[Error] Gagal membaca environment.txt: {e}")

    def save_api_key(self):
        key_input = self.ent_api.get().strip()
        if not key_input:
            messagebox.showwarning("Peringatan", "Kolom API Key tidak boleh kosong!")
            return
        try:
            with open(self.env_file, "w") as f:
                f.write(f"GEMINI_API_KEY={key_input}")
            messagebox.showinfo("Sukses", "Gemini API Key berhasil disimpan ke environment.txt")
            self.append_log("[Sistem] API Key berhasil diperbarui dan disimpan.")
        except Exception as e:
            messagebox.showerror("Error", f"Gagal menyimpan file: {e}")

    # --- LOGIKA CLEAN OLD SESSIO ---
    def cleanup_database(self):
        """Menghapus semua records/data di database SQLite dan membersihkan berkas unduhan/hasil klip"""
        if not os.path.exists(self.db_file):
            messagebox.showinfo("Info", "File database_konten.db belum terbentuk atau tidak ditemukan.")
            return
            
        # Tampilkan kotak konfirmasi demi keamanan data
        konfirmasi = messagebox.askyesno(
            "Konfirmasi Hapus Total", 
            "Apakah Anda yakin ingin MENGHAPUS SEMUA DATA di database,\nfile video podcast, dan hasil klip video?\n\nTindakan ini tidak dapat dibatalkan!",
            icon='warning'
        )
        
        if konfirmasi:
            try:
                # 1. Hapus data dari SQLite
                conn = sqlite3.connect(self.db_file)
                cursor = conn.cursor()
                
                # Mengosongkan data dari tabel yang ada
                cursor.execute("DELETE FROM moments;")
                cursor.execute("DELETE FROM videos;")
                
                # Mengosongkan cache internal sequence SQLite agar ID kembali dimulai dari 1
                cursor.execute("DELETE FROM sqlite_sequence WHERE name='videos' OR name='moments';")
                
                conn.commit()
                conn.close()
                self.append_log("\n🧹 [Database] CLEANUP BERHASIL! Semua data di database_konten.db telah dikosongkan.")
                
                # 2. Hapus file di videos_podcast
                folder_download = "videos_podcast"
                if os.path.exists(folder_download):
                    deleted_download_count = 0
                    for f in os.listdir(folder_download):
                        file_path = os.path.join(folder_download, f)
                        if os.path.isfile(file_path):
                            try:
                                os.remove(file_path)
                                self.append_log(f"🧹 [File] Dihapus: {file_path}")
                                deleted_download_count += 1
                            except Exception as ex:
                                self.append_log(f"[Error] Gagal menghapus file {file_path}: {ex}")
                    if deleted_download_count > 0:
                        self.append_log(f"🧹 [Info] Berhasil menghapus {deleted_download_count} file di folder '{folder_download}'.")

                # 3. Hapus file di clips_output
                folder_clips = "clips_output"
                if os.path.exists(folder_clips):
                    deleted_clips_count = 0
                    for f in os.listdir(folder_clips):
                        file_path = os.path.join(folder_clips, f)
                        if os.path.isfile(file_path):
                            try:
                                os.remove(file_path)
                                self.append_log(f"🧹 [File] Dihapus: {file_path}")
                                deleted_clips_count += 1
                            except Exception as ex:
                                self.append_log(f"[Error] Gagal menghapus file {file_path}: {ex}")
                    if deleted_clips_count > 0:
                        self.append_log(f"🧹 [Info] Berhasil menghapus {deleted_clips_count} file di folder '{folder_clips}'.")
                
                messagebox.showinfo("Sukses", "Database dan seluruh file sesi lama berhasil dibersihkan total!")
            except Exception as e:
                self.append_log(f"[Error] Gagal melakukan cleanup: {e}")
                messagebox.showerror("Error", f"Gagal mengosongkan data: {e}")

    # --- LOGIKA PENANGANAN LOG TERMINAL ---
    def append_log(self, text):
        self.txt_log.insert(tk.END, text + "\n")
        self.txt_log.see(tk.END)

    # --- DRIVER UTAMA THREADING (ANTI-FREEZE) ---
    def set_status_tombol(self, state):
        self.btn_auto.config(state=state)
        self.btn_analisa.config(state=state)
        self.btn_download.config(state=state)
        self.btn_potong.config(state=state)
        self.btn_upload.config(state=state)
        self.btn_cleanup.config(state=state)

    def eksekusi_script_live(self, perintah, nama_tahap):
        self.append_log(f"\n=== Memulai Tahap: {nama_tahap.upper()} ===")
        try:
            proses = subprocess.Popen(
                perintah,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                shell=True,
                bufsize=1
            )
            
            for line in proses.stdout:
                self.append_log(line.strip())
                
            proses.wait()
            return proses.returncode
        except Exception as e:
            self.append_log(f"[Error Kritis] Gagal mengeksekusi {nama_tahap}: {e}")
            return -1

    # --- FLOW AUTOMATIS (ALL-IN-ONE) ---
    def mulai_proses_otomatis(self):
        url = self.ent_url.get().strip()
        if url == "" or "watch" not in url and "youtu.be" not in url:
            messagebox.showwarning("Input Salah", "Silakan masukkan link URL YouTube yang valid!")
            return
            
        self.set_status_tombol(tk.DISABLED)
        threading.Thread(target=self.worker_proses_otomatis, args=(url,), daemon=True).start()

    def worker_proses_otomatis(self, url_video):
        self.append_log("\n🚀 MENJALANKAN PIPELINE OTOMATIS (ALL-IN-ONE)...")
        
        code_analisa = self.eksekusi_script_live([sys.executable, "analisa_youtube.py", url_video], "Analisa Gemini")
        if code_analisa != 0:
            self.append_log("❌ [Gagal] Proses otomatis dihentikan pada tahap Analisa.")
            self.root.after(0, lambda: self.set_status_tombol(tk.NORMAL))
            return
            
        code_download = self.eksekusi_script_live([sys.executable, "download_youtube.py", url_video], "Download Master Video")
        if code_download != 0:
            self.append_log("❌ [Gagal] Proses otomatis dihentikan pada tahap Download.")
            self.root.after(0, lambda: self.set_status_tombol(tk.NORMAL))
            return

        self.append_log("\n[Sistem] Menunggu input ID Video untuk pemotongan dan upload...")
        
        id_video_terpilih = self.MintaIDPopup()
        if not id_video_terpilih:
            self.append_log("❌ [Batal] Proses otomatis dibatalkan oleh pengguna karena ID kosong.")
            self.root.after(0, lambda: self.set_status_tombol(tk.NORMAL))
            return

        code_potong = self.eksekusi_script_live([sys.executable, "potong_video.py", id_video_terpilih], "Batch Potong Video (FFmpeg)")
        if code_potong != 0:
            self.append_log("❌ [Gagal] Proses otomatis dihentikan pada tahap Pemotongan.")
            self.root.after(0, lambda: self.set_status_tombol(tk.NORMAL))
            return

        code_upload = self.eksekusi_script_live([sys.executable, "upload_youtube.py", id_video_terpilih], "Batch Upload YouTube Data API")
        if code_upload == 0:
            self.append_log("\n🎉 [SUKSES BESAR] Seluruh rangkaian proses otomatis selesai dilaksanakan!")
            self.root.after(0, lambda: messagebox.showinfo("Sukses", "Rangkaian Shorts Automasi Selesai Diupload!"))
        else:
            self.append_log("❌ [Gagal] Masalah ditemukan pada tahap upload.")
            
        self.root.after(0, lambda: self.set_status_tombol(tk.NORMAL))

    # --- FLOW MANUAL PER TAHAP ---
    def jalankan_tahap_tunggal(self, nama_tahap):
        url = self.ent_url.get().strip()
        
        if nama_tahap in ["analisa", "download"]:
            if url == "" or "http" not in url:
                messagebox.showwarning("Input Salah", "Tahap ini memerlukan Link URL YouTube!")
                return
            target_param = url
        else:
            id_video = self.MintaIDPopup()
            if not id_video:
                return
            target_param = id_video

        self.set_status_tombol(tk.DISABLED)
        threading.Thread(target=self.worker_tahap_tunggal, args=(nama_tahap, target_param), daemon=True).start()

    def worker_tahap_tunggal(self, nama_tahap, param):
        if nama_tahap == "analisa":
            perintah = [sys.executable, "analisa_youtube.py", param]
        elif nama_tahap == "download":
            perintah = [sys.executable, "download_youtube.py", param]
        elif nama_tahap == "potong":
            perintah = [sys.executable, "potong_video.py", param]
        elif nama_tahap == "upload":
            perintah = [sys.executable, "upload_youtube.py", param]
            
        self.eksekusi_script_live(perintah, nama_tahap)
        self.root.after(0, lambda: self.set_status_tombol(tk.NORMAL))

    # --- FUNGSI PEMBANTU POPUP INPUT ID ---
    def MintaIDPopup(self):
        self.id_result = None
        
        win_pop = tk.Toplevel(self.root)
        win_pop.title("Masukkan ID Video")
        win_pop.geometry("300x130")
        win_pop.configure(bg="#2d2d2d")
        win_pop.resizable(False, False)
        win_pop.grab_set()
        
        lbl = tk.Label(win_pop, text="Masukkan ID Video dari Database SQLite:", bg="#2d2d2d", fg="white", font=('Arial', 10))
        lbl.pack(pady=(15,5))
        
        ent = tk.Entry(win_pop, font=('Arial', 11), justify="center", bd=1, relief=tk.SOLID)
        ent.pack(pady=5)
        ent.focus()
        
        def konfirmasi():
            res = ent.get().strip()
            if res:
                self.id_result = res
                win_pop.destroy()
            else:
                messagebox.showwarning("Kosong", "ID Video tidak boleh kosong!", parent=win_pop)
                
        btn = ttk.Button(win_pop, text="OK, Lanjutkan", command=konfirmasi)
        btn.pack(pady=10)
        
        self.root.wait_window(win_pop)
        return self.id_result

if __name__ == "__main__":
    root_window = tk.Tk()
    app = ClipperGUI(root_window)
    root_window.mainloop()
