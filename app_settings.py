"""App-layer runtime knobs — the ones with multiple consumers or env overrides.

Pedagogy tunables live in harness/config.py (kept separate on purpose). Single-use
timeouts stay inline next to the code that uses them (no indirection for its own
sake). This module only holds values that are read in more than one place or are
meant to be overridden from the environment.
"""
import os

# brain (LLM) endpoint — point at a LAN box e.g.
#   BRAIN_URL=http://192.168.1.50:11434/api/chat BRAIN_MODEL=qwen3:30b-a3b
BRAIN_URL = os.environ.get("BRAIN_URL", "http://localhost:11434/api/chat")
BRAIN_MODEL = os.environ.get("BRAIN_MODEL", "qwen3:8b")

# speech-to-text model (faster-whisper): tiny|base|small|medium|large-v3
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")

# server ports
VOICE_PORT = int(os.environ.get("VOICE_PORT", "8443"))
SIM_PORT = int(os.environ.get("SIM_PORT", "8000"))
