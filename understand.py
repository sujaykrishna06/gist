#!/usr/bin/env python3
"""
Reel Comprehension Pipeline (Audio Transcription + Vision Frame Description)
-----------------------------------------------------------------------------
Input: Path to a reel data directory (e.g. data/<reel_id>/)
Outputs:
  - transcript.txt (Speech-to-text via faster-whisper)
  - frames_description.txt (Visual description of keyframes via Ollama vision model)
  - combined_context.txt (Aggregated context combining caption, transcript, and visual descriptions)
"""

import sys
import os
import json
import base64
import urllib.request
import urllib.parse
from pathlib import Path

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "http://localhost:11434/api/generate")

def transcribe_audio(audio_path: Path, output_path: Path, model_size: str = "tiny") -> str:
    print(f"[understand] Transcribing audio with faster-whisper ({model_size})...", flush=True)
    if not audio_path.exists():
        print(f"[warn] Audio file not found at {audio_path}", flush=True)
        output_path.write_text("[No audio file found]", encoding="utf-8")
        return ""

    if WhisperModel is None:
        err_msg = "[error] faster-whisper library is not installed."
        print(err_msg, flush=True)
        output_path.write_text(err_msg, encoding="utf-8")
        return err_msg

    try:
        # cpu_threads=0 automatically uses all available CPU cores
        model = WhisperModel(model_size, device="cpu", compute_type="int8", cpu_threads=0)
        segments, info = model.transcribe(str(audio_path), beam_size=1)

        transcript_lines = []
        for segment in segments:
            transcript_lines.append(segment.text.strip())

        full_transcript = " ".join(transcript_lines).strip()
        if not full_transcript:
            full_transcript = "[No speech detected in audio track]"

        output_path.write_text(full_transcript, encoding="utf-8")
        print(f"[understand] Transcription complete. Length: {len(full_transcript)} chars.", flush=True)
        return full_transcript
    except Exception as e:
        err_msg = f"[Error during transcription: {e}]"
        print(f"[error] Transcription failed: {e}", flush=True)
        output_path.write_text(err_msg, encoding="utf-8")
        return err_msg

def describe_frame_with_ollama(image_path: Path, model_name: str = "moondream") -> str:
    if not image_path.exists():
        return "[Frame image not found]"

    try:
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")

        payload = {
            "model": model_name,
            "prompt": "Describe what is clearly visible in this video frame concisely.",
            "images": [img_b64],
            "stream": False
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(OLLAMA_API_URL, data=data, headers={"Content-Type": "application/json"})

        with urllib.request.urlopen(req, timeout=25) as resp:
            res_json = json.loads(resp.read().decode("utf-8"))
            raw_text = res_json.get("response", "").strip()

            if len(raw_text) > 300:
                raw_text = raw_text[:300] + "..."
            return raw_text
    except Exception as e:
        print(f"[warn] Ollama vision notice for {image_path.name}: {e}", flush=True)
        return f"[Visual frame description unavailable]"

def describe_all_frames(frames_dir: Path, output_path: Path, model_name: str = "moondream") -> str:
    print(f"[understand] Analyzing key frame using Ollama vision model ({model_name})...", flush=True)
    if not frames_dir.exists():
        output_path.write_text("[No frames directory found]", encoding="utf-8")
        return ""

    frame_files = sorted(list(frames_dir.glob("*.jpg")))
    if not frame_files:
        output_path.write_text("[No frame images found]", encoding="utf-8")
        return ""

    # Pick single representative middle keyframe for fast CPU processing
    mid_idx = len(frame_files) // 2
    frame_path = frame_files[mid_idx]
    
    desc = describe_frame_with_ollama(frame_path, model_name=model_name)
    full_descriptions = f"Keyframe ({frame_path.name}): {desc}"

    output_path.write_text(full_descriptions, encoding="utf-8")
    print(f"[understand] Frame description complete.", flush=True)
    return full_descriptions

def bundle_combined_context(reel_dir: Path) -> Path:
    meta_path = reel_dir / "meta.json"
    caption_path = reel_dir / "caption.txt"
    transcript_path = reel_dir / "transcript.txt"
    frames_path = reel_dir / "frames_description.txt"
    combined_path = reel_dir / "combined_context.txt"

    meta = {}
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            pass

    caption = caption_path.read_text(encoding="utf-8") if caption_path.exists() else "[No caption]"
    transcript = transcript_path.read_text(encoding="utf-8") if transcript_path.exists() else "[No transcript]"
    frames_desc = frames_path.read_text(encoding="utf-8") if frames_path.exists() else "[No frame descriptions]"

    context_str = f"""==================================================
REEL METADATA
==================================================
Reel ID: {meta.get("reel_id", reel_dir.name)}
URL: {meta.get("url", "N/A")}
Uploader: {meta.get("uploader", "N/A")}
Upload Date: {meta.get("upload_date", "N/A")}
Status: {meta.get("status", "success")}

==================================================
INSTAGRAM POST CAPTION
==================================================
{caption.strip()}

==================================================
AUDIO TRANSCRIPTION (SPEECH-TO-TEXT)
==================================================
{transcript.strip()}

==================================================
VISUAL FRAME DESCRIPTIONS (KEYFRAMES)
==================================================
{frames_desc.strip()}
==================================================
"""
    combined_path.write_text(context_str, encoding="utf-8")
    print(f"[understand] Combined context saved to {combined_path}", flush=True)
    return combined_path

def process_reel_understanding(reel_dir: Path, vision_model: str = "moondream") -> Path:
    audio_file = reel_dir / "audio.wav"
    transcript_file = reel_dir / "transcript.txt"
    frames_dir = reel_dir / "frames"
    frames_desc_file = reel_dir / "frames_description.txt"

    transcribe_audio(audio_file, transcript_file)
    describe_all_frames(frames_dir, frames_desc_file, model_name=vision_model)
    combined = bundle_combined_context(reel_dir)
    return combined

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python understand.py <reel_data_directory>")
        sys.exit(1)

    target_dir = Path(sys.argv[1]).resolve()
    if not target_dir.exists():
        print(f"Error: Target directory {target_dir} does not exist.")
        sys.exit(1)

    process_reel_understanding(target_dir)
