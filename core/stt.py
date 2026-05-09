"""
core/stt.py — Speech to Text
Uses OpenAI Whisper (local, offline) to transcribe audio to text.
Optimized for CPU with the 'base' model.
"""

import numpy as np
import logging
import time
import sounddevice as sd
from typing import Optional

logger = logging.getLogger(__name__)


class SpeechToText:
    """
    Wraps OpenAI Whisper for local speech transcription.
    Completely offline — no API calls, no data leaves your machine.
    """

    def __init__(self, config: dict):
        self.cfg = config
        self.model_name = config.get("whisper_model", "base")
        self.language = config.get("language", "en")
        self.sample_rate = 16000

        self._model = None
        self._load_model()

    def _load_model(self):
        """Load Whisper model (downloads on first run ~150MB for 'base')."""
        try:
            import whisper
            logger.info(f"Loading Whisper '{self.model_name}' model...")
            start = time.time()
            self._model = whisper.load_model(self.model_name)
            elapsed = time.time() - start
            logger.info(f"Whisper loaded in {elapsed:.1f}s")
        except ImportError:
            logger.error("openai-whisper not installed. Run: pip install openai-whisper")
            raise
        except Exception as e:
            logger.error(f"Failed to load Whisper: {e}")
            raise

    def transcribe(self, audio: np.ndarray) -> str:
        """
        Transcribe audio array to text.
        
        Args:
            audio: float32 numpy array, 16kHz mono
            
        Returns:
            Transcribed text string (empty string if failed/silent)
        """
        if self._model is None:
            return ""

        if len(audio) < self.sample_rate * 0.3:  # Minimum 0.3 seconds
            logger.debug("Audio too short, skipping transcription")
            return ""

        try:
            start = time.time()

            # Whisper expects float32 audio normalized to [-1, 1]
            if audio.dtype != np.float32:
                audio = audio.astype(np.float32)

            # Normalize if needed
            max_val = np.abs(audio).max()
            if max_val > 1.0:
                audio = audio / max_val

            result = self._model.transcribe(
                audio,
                language=self.language,
                fp16=False,          # CPU doesn't support fp16
                temperature=0,       # Greedy decoding — more deterministic
                no_speech_threshold=0.6,
                condition_on_previous_text=False,
            )

            text = result["text"].strip()
            elapsed = time.time() - start
            logger.debug(f"Transcribed in {elapsed:.2f}s: '{text}'")
            return text

        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return ""

    def transcribe_file(self, filepath: str) -> str:
        """Transcribe an audio file."""
        try:
            import whisper
            result = self._model.transcribe(
                filepath,
                language=self.language,
                fp16=False,
            )
            return result["text"].strip()
        except Exception as e:
            logger.error(f"File transcription error: {e}")
            return ""

    def record_and_transcribe(self, duration: float = 5.0) -> str:
        """
        Simple blocking record + transcribe (no VAD).
        Used as fallback when VAD is not available.
        """
        logger.info(f"Recording for {duration}s...")
        audio = sd.rec(
            int(duration * self.sample_rate),
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32"
        )
        sd.wait()
        audio = audio.flatten()
        return self.transcribe(audio)
