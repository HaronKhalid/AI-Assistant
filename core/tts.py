"""
core/tts.py — Kokoro-ONNX TTS (Best open-source female voice)
Primary:  kokoro-onnx  (works on Python 3.13, CPU, beautiful natural voice)
Fallback: Piper TTS
Fallback: eSpeak NG

Kokoro voices (female):
  af_heart   — warm, flowing, most natural ❤️  (DEFAULT)
  af_bella   — smooth and confident
  af_sarah   — clear and friendly
  af_nova    — bright and energetic
  af_nicole  — soft and calm
  bf_emma    — British English, elegant
  bf_isabella— British English, rich
"""

import subprocess
import logging
import os
import tempfile
import threading
import queue
import re
import time
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)


class TextToSpeech:
    def __init__(self, config: dict):
        self.cfg = config
        self.voice = config.get("kokoro_voice", "af_heart")
        self.speed = config.get("speaking_rate", 1.0)
        self.piper_binary = config.get("piper_binary", "models/piper/piper")
        self.voice_model = config.get("voice_model", "models/piper/en_US-lessac-medium.onnx")
        self.fallback = config.get("fallback_engine", "espeak")

        self._engine = None          # "kokoro", "piper", "espeak"
        self._kokoro_pipeline = None
        self._kokoro_voices = None
        self._speaking = False

        self._speak_queue = queue.Queue()
        self._worker = threading.Thread(
            target=self._speak_worker, daemon=True, name="TTSWorker"
        )
        self._worker.start()

        self._init_engine()

    def _init_engine(self):
        """Try engines in order of quality: kokoro-onnx > piper > espeak."""

        # ── Try Kokoro-ONNX ──────────────────────────────────
        try:
            from kokoro_onnx import Kokoro
            import soundfile as sf

            model_path = self.cfg.get("kokoro_model", "models/kokoro/kokoro-v1.0.onnx")
            voices_path = self.cfg.get("kokoro_voices", "models/kokoro/voices-v1.0.bin")

            if not os.path.exists(model_path) or not os.path.exists(voices_path):
                logger.info("Kokoro model files not found, downloading...")
                self._download_kokoro_models(model_path, voices_path)

            self._kokoro = Kokoro(model_path, voices_path)
            self._engine = "kokoro"
            logger.info(f"✅ Kokoro-ONNX TTS ready — voice: {self.voice}")
            return
        except ImportError:
            logger.info("kokoro-onnx not installed, trying next engine...")
        except Exception as e:
            logger.warning(f"Kokoro-ONNX init failed: {e}")

        # ── Try Piper ─────────────────────────────────────────
        if (os.path.isfile(self.piper_binary) and
                os.access(self.piper_binary, os.X_OK) and
                os.path.isfile(self.voice_model)):
            self._engine = "piper"
            logger.info("✅ Piper TTS ready")
            return

        # ── Fallback: eSpeak ─────────────────────────────────
        self._engine = "espeak"
        logger.warning("⚠️  Using eSpeak fallback (robotic voice). Install kokoro-onnx for best quality.")

    def _download_kokoro_models(self, model_path: str, voices_path: str):
        """Download Kokoro ONNX model files from GitHub releases."""
        import requests

        os.makedirs(os.path.dirname(model_path), exist_ok=True)

        files = {
            model_path:  "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
            voices_path: "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
        }

        for dest, url in files.items():
            if os.path.exists(dest):
                continue
            logger.info(f"Downloading {os.path.basename(dest)} (~{url.split('/')[-1]})...")
            try:
                r = requests.get(url, stream=True, timeout=120)
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0))
                downloaded = 0
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = downloaded * 100 // total
                            print(f"\r  Downloading {os.path.basename(dest)}: {pct}%", end="", flush=True)
                print()
                logger.info(f"✅ Downloaded: {dest}")
            except Exception as e:
                logger.error(f"Download failed for {dest}: {e}")
                raise

    # ── Public API ────────────────────────────────────────────
    def speak(self, text: str, blocking: bool = False):
        if not text or not text.strip():
            return
        text = self._clean(text)
        if blocking:
            self._do_speak(text)
        else:
            self._speak_queue.put(text)

    def stop(self):
        subprocess.run(["pkill", "-f", "aplay"], capture_output=True)
        subprocess.run(["pkill", "-f", "espeak"], capture_output=True)
        while not self._speak_queue.empty():
            try: self._speak_queue.get_nowait()
            except queue.Empty: break
        self._speaking = False

    @property
    def is_speaking(self): return self._speaking

    # ── Internal ──────────────────────────────────────────────
    def _speak_worker(self):
        while True:
            try:
                text = self._speak_queue.get(timeout=1.0)
                self._speaking = True
                self._do_speak(text)
                self._speaking = False
                self._speak_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"TTS worker error: {e}")
                self._speaking = False

    def _do_speak(self, text: str):
        if self._engine == "kokoro":
            self._speak_kokoro(text)
        elif self._engine == "piper":
            self._speak_piper(text)
        else:
            self._speak_espeak(text)

    def _speak_kokoro(self, text: str):
        """Speak using Kokoro-ONNX — natural neural voice."""
        try:
            import soundfile as sf

            # Generate audio samples
            samples, sample_rate = self._kokoro.create(
                text,
                voice=self.voice,
                speed=self.speed,
                lang="en-us",
            )

            # Write to temp WAV and play
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = f.name

            sf.write(wav_path, samples, sample_rate)

            subprocess.run(
                ["aplay", "-q", wav_path],
                capture_output=True, timeout=60
            )
            os.unlink(wav_path)

        except Exception as e:
            logger.error(f"Kokoro speak error: {e}")
            self._speak_espeak(text)

    def _speak_piper(self, text: str):
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = f.name
            proc = subprocess.run(
                [self.piper_binary, "--model", self.voice_model, "--output_file", wav_path],
                input=text.encode("utf-8"), capture_output=True, timeout=30
            )
            if proc.returncode == 0:
                subprocess.run(["aplay", "-q", wav_path], capture_output=True, timeout=60)
            os.unlink(wav_path)
        except Exception as e:
            logger.error(f"Piper error: {e}")
            self._speak_espeak(text)

    def _speak_espeak(self, text: str):
        try:
            subprocess.run(
                ["espeak-ng", "-v", "en-us+f3", "-s", "145", "-p", "55", "-a", "100", text],
                capture_output=True, timeout=30
            )
        except Exception as e:
            logger.error(f"eSpeak error: {e}")

    def _clean(self, text: str) -> str:
        text = re.sub(r'\*+([^*]+)\*+', r'\1', text)
        text = re.sub(r'#+\s', '', text)
        text = re.sub(r'`[^`]+`', '', text)
        text = re.sub(r'https?://\S+', 'a web link', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def set_voice(self, voice_name: str):
        """Change voice at runtime."""
        self.voice = voice_name
        logger.info(f"Voice changed to: {voice_name}")

    def get_engine(self) -> str:
        return self._engine or "unknown"