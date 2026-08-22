# reel-extract — Instagram Reel Downloader, Extractor & Comprehension Pipeline

Standalone Python tool to download Instagram Reels, extract audio for speech transcription, pull video frames for vision processing, describe visual content via Ollama, and bundle all context for summarization.

## Capabilities

- **yt-dlp**: Downloads the highest quality video and extracts post caption & metadata into `caption.txt` and `meta.json`.
- **ffmpeg**:
  - Converts/remuxes audio to 16kHz mono WAV (`audio.wav`), optimized for local Whisper models.
  - Extracts 5 evenly spaced JPEG keyframes (`frames/frame_01.jpg` ... `frames/frame_05.jpg`).
- **faster-whisper**: Transcribes speech from `audio.wav` locally into `transcript.txt`.
- **Ollama Vision (`moondream`)**: Analyzes each frame image to generate concise visual scene descriptions in `frames_description.txt`.
- **Context Bundling**: Merges metadata, caption, transcript, and frame descriptions into `combined_context.txt`.

## Installation / Prerequisites

Ensure `yt-dlp` and `ffmpeg` are installed on your system PATH:

```bash
python -m pip install -r requirements.txt
ollama pull moondream
```

## Standalone Usage

### 1. Download & Media Extraction (`extract.py`)

Run `extract.py` passing an Instagram Reel URL:

```bash
python extract.py "https://www.instagram.com/reel/DcRCbBNTMSK/"
```

### 2. Comprehension & Transcription (`understand.py`)

Run `understand.py` pointing to the extracted reel folder:

```bash
python understand.py reel-extract/data/DcRCbBNTMSK/
```

### Output Folder Structure

Output generated under `reel-extract/data/<reel_id>/`:

```text
reel-extract/data/DcRCbBNTMSK/
├── video.mp4                 # Extracted full video file
├── audio.wav                 # 16kHz mono WAV file for transcription
├── caption.txt               # Full Instagram caption / post description text
├── meta.json                 # Structured metadata (URL, status, title, upload date)
├── transcript.txt            # Speech transcription from faster-whisper
├── frames_description.txt    # Frame-by-frame visual descriptions from Ollama
├── combined_context.txt      # Aggregated context file ready for LLM summarization
└── frames/                   # Extracted key frames
    ├── frame_01.jpg
    ├── frame_02.jpg
    ├── frame_03.jpg
    ├── frame_04.jpg
    └── frame_05.jpg
```

