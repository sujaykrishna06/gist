#!/usr/bin/env python3
"""
Standalone Reel Downloader and Extractor
----------------------------------------
Input: Instagram Reel URL
Output: Structured directory under data/<reel_id>/ containing:
  - video.mp4 (Downloaded reel video)
  - audio.wav (16kHz mono WAV for speech transcription)
  - frames/ (4-6 key frames saved as frame_01.jpg, frame_02.jpg...)
  - caption.txt (Original post caption/description)
  - meta.json (Extracted metadata)
"""

import sys
import os
import re
import json
import subprocess
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

def sanitize_reel_id(url: str) -> str:
    match = re.search(r"/(reel|reels|p)/([A-Za-z0-9_-]+)", url)
    if match:
        return match.group(2)
    clean = re.sub(r"[^A-Za-z0-9_-]", "_", url)
    return clean[-15:] if len(clean) > 15 else clean

def get_video_duration(video_path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path)
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(res.stdout.strip())
    except Exception as e:
        print(f"[warn] ffprobe failed to get duration: {e}", flush=True)
        return 0.0

def extract_reel(url: str, num_frames: int = 3) -> Path:
    reel_id = sanitize_reel_id(url)
    output_dir = DATA_DIR / reel_id
    output_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = output_dir / "frames"
    frames_dir.mkdir(exist_ok=True)

    print(f"[extract] Processing Reel ID: {reel_id}", flush=True)
    print(f"[extract] Output Directory: {output_dir}", flush=True)

    # 1. Run yt-dlp to download video and metadata
    info_json_path = output_dir / "video.info.json"
    ytdlp_cmd = [
        "yt-dlp",
        "-f", "bestvideo+bestaudio/best",
        "--write-info-json",
        "--no-warnings",
        "-o", str(output_dir / "temp_video.%(ext)s"),
        url
    ]

    print(f"[extract] Downloading video with yt-dlp...", flush=True)
    try:
        res = subprocess.run(ytdlp_cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"yt-dlp download failed: {res.stderr.strip()}")
    except Exception as e:
        error_meta = {
            "reel_id": reel_id,
            "url": url,
            "status": "error",
            "error": str(e)
        }
        with open(output_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump(error_meta, f, indent=2)
        print(f"[error] Failed to download reel: {e}", flush=True)
        raise RuntimeError(f"Failed to download reel: {e}")

    # Locate downloaded video file and rename/remux to video.mp4
    downloaded_files = list(output_dir.glob("temp_video.*"))
    video_file = None
    for f in downloaded_files:
        if f.suffix != ".json":
            video_file = f
            break

    if not video_file or not video_file.exists():
        raise RuntimeError("No downloaded video file found.")

    final_video_path = output_dir / "video.mp4"
    if video_file.suffix.lower() == ".mp4":
        if final_video_path.exists():
            final_video_path.unlink()
        video_file.rename(final_video_path)
    else:
        print(f"[extract] Remuxing {video_file.name} to video.mp4 using ffmpeg...", flush=True)
        remux_cmd = ["ffmpeg", "-i", str(video_file), "-c", "copy", str(final_video_path), "-y"]
        subprocess.run(remux_cmd, capture_output=True, check=True)
        video_file.unlink()

    # Parse metadata info json if present
    caption_text = ""
    meta = {
        "reel_id": reel_id,
        "url": url,
        "status": "success",
        "title": "",
        "uploader": "",
        "upload_date": ""
    }

    info_files = list(output_dir.glob("*.info.json"))
    if info_files:
        try:
            with open(info_files[0], "r", encoding="utf-8") as f:
                info_data = json.load(f)
            caption_text = info_data.get("description") or info_data.get("title") or ""
            meta["title"] = info_data.get("title", "")
            meta["uploader"] = info_data.get("uploader", "")
            meta["upload_date"] = info_data.get("upload_date", "")
            info_files[0].unlink()
        except Exception as e:
            print(f"[warn] Failed to parse info JSON: {e}", flush=True)

    with open(output_dir / "caption.txt", "w", encoding="utf-8") as f:
        f.write(caption_text.strip())

    with open(output_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    # 2. Extract Audio (16kHz mono WAV) for Whisper
    audio_path = output_dir / "audio.wav"
    print(f"[extract] Extracting audio track to audio.wav...", flush=True)
    audio_cmd = [
        "ffmpeg",
        "-i", str(final_video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(audio_path),
        "-y"
    ]
    res_audio = subprocess.run(audio_cmd, capture_output=True, text=True)
    if res_audio.returncode != 0:
        print(f"[warn] Audio extraction notice: {res_audio.stderr.strip()}", flush=True)

    # 3. Extract Key Frames
    print(f"[extract] Extracting {num_frames} key frames...", flush=True)
    duration = get_video_duration(final_video_path)
    
    if duration > 0:
        interval = duration / num_frames
        for i in range(num_frames):
            timestamp = (i + 0.5) * interval
            frame_path = frames_dir / f"frame_{i+1:02d}.jpg"
            frame_cmd = [
                "ffmpeg",
                "-ss", f"{timestamp:.2f}",
                "-i", str(final_video_path),
                "-vframes", "1",
                "-q:v", "2",
                str(frame_path),
                "-y"
            ]
            subprocess.run(frame_cmd, capture_output=True)
    else:
        fallback_cmd = [
            "ffmpeg",
            "-i", str(final_video_path),
            "-vf", "fps=1/5",
            "-vframes", str(num_frames),
            str(frames_dir / "frame_%02d.jpg"),
            "-y"
        ]
        subprocess.run(fallback_cmd, capture_output=True)

    extracted_frames = list(frames_dir.glob("*.jpg"))
    print(f"[extract] Done! Extracted {len(extracted_frames)} frames.", flush=True)
    print(f"[extract] Reel files ready at: {output_dir}", flush=True)
    return output_dir

def cleanup_reel(output_dir: Path):
    """Clean up temporary media and frame files to save disk space."""
    try:
        if output_dir.exists():
            shutil.rmtree(output_dir)
            print(f"[cleanup] Deleted temporary directory: {output_dir}", flush=True)
    except Exception as e:
        print(f"[warn] Failed to clean up {output_dir}: {e}", flush=True)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract.py <instagram_reel_url>")
        sys.exit(1)

    url_input = sys.argv[1]
    extract_reel(url_input)
