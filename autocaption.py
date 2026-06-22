import argparse
import os
import sys
import subprocess
import whisper
from whisper.utils import get_writer

def cek_ffmpeg():
    """Memastikan FFmpeg tersedia di PATH"""
    try:
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("[Error] FFmpeg tidak ditemukan! Pastikan FFmpeg terinstal dan tersedia di PATH.")
        sys.exit(1)

def extract_audio(video_path, audio_path):
    cek_ffmpeg()
    print(f"Mengekstrak audio dari {video_path}...")
    command = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn", 
        "-acodec", "pcm_s16le", 
        "-ar", "16000", 
        "-ac", "1", 
        audio_path
    ]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("Ekstraksi audio selesai.")

def transcribe_audio(audio_path, srt_path, model_name="medium"):
    print(f"Memuat model Whisper ({model_name})...")
    model = whisper.load_model(model_name)
    
    print("Mulai mentranskripsi audio (Bahasa: Indonesia)...")
    # Transkripsi audio
    result = model.transcribe(audio_path, language="id", verbose=True)
    
    # Simpan sebagai .srt
    print(f"Menyimpan subtitle ke {srt_path}...")
    # Whisper's get_writer expects the format, and the output directory
    output_dir = os.path.dirname(srt_path)
    if not output_dir:
        output_dir = "."
    
    writer = get_writer("srt", output_dir)
    # The writer will append the extension to the base name we provide
    # We strip the extension from srt_path to pass as the base name
    base_name = os.path.splitext(os.path.basename(srt_path))[0]
    writer(result, os.path.join(output_dir, base_name))
    print("Penyimpanan subtitle selesai.")

def burn_subtitles(video_path, srt_path, output_path, font_name, font_size, align, margin_v, margin_h):
    print(f"Menambahkan subtitle ke video (Hardcode) dengan font {font_name}...")
    # Pastikan format path aman untuk FFmpeg (Windows)
    # FFmpeg membutuhkan format path tertentu untuk filter `subtitles`
    safe_srt_path = srt_path.replace("\\", "/")
    # Tambahkan escaping ekstra jika path absolute di Windows (C:/...)
    if ":" in safe_srt_path:
        safe_srt_path = safe_srt_path.replace(":", "\\:")

    # Style subtitle:
    # MarginL dan MarginR membatasi batas kiri-kanan, MarginV batas atas/bawah
    style = f"FontName={font_name},FontSize={font_size},Alignment={align},PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,MarginV={margin_v},MarginL={margin_h},MarginR={margin_h}"

    command = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"subtitles='{safe_srt_path}':force_style='{style}'",
        "-c:a", "copy",
        output_path
    ]
    subprocess.run(command, check=True)
    print(f"Video selesai diproses dan disimpan di: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Auto Captions: Tambahkan subtitle ke video secara otomatis.")
    parser.add_argument("input_video", help="Path ke file video input")
    parser.add_argument("-o", "--output", help="Path untuk file video output (Opsional)", default=None)
    parser.add_argument("-m", "--model", help="Model Whisper yang digunakan (base, small, medium, large)", default="base")
    parser.add_argument("--font", help="Nama Font untuk subtitle", default="Cooper Black")
    parser.add_argument("--fontsize", help="Ukuran Font", default="8")
    parser.add_argument("--align", help="Posisi dasar (2=Bawah Tengah, 8=Atas Tengah, 5=Tengah, 1=Bawah Kiri, dll)", default="2")
    parser.add_argument("--margin-v", help="Kordinat Y (Jarak vertikal dari posisi dasar)", default="100")
    parser.add_argument("--margin-h", help="Kordinat X (Jarak horizontal dari sisi kiri/kanan)", default="0")
    
    args = parser.parse_args()
    input_video = args.input_video
    
    if not os.path.exists(input_video):
        print(f"Error: File {input_video} tidak ditemukan.")
        return

    # Tentukan nama file sementara dan output
    base_name = os.path.splitext(input_video)[0]
    temp_audio = f"{base_name}_temp_audio.wav"
    temp_srt = f"{base_name}_temp_audio.srt"
    
    output_video = args.output
    if not output_video:
        output_video = f"{base_name}_captioned.mp4"

    try:
        extract_audio(input_video, temp_audio)
        # temp_srt will actually be temp_audio.srt because we pass temp_audio as base to the writer
        transcribe_audio(temp_audio, temp_srt, args.model)
        burn_subtitles(input_video, temp_srt, output_video, args.font, args.fontsize, args.align, args.margin_v, args.margin_h)
        
    except Exception as e:
        print(f"Terjadi kesalahan: {e}")
        
    finally:
        # Bersihkan file sementara
        print("Membersihkan file sementara...")
        if os.path.exists(temp_audio):
            os.remove(temp_audio)
        if os.path.exists(temp_srt):
            os.remove(temp_srt)
        print("Selesai.")

if __name__ == "__main__":
    main()