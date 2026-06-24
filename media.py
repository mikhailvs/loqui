"""Speech I/O: faster-whisper STT and edge-tts TTS.

Separated from the HTTP server and the turn engine. All external calls (ffmpeg,
ffprobe, whisper, edge-tts) are bounded and log on failure rather than crashing a
turn; temp files are request-scoped (a tempdir per call) so the coarse server lock
is not load-bearing for filename safety.
"""
from __future__ import annotations
import logging
import os
import shutil
import subprocess
import tempfile
import uuid

import app_settings
import voice

log = logging.getLogger("loqui.media")
MIN_SPEECH_SEC = 0.35
_WMODEL = None
_DBG = 0


def warm() -> None:
    _whisper()


def _whisper():
    """Load the STT model ONCE and keep it resident (int8 on CPU, built-in VAD)."""
    global _WMODEL
    if _WMODEL is None:
        from faster_whisper import WhisperModel
        _WMODEL = WhisperModel(app_settings.WHISPER_MODEL, device="cpu", compute_type="int8")
    return _WMODEL


def _duration(path: str) -> float:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", path], capture_output=True, text=True, timeout=15)
        return float(r.stdout.strip())
    except (ValueError, subprocess.SubprocessError, FileNotFoundError):
        return 0.0


def _debug(audio_bytes: bytes, wav: str, transcript: str) -> None:
    """Optional diagnostic: set STT_DEBUG_DIR to capture every clip + what was heard."""
    dbg = os.environ.get("STT_DEBUG_DIR")
    if not dbg:
        return
    global _DBG
    _DBG += 1
    try:
        os.makedirs(dbg, exist_ok=True)
        if os.path.exists(wav):
            shutil.copy(wav, os.path.join(dbg, f"in_{_DBG}.wav"))
        with open(os.path.join(dbg, "log.txt"), "a") as f:
            f.write(f"{_DBG}\tdur={_duration(wav):.2f}s\tbytes={len(audio_bytes)}\t"
                    f"transcript={transcript!r}\n")
    except Exception:
        pass


def transcribe(audio_bytes: bytes, lang: str = "pt") -> str:
    """Browser audio (webm/mp4) -> 16k mono wav -> text. Returns '' for silence or
    on any decode/transcribe failure (logged); the caller treats '' as 'no input'."""
    with tempfile.TemporaryDirectory() as td:
        raw, wav = os.path.join(td, "in.bin"), os.path.join(td, "in.wav")
        with open(raw, "wb") as f:
            f.write(audio_bytes)
        try:
            subprocess.run(["ffmpeg", "-y", "-i", raw, "-ar", "16000", "-ac", "1", wav],
                           capture_output=True, timeout=15, check=True)
        except (subprocess.SubprocessError, FileNotFoundError):
            log.exception("ffmpeg decode failed")
            return ""
        if _duration(wav) < MIN_SPEECH_SEC:        # too short = silence/accidental tap
            _debug(audio_bytes, wav, "")
            return ""
        try:
            segs, _info = _whisper().transcribe(
                wav, language=lang, beam_size=1, temperature=0,
                vad_filter=True, condition_on_previous_text=False)
            txt = " ".join(s.text.strip() for s in segs).strip()
        except Exception:
            log.exception("whisper/transcribe failed (treating as silence)")
            txt = ""
        _debug(audio_bytes, wav, txt)
        return txt


def synth_turn(text: str, audio_dir: str, voice_name: str):
    """Synthesize a tutor line; return a /audio/<uuid>.mp3 URL or None on failure."""
    if not text or not text.strip():
        return None
    name = f"turn_{uuid.uuid4().hex[:8]}.mp3"
    try:
        voice.synth(text, os.path.join(audio_dir, name), voice=voice_name)
    except Exception:
        log.exception("tts failed (turn proceeds without audio)")
        return None
    return f"/audio/{name}"
